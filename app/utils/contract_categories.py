"""Contract category lookup helpers."""
from time import monotonic

import pyodbc
from flask import current_app, has_app_context


FALLBACK_CONTRACT_CATEGORIES = [
    'Administrative And Related Services',
    'Capital Equipment',
    'Clinical',
    'Facilities And Construction',
    'Food Services',
    'Information Technology',
    'Laboratory',
    'Medical Devices',
    'Pharmaceuticals',
    'Professional Services',
    'Supplies',
    'Other',
]

# These categories are always appended to the list returned by the PRIME query.
SUPPLEMENTAL_CONTRACT_CATEGORIES = [
    'Wave - Med/Surg',
    'Wave - Non-Clinical',
    'Wave - PPI',
    'Wave - Rx/Formulary',
]

_CACHE_TTL_SECONDS = 1800
_CONTRACT_CATEGORY_QUERY = """
SELECT DISTINCT ContractType
FROM dbo.GHX_CONTRACT_ORGANIZATION
WHERE ExpirationDate >= GETDATE()
  AND ContractType IS NOT NULL
  AND LTRIM(RTRIM(ContractType)) <> ''
ORDER BY ContractType
"""
_CONTRACT_LOOKUP_QUERY = """
SELECT DISTINCT ContractNumber, Vendor
FROM dbo.GHX_CONTRACT_ORGANIZATION
WHERE ExpirationDate >= GETDATE()
    AND ContractNumber IS NOT NULL
    AND LTRIM(RTRIM(ContractNumber)) <> ''
ORDER BY ContractNumber, Vendor
"""
_contract_category_cache = {
    'expires_at': 0.0,
    'values': tuple(FALLBACK_CONTRACT_CATEGORIES),
}
_contract_lookup_cache = {
        'expires_at': 0.0,
        'pairs': tuple(),
}


def _build_prime_connection_string(config):
    """Build the PRIME database ODBC connection string."""
    driver = config.get('PRIME_DB_DRIVER') or config.get('DB_DRIVER') or 'ODBC Driver 17 for SQL Server'
    server = config.get('PRIME_DB_SERVER') or 'MISCPRDADHOCDB'
    database = config.get('PRIME_DB_NAME') or 'PRIME'
    trusted = str(
        config.get('PRIME_DB_TRUSTED_CONNECTION')
        or config.get('DB_TRUSTED_CONNECTION')
        or 'yes'
    ).lower()

    if trusted == 'yes':
        return 'Driver={{{}}};Server={};Database={};Trusted_Connection=yes;'.format(
            driver,
            server,
            database,
        )

    user = config.get('PRIME_DB_USER') or config.get('DB_USER') or ''
    password = config.get('PRIME_DB_PASSWORD') or config.get('DB_PASSWORD') or ''
    return 'Driver={{{}}};Server={};Database={};UID={};PWD={};'.format(
        driver,
        server,
        database,
        user,
        password,
    )


def _query_contract_categories(config):
    """Fetch active contract categories from PRIME."""
    timeout = int(config.get('PRIME_DB_TIMEOUT', 5) or 5)
    connection_string = _build_prime_connection_string(config)

    with pyodbc.connect(connection_string, timeout=timeout) as connection:
        connection.timeout = timeout
        cursor = connection.cursor()
        cursor.execute(_CONTRACT_CATEGORY_QUERY)
        rows = cursor.fetchall()

    categories = []
    seen = set()
    for row in rows:
        value = str(row[0]).strip() if row and row[0] is not None else ''
        if not value:
            continue
        normalized = value.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        categories.append(value)
    return categories


def _query_contract_lookup_rows(config):
    """Fetch active contract number and vendor pairs from PRIME."""
    timeout = int(config.get('PRIME_DB_TIMEOUT', 5) or 5)
    connection_string = _build_prime_connection_string(config)

    with pyodbc.connect(connection_string, timeout=timeout) as connection:
        connection.timeout = timeout
        cursor = connection.cursor()
        cursor.execute(_CONTRACT_LOOKUP_QUERY)
        rows = cursor.fetchall()

    contract_pairs = []
    seen = set()
    for row in rows:
        contract_number = str(row[0]).strip() if row and row[0] is not None else ''
        vendor_name = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ''
        if not contract_number:
            continue

        normalized_key = (contract_number.casefold(), vendor_name.casefold())
        if normalized_key in seen:
            continue

        seen.add(normalized_key)
        contract_pairs.append({
            'contract_number': contract_number,
            'vendor_name': vendor_name,
        })

    return contract_pairs


def _merge_supplemental(categories):
    """Append SUPPLEMENTAL_CONTRACT_CATEGORIES that are not already present (case-insensitive)."""
    existing = {c.casefold() for c in categories}
    result = list(categories)
    for cat in SUPPLEMENTAL_CONTRACT_CATEGORIES:
        if cat.casefold() not in existing:
            result.append(cat)
    return result


def get_contract_categories(force_refresh=False):
    """Return contract categories from PRIME, with caching and a safe fallback."""
    if not has_app_context():
        return _merge_supplemental(list(FALLBACK_CONTRACT_CATEGORIES))

    now = monotonic()
    if not force_refresh and _contract_category_cache['values'] and now < _contract_category_cache['expires_at']:
        return _merge_supplemental(list(_contract_category_cache['values']))

    try:
        categories = _query_contract_categories(current_app.config)
        if categories:
            _contract_category_cache['values'] = tuple(categories)
            _contract_category_cache['expires_at'] = now + _CACHE_TTL_SECONDS
            return _merge_supplemental(categories)
        raise ValueError('PRIME contract category query returned no active categories.')
    except Exception as exc:
        current_app.logger.warning('Unable to load contract categories from PRIME: %s', exc)
        cached_values = list(_contract_category_cache['values'])
        if cached_values:
            return _merge_supplemental(cached_values)
        return _merge_supplemental(list(FALLBACK_CONTRACT_CATEGORIES))


def get_prime_contract_lookup(force_refresh=False):
    """Return active PRIME contract number and vendor pairs with caching."""
    if not has_app_context():
        return []

    now = monotonic()
    if not force_refresh and _contract_lookup_cache['pairs'] and now < _contract_lookup_cache['expires_at']:
        return [dict(item) for item in _contract_lookup_cache['pairs']]

    try:
        contract_pairs = _query_contract_lookup_rows(current_app.config)
        _contract_lookup_cache['pairs'] = tuple(contract_pairs)
        _contract_lookup_cache['expires_at'] = now + _CACHE_TTL_SECONDS
        return [dict(item) for item in contract_pairs]
    except Exception as exc:
        current_app.logger.warning('Unable to load PRIME contract lookup rows: %s', exc)
        return [dict(item) for item in _contract_lookup_cache['pairs']]


def get_prime_contract_numbers(force_refresh=False):
    """Return distinct active PRIME contract numbers."""
    contract_pairs = get_prime_contract_lookup(force_refresh=force_refresh)
    contract_numbers = []
    seen = set()
    for item in contract_pairs:
        contract_number = (item.get('contract_number') or '').strip()
        if not contract_number:
            continue
        normalized = contract_number.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        contract_numbers.append(contract_number)
    return contract_numbers


def get_prime_vendors_for_contract(contract_number, force_refresh=False):
    """Return distinct active vendors for a PRIME contract number."""
    target = (contract_number or '').strip()
    if not target:
        return []

    vendors = []
    seen = set()
    for item in get_prime_contract_lookup(force_refresh=force_refresh):
        item_contract_number = (item.get('contract_number') or '').strip()
        if item_contract_number.casefold() != target.casefold():
            continue

        vendor_name = (item.get('vendor_name') or '').strip()
        if not vendor_name:
            continue

        normalized = vendor_name.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        vendors.append(vendor_name)

    return vendors