"""
Analytics / Savings Dashboard API endpoints.
Returns aggregated savings data for charts with optional date-range filtering.
All initiative data is now read from dbo.vw_initiative_dashboard instead of
joining the raw tables directly.
"""
from flask import jsonify, request
from datetime import date, datetime, timedelta
from sqlalchemy import text
from app import db
from app.api import analytics_bp
from app.models import FacilityAllocation, Facility

# Map facility code → view column for allocation amount pivots.
_FAC_ALLOC_COL = {
    'MMC':   'MMC_ALLOC',
    'BURKE': 'BURKE_ALLOC',
    'AECOM': 'AECOM_ALLOC',
    'MMVO':  'MMVO_ALLOC',
    'MSSO':  'MSSO_ALLOC',
    'NYACK': 'NYACK_ALLOC',
    'SLCH':  'SLCH_ALLOC',
    'WPH':   'WPH_ALLOC',
}


def _parse_date(value, fallback):
    """Parse ISO date string, returning fallback on failure."""
    if not value:
        return fallback
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return fallback


def _to_date(val):
    """Coerce a value to a Python date, or None."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except (ValueError, TypeError):
        return None


def _fiscal_year(d):
    """Return fiscal year label for a date (Oct 1 → Sep 30)."""
    return d.year if d.month <= 9 else d.year + 1


def _fiscal_quarter(d):
    """Return (fiscal_year, quarter) tuple."""
    fy = _fiscal_year(d)
    month_to_q = {10: 1, 11: 1, 12: 1, 1: 2, 2: 2, 3: 2,
                  4: 3, 5: 3, 6: 3, 7: 4, 8: 4, 9: 4}
    return fy, month_to_q[d.month]


# ---------------------------------------------------------------------------
# Helper: prorate amount over a date range, clipped to filter window
#
# Each row dict: { type, vendor, amount, start, end }
#   - For Cost Savings:  start/end = contract start_date / end_date
#   - For CA / Rebate:   start == end  (single-day event)
#
# For aggregation the amount is prorated:
#   daily_rate = amount / max(total_days, 1)
#   bucket_contribution = daily_rate * days_in_bucket
# ---------------------------------------------------------------------------

def _prorate(amount, row_start, row_end, bucket_start, bucket_end):
    """
    Return the portion of `amount` attributable to [bucket_start, bucket_end].
    `row_start`/`row_end` is the full span of the record.
    """
    total_days = (row_end - row_start).days + 1
    overlap_start = max(row_start, bucket_start)
    overlap_end   = min(row_end,   bucket_end)
    if overlap_end < overlap_start:
        return 0.0
    overlap_days = (overlap_end - overlap_start).days + 1
    return amount * (overlap_days / total_days)


def _fac_sql_parts(facility_codes):
    """
    Given a list of facility codes, return:
      eff_amount_sql – SQL expression for the effective allocated dollar amount
      fac_where_sql  – extra WHERE clause fragment (may be empty string)
    Falls back to the full Savings_Amount when no codes are given or none match.
    """
    if not facility_codes:
        return 'Savings_Amount', ''

    cols = [_FAC_ALLOC_COL[c] for c in facility_codes if c in _FAC_ALLOC_COL]
    if not cols:
        return 'Savings_Amount', ''

    eff_amount_sql = '(' + ' + '.join(f'ISNULL({c}, 0)' for c in cols) + ')'
    fac_where_sql  = 'AND (' + ' OR '.join(f'{c} > 0' for c in cols) + ')'
    return eff_amount_sql, fac_where_sql


def _get_rows(start_date, end_date, include_pending=False, facility_codes=None):
    """
    Return list of dicts: { type, vendor, amount, start, end }
    for all initiatives whose effective date range overlaps [start_date, end_date].

    Reads from dbo.vw_initiative_dashboard (single query, all types).

    Cost Savings: start=Start_Date, end=End_Date  (prorated over range)
    Rebate / CA:  start=end=Start_Date            (single-day lump sum)
    NULL date fallback → CAST(CreateTime AS DATE).

    facility_codes: optional list of facility code strings.
      When provided, the effective amount is the SUM of the matching *_ALLOC
      dollar columns and only rows with at least one non-zero allocation are returned.
    """
    statuses = ['Approved']
    if include_pending:
        statuses.append('Pending Review')
    statuses_str = ', '.join(f"'{s}'" for s in statuses)

    eff_amount_sql, fac_where_sql = _fac_sql_parts(facility_codes)

    sql = text(f"""
        SELECT
            Initiative_Type,
            Vendor_Name,
            ISNULL(Start_Date, CAST(CreateTime AS DATE))                          AS eff_start,
            CASE
                WHEN Initiative_Type = 'Cost Savings'
                THEN ISNULL(End_Date, ISNULL(Start_Date, CAST(CreateTime AS DATE)))
                ELSE ISNULL(Start_Date, CAST(CreateTime AS DATE))
            END                                                                   AS eff_end,
            {eff_amount_sql}                                                      AS eff_amount
        FROM dbo.vw_initiative_dashboard
        WHERE IsDeleted = 0
          AND STATUS IN ({statuses_str})
          AND Savings_Amount IS NOT NULL
          AND (
                (Initiative_Type = 'Cost Savings'
                 AND ISNULL(Start_Date, CAST(CreateTime AS DATE)) <= :end_date
                 AND ISNULL(End_Date, ISNULL(Start_Date, CAST(CreateTime AS DATE))) >= :start_date)
              OR
                (Initiative_Type IN ('Rebate', 'Cost Avoidance')
                 AND ISNULL(Start_Date, CAST(CreateTime AS DATE)) >= :start_date
                 AND ISNULL(Start_Date, CAST(CreateTime AS DATE)) <= :end_date)
          )
          {fac_where_sql}
    """)

    result = db.session.execute(sql, {'start_date': start_date, 'end_date': end_date})

    rows = []
    for r in result:
        init_type = r.Initiative_Type
        vendor    = r.Vendor_Name or 'Unknown'
        amt       = float(r.eff_amount) if r.eff_amount else None
        s         = _to_date(r.eff_start)
        e         = _to_date(r.eff_end)

        if not s or not amt:
            continue

        if init_type == 'Cost Savings':
            rows.append({'type': init_type, 'vendor': vendor,
                         'amount': amt, 'start': s, 'end': e or s})
        else:
            rows.append({'type': init_type, 'vendor': vendor,
                         'amount': amt, 'start': s, 'end': s})

    return rows


# ---------------------------------------------------------------------------
# Summary endpoint  –  GET /api/analytics/summary
# ---------------------------------------------------------------------------

@analytics_bp.route('/summary', methods=['GET'])
def savings_summary():
    """
    Aggregated savings summary for the dashboard.

    Query params:
      start_date      – ISO date  (default: 2 years ago)
      end_date        – ISO date  (default: today)
      include_pending – 'true' to include Pending Review (default false)

    Row structure from _get_rows:
      { type, vendor, amount, start, end }
      Cost Savings : start=contract_start, end=contract_end  → prorated over range
      CA / Rebate  : start==end (single day)                 → lump sum on that day
    """
    today = date.today()
    default_start = today.replace(year=today.year - 2)

    start_date      = _parse_date(request.args.get('start_date'), default_start)
    end_date        = _parse_date(request.args.get('end_date'), today)
    include_pending = request.args.get('include_pending', 'false').lower() == 'true'
    facility_codes  = [c.strip() for c in request.args.get('facility_codes', '').split(',') if c.strip()] or None

    rows = _get_rows(start_date, end_date, include_pending, facility_codes)

    # ── Totals by category (full contract amount, no proration) ─────────────
    totals = {'Cost Savings': 0.0, 'Rebate': 0.0, 'Cost Avoidance': 0.0}
    for r in rows:
        totals[r['type']] += r['amount']

    # ── Vendor pivot (full contract amount) ──────────────────────────────────
    vendor_map = {}
    for r in rows:
        v = r['vendor']
        if v not in vendor_map:
            vendor_map[v] = {'Cost Savings': 0.0, 'Rebate': 0.0, 'Cost Avoidance': 0.0}
        vendor_map[v][r['type']] += r['amount']

    vendor_rows = []
    for v, cats in sorted(vendor_map.items(), key=lambda x: -(sum(x[1].values()))):
        vendor_rows.append({
            'vendor': v,
            'cost_savings':    cats['Cost Savings'],
            'rebate':          cats['Rebate'],
            'cost_avoidance':  cats['Cost Avoidance'],
            'total':           sum(cats.values()),
        })

    # ── By Day ──────────────────────────────────────────────────────────────
    # Cost Savings: prorated daily over [start, end] clipped to filter window.
    # CA / Rebate:  lump sum on their single date (start==end).
    day_map = {}

    def _add_day(d, typ, amt):
        key = d.isoformat()
        if key not in day_map:
            day_map[key] = {'Cost Savings': 0.0, 'Rebate': 0.0, 'Cost Avoidance': 0.0}
        day_map[key][typ] += amt

    for r in rows:
        r_start = max(r['start'], start_date)
        r_end   = min(r['end'],   end_date)
        total_days = (r['end'] - r['start']).days + 1
        span_days  = (r_end - r_start).days + 1
        if r['start'] == r['end']:
            # Single-day event (CA / Rebate): full amount on that day
            _add_day(r['start'], r['type'], r['amount'])
        else:
            # Multi-day contract (Cost Savings): prorate per day within filter window
            daily = r['amount'] / total_days
            cur = r_start
            while cur <= r_end:
                _add_day(cur, r['type'], daily)
                cur += timedelta(days=1)

    by_day = [
        {
            'date':           k,
            'cost_savings':   v['Cost Savings'],
            'rebate':         v['Rebate'],
            'cost_avoidance': v['Cost Avoidance'],
        }
        for k, v in sorted(day_map.items())
    ]

    # ── By Quarter ──────────────────────────────────────────────────────────
    # CA / Rebate: full amount in their one quarter.
    # Cost Savings: prorated by how many days of the contract fall in each quarter.
    q_map = {}

    def _add_quarter(d, typ, amt):
        fy, q = _fiscal_quarter(d)
        key = f'FY{fy} Q{q}'
        if key not in q_map:
            q_map[key] = {'fy': fy, 'q': q,
                          'Cost Savings': 0.0, 'Rebate': 0.0, 'Cost Avoidance': 0.0}
        q_map[key][typ] += amt

    def _quarter_bounds(fy, q):
        """Return (first_day, last_day) of a fiscal quarter."""
        q_start_month = {1: 10, 2: 1, 3: 4, 4: 7}[q]
        q_start_year  = fy - 1 if q == 1 else fy
        first = date(q_start_year, q_start_month, 1)
        # first day of NEXT quarter
        if q == 1:
            nxt = date(fy, 1, 1)        # Q1 = Oct–Dec → next = Jan of FY year
        elif q == 4:
            nxt = date(fy, 10, 1)       # Q4 = Jul–Sep → next FY starts Oct
        else:
            nxt = date(fy, q_start_month + 3, 1)
        last = nxt - timedelta(days=1)
        return first, last

    for r in rows:
        if r['start'] == r['end']:
            _add_quarter(r['start'], r['type'], r['amount'])
        else:
            total_days = (r['end'] - r['start']).days + 1
            # Walk through each fiscal quarter that overlaps the contract range
            cur = r['start']
            while cur <= r['end']:
                fy, q = _fiscal_quarter(cur)
                q_first, q_last = _quarter_bounds(fy, q)
                overlap_start = max(r['start'], q_first)
                overlap_end   = min(r['end'],   q_last)
                overlap_days  = (overlap_end - overlap_start).days + 1
                portion = r['amount'] * overlap_days / total_days
                _add_quarter(cur, r['type'], portion)
                # Advance to first day of next quarter
                cur = q_last + timedelta(days=1)

    by_quarter = sorted(
        [
            {
                'label':          k,
                'cost_savings':   v['Cost Savings'],
                'rebate':         v['Rebate'],
                'cost_avoidance': v['Cost Avoidance'],
            }
            for k, v in q_map.items()
        ],
        key=lambda x: x['label']
    )

    # ── By Fiscal Year ───────────────────────────────────────────────────────
    fy_map = {}

    def _add_fy(d, typ, amt):
        key = f'FY{_fiscal_year(d)}'
        if key not in fy_map:
            fy_map[key] = {'Cost Savings': 0.0, 'Rebate': 0.0, 'Cost Avoidance': 0.0}
        fy_map[key][typ] += amt

    def _fy_bounds(fy):
        return date(fy - 1, 10, 1), date(fy, 9, 30)

    for r in rows:
        if r['start'] == r['end']:
            _add_fy(r['start'], r['type'], r['amount'])
        else:
            total_days = (r['end'] - r['start']).days + 1
            cur_fy = _fiscal_year(r['start'])
            end_fy = _fiscal_year(r['end'])
            for fy in range(cur_fy, end_fy + 1):
                fy_first, fy_last = _fy_bounds(fy)
                overlap_start = max(r['start'], fy_first)
                overlap_end   = min(r['end'],   fy_last)
                if overlap_end < overlap_start:
                    continue
                overlap_days = (overlap_end - overlap_start).days + 1
                portion = r['amount'] * overlap_days / total_days
                _add_fy(overlap_start, r['type'], portion)

    by_fiscal_year = sorted(
        [
            {
                'label':          k,
                'cost_savings':   v['Cost Savings'],
                'rebate':         v['Rebate'],
                'cost_avoidance': v['Cost Avoidance'],
            }
            for k, v in fy_map.items()
        ],
        key=lambda x: x['label']
    )

    return jsonify({
        'date_range':      {'start': start_date.isoformat(), 'end': end_date.isoformat()},
        'totals':          totals,
        'vendor_breakdown': vendor_rows,
        'by_day':          by_day,
        'by_quarter':      by_quarter,
        'by_fiscal_year':  by_fiscal_year,
    })


# ---------------------------------------------------------------------------
# Details endpoint  –  GET /api/analytics/details
# Returns one flat row per initiative for the full-detail table.
#   start_date / end_date semantics:
#     Cost Savings   → contract start_date … end_date
#     Rebate         → rebate_check_date … rebate_check_date
#     Cost Avoidance → avoidance_date    … avoidance_date
# ---------------------------------------------------------------------------

@analytics_bp.route('/details', methods=['GET'])
def initiative_details():
    """
    Full initiative detail rows for the analytics table.

    Query params:
      start_date      – ISO date filter on effective start date (default: 10 years ago)
      end_date        – ISO date filter on effective end date   (default: today)
      include_pending – 'true' to include Pending Review
    """
    today = date.today()
    default_start = today.replace(year=today.year - 10)

    start_date      = _parse_date(request.args.get('start_date'), default_start)
    end_date        = _parse_date(request.args.get('end_date'), today)
    include_pending = request.args.get('include_pending', 'false').lower() == 'true'
    facility_codes  = [c.strip() for c in request.args.get('facility_codes', '').split(',') if c.strip()] or None

    statuses = ['Approved']
    if include_pending:
        statuses.append('Pending Review')
    statuses_str = ', '.join(f"'{s}'" for s in statuses)

    eff_amount_sql, fac_where_sql = _fac_sql_parts(facility_codes)

    # Amount label and savings-type column differ by initiative type.
    sql = text(f"""
        SELECT
            InitiativeID,
            Initiative_Type,
            STATUS,
            Initiative_Desc,
            Vendor_Name,
            Contract_Number,
            Contract_Category,
            InitiativeOwner,
            Created_By,
            CAST(CreateTime AS DATE)                                              AS created_date,
            ISNULL(Start_Date, CAST(CreateTime AS DATE))                          AS eff_start,
            CASE
                WHEN Initiative_Type = 'Cost Savings'
                THEN ISNULL(End_Date, ISNULL(Start_Date, CAST(CreateTime AS DATE)))
                ELSE ISNULL(Start_Date, CAST(CreateTime AS DATE))
            END                                                                   AS eff_end,
            {eff_amount_sql}                                                      AS eff_amount,
            CASE
                WHEN Initiative_Type = 'Cost Savings'   THEN Cost_Savings_Type_CS
                WHEN Initiative_Type = 'Rebate'         THEN Rebates_Type_RB
                WHEN Initiative_Type = 'Cost Avoidance' THEN Cost_Avoidance_Type_CA
                ELSE NULL
            END                                                                   AS savings_type
        FROM dbo.vw_initiative_dashboard
        WHERE IsDeleted = 0
          AND STATUS IN ({statuses_str})
          AND Savings_Amount IS NOT NULL
          AND (
                (Initiative_Type = 'Cost Savings'
                 AND ISNULL(Start_Date, CAST(CreateTime AS DATE)) <= :end_date
                 AND ISNULL(End_Date, ISNULL(Start_Date, CAST(CreateTime AS DATE))) >= :start_date)
              OR
                (Initiative_Type IN ('Rebate', 'Cost Avoidance')
                 AND ISNULL(Start_Date, CAST(CreateTime AS DATE)) >= :start_date
                 AND ISNULL(Start_Date, CAST(CreateTime AS DATE)) <= :end_date)
          )
          {fac_where_sql}
        ORDER BY ISNULL(Start_Date, CAST(CreateTime AS DATE)) DESC
    """)

    result = db.session.execute(sql, {'start_date': start_date, 'end_date': end_date})

    _amount_label = {
        'Cost Savings':   'Total Savings',
        'Rebate':         'Rebate Amount',
        'Cost Avoidance': 'Avoidance Amount',
    }

    detail_rows = []
    for r in result:
        eff_s = _to_date(r.eff_start)
        eff_e = _to_date(r.eff_end) or eff_s
        facilities = _get_facilities(r.InitiativeID)
        detail_rows.append({
            'id':               r.InitiativeID,
            'type':             r.Initiative_Type,
            'status':           r.STATUS,
            'description':      r.Initiative_Desc or '',
            'vendor':           r.Vendor_Name or '',
            'contract_number':  r.Contract_Number or '',
            'contract_category': r.Contract_Category or '',
            'start_date':       eff_s.isoformat() if eff_s else None,
            'end_date':         eff_e.isoformat() if eff_e else None,
            'amount':           float(r.eff_amount) if r.eff_amount else 0.0,
            'amount_label':     _amount_label.get(r.Initiative_Type, 'Amount'),
            'savings_type':     r.savings_type or '',
            'facilities':       facilities,
            'owner':            r.InitiativeOwner or '',
            'created_by':       r.Created_By or '',
            'created_at':       str(r.created_date) if r.created_date else None,
        })

    # Sort all by start_date desc
    detail_rows.sort(key=lambda r: r['start_date'] or '', reverse=True)

    return jsonify({
        'date_range': {'start': start_date.isoformat(), 'end': end_date.isoformat()},
        'count': len(detail_rows),
        'rows': detail_rows,
    })


# ---------------------------------------------------------------------------
# Facilities list  –  GET /api/analytics/facilities
# ---------------------------------------------------------------------------

@analytics_bp.route('/facilities', methods=['GET'])
def list_facilities():
    """Return all active facilities as [{code, name}] for the filter dropdown."""
    facilities = (
        Facility.query
        .filter_by(is_active=True)
        .order_by(Facility.code)
        .all()
    )
    return jsonify([{'code': f.code, 'name': f.name} for f in facilities])


def _get_facilities(initiative_id):
    """Return list of {code, pct, amount} for each facility allocation, ordered by code."""
    allocs = (
        db.session.query(
            Facility.code,
            FacilityAllocation.allocation_percentage,
            FacilityAllocation.allocation_amount,
        )
        .join(FacilityAllocation, FacilityAllocation.facility_id == Facility.id)
        .filter(FacilityAllocation.initiative_id == initiative_id)
        .order_by(Facility.code)
        .all()
    )
    return [
        {
            'code':   code,
            'pct':    float(pct)    if pct    is not None else None,
            'amount': float(alloc_amt) if alloc_amt is not None else None,
        }
        for code, pct, alloc_amt in allocs
    ]
