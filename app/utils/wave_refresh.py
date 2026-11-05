"""
Wave weekly export refresh.

Ports the WaveL5 workflow (fileprocess.ipynb transformation and the
refresh_wave.py runner) so users can load the weekly Wave export themselves:
validate the workbook, replace the PBI staging table, run the existing merge
procedure and read back the dashboard savings totals.

The transformation uses openpyxl rather than pandas so the IIS deployment
needs no new dependencies. Business rules must stay in lockstep with
fileprocess.ipynb: L0-L5 stage filter, stage mapping, the L0-L5 stage
dates, the $M -> $ conversion and the file's native creation date as the
loaded stamp and the basis of every date check.

The Savings Tracker and the A16 File Upload app each carry this module. Keep
the two copies identical until one of them is retired.
"""
import hashlib
import io
import math
import os
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

import openpyxl
import pyodbc
from dateutil import parser as date_parser
from openpyxl.utils.datetime import from_excel
from werkzeug.utils import secure_filename

from app.utils.timezone import now_eastern


REQUIRED_SHEET_NAME = 'initiative'
DEFAULT_MAX_EXPORT_AGE_DAYS = 10
QUERY_TIMEOUT_SECONDS = 60
APPLOCK_RESOURCE = 'WaveL5.refresh'  # Shared with refresh_wave.py so the two never merge concurrently.

# Export column -> staging column, in insert order (notebook COLMAP_FINAL_TO_DB).
SOURCE_TO_STAGING = [
    ('#', 'Initiative ID'),
    ('Accountable workstream', 'Accountable Workstream'),
    ('Name', 'Initiative Name'),
    ('Weekly status', 'Weekly Status'),
    ('Stage', 'Stage'),
    ('L5 actual date', 'L5 Date'),
    ('Sub. for L5 approv. date', 'SL5 Date'),
    ('L4 actual date', 'L4 Date'),
    ('Sub. for L4 approv. date', 'SL4 Date'),
    ('L3 actual date', 'L3 Date'),
    ('Sub. for L3 approv. date', 'SL3 Date'),
    ('Net recurring benefits (latest estimate, annualized)', 'Net Recurring Benefits Annualized'),
    ('One-time benefits (latest estimate, annualized)', 'Onetime Benefits Annualized'),
    ('L2 actual date', 'L2 Date'),
    ('Sub. for L2 approv. date', 'SL2 Date'),
    ('L1 actual date', 'L1 Date'),
    ('Sub. for L1 approv. date', 'SL1 Date'),
    ('L0 actual date', 'L0 Date'),
]
OPTIONAL_SOURCE_COLUMNS = {'Weekly status'}  # Defaults to 'Active' when the column is absent.
STAGING_COLUMNS = [column for _, column in SOURCE_TO_STAGING] + ['loaded stamp']

# Case-insensitive substring match on Stage, as the notebook's str.contains masks.
STAGE_LEVELS = ('l5', 'l4', 'l3', 'l2', 'l1', 'l0')
STAGE_MAP = {
    'Submitted for L5 approval': 'SL5',
    'Submitted for L4 approval': 'SL4',
    'Submitted for L3 approval': 'SL3',
    'Submitted for L2 approval': 'SL2',
    'Submitted for L1 approval': 'SL1',
}
STAGE_ORDER = ['L5', 'SL5', 'L4', 'SL4', 'L3', 'SL3', 'L2', 'SL2', 'L1', 'SL1', 'L0']

DATE_COLUMNS = {
    'L5 Date', 'SL5 Date', 'L4 Date', 'SL4 Date', 'L3 Date', 'SL3 Date',
    'L2 Date', 'SL2 Date', 'L1 Date', 'SL1 Date', 'L0 Date',
}
MONEY_COLUMNS = {'Net Recurring Benefits Annualized', 'Onetime Benefits Annualized'}
REQUIRED_TEXT_COLUMNS = ('Accountable Workstream', 'Initiative Name', 'Weekly Status')
# varchar limits on SCSSaving.Initiatives_stg; checked up front for a readable error.
TEXT_LIMITS = {'Accountable Workstream': 100, 'Initiative Name': 200, 'Weekly Status': 20, 'Stage': 10}
MONEY_MULTIPLIER = Decimal(1000000)  # Wave exports benefits in millions.
MONEY_SCALE = Decimal('0.0001')      # SQL Server money precision.
INT32_RANGE = (-2147483648, 2147483647)

_STAGING_TABLE = '[SCSSaving].[Initiatives_stg]'
_INSERT_SQL = 'INSERT INTO {} ({}) VALUES ({})'.format(
    _STAGING_TABLE,
    ', '.join(f'[{column}]' for column in STAGING_COLUMNS),
    ', '.join('?' for _ in STAGING_COLUMNS),
)
_STAGING_COLUMNS_SQL = """
SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'SCSSaving' AND TABLE_NAME = 'Initiatives_stg'
"""
_STAGING_SNAPSHOT_SQL = f'SELECT MAX([loaded stamp]), COUNT_BIG(*) FROM {_STAGING_TABLE}'
_SAVINGS_SQL = """
SELECT [Savings Channel], SUM([Total Savings])
FROM [SCSSaving].[vw_MainSavings]
WHERE [Supplemental Staffing Filter] = 'Include'
  AND [Saving Realization Year] = ?
GROUP BY [Savings Channel]
ORDER BY [Savings Channel]
"""
_APPLOCK_SQL = f"""
DECLARE @result int;
EXEC @result = sys.sp_getapplock @Resource = N'{APPLOCK_RESOURCE}',
     @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 0;
SELECT @result;
"""


class WaveRefreshError(RuntimeError):
    """A refresh cannot safely proceed. The message is shown to the user."""

    def __init__(self, message, details=None, status_code=400):
        super().__init__(message)
        self.details = list(details or [])
        self.status_code = status_code


@dataclass
class WaveExport:
    """A validated weekly export, transformed to staging rows."""
    file_name: str
    content: bytes
    sha256: str
    created_at: datetime  # Native creation time, Eastern. See native_created_at.
    rows: list
    stage_counts: dict
    warnings: list = field(default_factory=list)

    @property
    def workbook_date(self):
        return self.created_at.date()

    def staging_rows(self):
        """Rows in STAGING_COLUMNS order, with the native creation date as the loaded stamp."""
        return [row + (self.workbook_date,) for row in self.rows]

    def summary(self):
        return {
            'file_name': self.file_name,
            'sha256': self.sha256,
            'created_at': self.created_at.isoformat(),
            'workbook_date': _iso(self.workbook_date),
            'rows': len(self.rows),
            'stage_counts': self.stage_counts,
            'warnings': self.warnings,
        }


def can_refresh_wave(user):
    """Wave refresh is offered to the same roles that can create initiatives."""
    return bool(user and user.is_active and user.has_permission('create'))


# ---------------------------------------------------------------------------
# Parsing and validation (no database access)
# ---------------------------------------------------------------------------

def parse_export(file_name, content, today=None, max_age_days=DEFAULT_MAX_EXPORT_AGE_DAYS):
    """Validate and transform an uploaded export, raising WaveRefreshError with the reason."""
    if not (file_name or '').lower().endswith('.xlsx'):
        raise WaveRefreshError('Upload the Wave export as an .xlsx workbook.')
    today = today or now_eastern().date()

    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise WaveRefreshError('The file could not be opened as an Excel workbook.') from exc
    try:
        sheet_name, records, has_weekly_status = _read_initiative_sheet(workbook)
    finally:
        workbook.close()

    created_at = native_created_at(content)
    if created_at is None:
        raise WaveRefreshError(
            'Could not determine when this export was created. Saving a Wave download in Excel can '
            'remove that date, so download the original export from Wave again.'
        )
    _check_dates(created_at.date(), today, max_age_days)

    rows, warnings = _transform(records, has_weekly_status)
    if not rows:
        raise WaveRefreshError(f"No L0-L5 initiatives were found on the '{sheet_name}' tab.")
    _check_rows(rows)

    stage_counts = Counter(row[STAGING_COLUMNS.index('Stage')] for row in rows)
    ordered_stages = STAGE_ORDER + sorted(stage for stage in stage_counts if stage not in STAGE_ORDER)
    return WaveExport(
        file_name=file_name,
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        created_at=created_at,
        rows=rows,
        stage_counts={stage: stage_counts[stage] for stage in ordered_stages if stage_counts[stage]},
        warnings=warnings,
    )


def _read_initiative_sheet(workbook):
    """Return the initiative tab's records keyed by export column name."""
    sheet_name = next(
        (name for name in workbook.sheetnames if name.strip().lower() == REQUIRED_SHEET_NAME),
        None,
    )
    if not sheet_name:
        raise WaveRefreshError(f"The workbook is missing the required '{REQUIRED_SHEET_NAME}' tab.")

    rows = workbook[sheet_name].iter_rows(values_only=True)
    positions = {}
    for index, name in enumerate(next(rows, None) or ()):
        if name is not None:
            positions.setdefault(str(name).strip(), index)

    missing = [
        source for source, _ in SOURCE_TO_STAGING
        if source not in positions and source not in OPTIONAL_SOURCE_COLUMNS
    ]
    if missing:
        raise WaveRefreshError(
            f"The '{sheet_name}' tab is missing required columns.",
            details=missing,
        )

    wanted = [(source, positions.get(source)) for source, _ in SOURCE_TO_STAGING]
    records = [
        {source: (row[index] if index is not None and index < len(row) else None) for source, index in wanted}
        for row in rows
    ]
    return sheet_name, records, 'Weekly status' in positions


def _transform(records, has_weekly_status):
    """Apply the notebook's filter, stage mapping and type rules to each record."""
    rows = []
    unreadable_dates = 0
    unreadable_money = 0

    for record in records:
        stage = _text(record['Stage'])
        if stage is None or not any(level in stage.lower() for level in STAGE_LEVELS):
            continue

        values = []
        for source, column in SOURCE_TO_STAGING:
            raw = record[source]
            if column == 'Initiative ID':
                value = _whole_number(raw)
            elif column == 'Stage':
                value = STAGE_MAP.get(stage, stage)
            elif column == 'Weekly Status' and not has_weekly_status:
                value = 'Active'
            elif column in DATE_COLUMNS:
                value = _to_date(raw)
                if value is None and not _is_blank(raw):
                    unreadable_dates += 1
            elif column in MONEY_COLUMNS:
                value = _to_money(raw)
                if value is None:
                    unreadable_money += 1
                    value = Decimal(0)
            else:
                value = _text(raw)
            values.append(value)
        rows.append(tuple(values))

    warnings = []
    if not has_weekly_status:
        warnings.append("No 'Weekly status' column was found; every initiative was set to Active.")
    if unreadable_dates:
        warnings.append(f'{unreadable_dates} stage date value(s) could not be read and were left blank.')
    if unreadable_money:
        warnings.append(f'{unreadable_money} benefit value(s) were not numbers and were loaded as $0.')
    return rows, warnings


def _check_rows(rows):
    """Reject rows the staging table would refuse, listing every problem at once."""
    id_index = STAGING_COLUMNS.index('Initiative ID')
    name_index = STAGING_COLUMNS.index('Initiative Name')
    problems = []

    unnamed = [row[name_index] or '(no name)' for row in rows if row[id_index] is None]
    if unnamed:
        problems.append(f'Missing or invalid Initiative ID (#): {_preview(unnamed)}')

    ids = [row[id_index] for row in rows if row[id_index] is not None]
    out_of_range = [str(value) for value in ids if not INT32_RANGE[0] <= value <= INT32_RANGE[1]]
    if out_of_range:
        problems.append(f'Initiative IDs too large for the database: {_preview(out_of_range)}')
    duplicates = sorted(value for value, count in Counter(ids).items() if count > 1)
    if duplicates:
        problems.append(f'Duplicate Initiative IDs: {_preview([str(value) for value in duplicates])}')

    for column in REQUIRED_TEXT_COLUMNS:
        index = STAGING_COLUMNS.index(column)
        blank = [str(row[id_index]) for row in rows if row[index] is None]
        if blank:
            problems.append(f'{column} is blank for initiatives: {_preview(blank)}')

    for column, limit in TEXT_LIMITS.items():
        index = STAGING_COLUMNS.index(column)
        too_long = [str(row[id_index]) for row in rows if row[index] is not None and len(row[index]) > limit]
        if too_long:
            problems.append(f'{column} is longer than {limit} characters for initiatives: {_preview(too_long)}')

    if problems:
        raise WaveRefreshError('The export has rows the dashboard tables cannot accept.', details=problems)


def _check_dates(created_date, today, max_age_days):
    if created_date > today:
        raise WaveRefreshError(
            f'Export creation date {created_date:%m/%d/%Y} is in the future. Check that this is the right file.'
        )
    age = (today - created_date).days
    if age > max_age_days:
        raise WaveRefreshError(
            f'Export creation date {created_date:%m/%d/%Y} is {age} days old (limit {max_age_days}). '
            'Download the latest export from Wave.'
        )


def check_not_older(export, previous_stamp):
    """Never replace the dashboard data with an export older than the current load."""
    if previous_stamp and export.workbook_date < previous_stamp:
        raise WaveRefreshError(
            f'This export ({export.workbook_date:%m/%d/%Y}) is older than the data already loaded '
            f'({previous_stamp:%m/%d/%Y}). Upload the newer export.'
        )


def _core_created(package):
    """The dcterms:created property, if the file has a readable one."""
    try:
        core = ET.fromstring(package.read('docProps/core.xml'))
        created = datetime.fromisoformat(core.findtext('{http://purl.org/dc/terms/}created', '').strip())
    except (KeyError, ET.ParseError, ValueError):
        return None
    return created if created.tzinfo else created.replace(tzinfo=timezone.utc)


def _newest_zip_entry(package):
    """The latest zip entry time, which is UTC in Wave's own downloads. 1980 is a placeholder."""
    stamps = [info.date_time for info in package.infolist() if info.date_time[0] > 1980]
    try:
        return datetime(*max(stamps), tzinfo=timezone.utc) if stamps else None
    except ValueError:
        return None


def native_created_at(content):
    """
    When the export was really created, in Eastern time, read from inside the file.

    Must match native_created_at in fileprocess.ipynb. Excel-saved exports carry
    the dcterms:created property. Wave's own download has no such property, so
    the time it built the file comes from its zip entries. The filename is only
    a label and is never read. openpyxl's workbook.properties.created must not
    be used: it substitutes the current time when the property is missing.
    """
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        created = _core_created(package) or _newest_zip_entry(package)
    return created.astimezone(now_eastern().tzinfo) if created else None


def _is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _text(value):
    if value is None:
        return None
    return str(value).strip()


def _whole_number(value):
    if isinstance(value, bool) or _is_blank(value):
        return None
    if isinstance(value, int):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if math.isfinite(number) and number.is_integer() else None


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return from_excel(value).date()
        except (ValueError, OverflowError, AttributeError):
            return None
    if isinstance(value, str) and value.strip():
        try:
            return date_parser.parse(value.strip()).date()
        except (ValueError, OverflowError):
            return None
    return None


def _to_money(value):
    """Return dollars (export is in $M); blank is $0 and non-numeric text is None."""
    if _is_blank(value):
        return Decimal(0)
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return Decimal(0)
    if math.isinf(number):
        raise WaveRefreshError('The export contains an infinite benefit amount.')
    return (Decimal(str(number)) * MONEY_MULTIPLIER).quantize(MONEY_SCALE, ROUND_HALF_UP)


def _preview(values, limit=8):
    shown = ', '.join(values[:limit])
    return f'{shown} (+{len(values) - limit} more)' if len(values) > limit else shown


def _iso(value):
    return value.isoformat() if value else None


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

def archive_export(folder, export, timestamp):
    """Keep the exact bytes as <upload time>_created_<native creation time>_<name>, both Eastern."""
    os.makedirs(folder, exist_ok=True)
    safe_name = secure_filename(export.file_name) or 'wave_export.xlsx'
    path = os.path.join(folder, f'{timestamp:%Y%m%d_%H%M%S_%f}_created_{export.created_at:%Y%m%d_%H%M%S}_{safe_name}')
    with open(path, 'xb') as handle:
        handle.write(export.content)
    with open(path, 'rb') as handle:
        if hashlib.sha256(handle.read()).hexdigest() != export.sha256:
            raise OSError('Archived copy does not match the upload.')
    return path


# ---------------------------------------------------------------------------
# Power BI refresh schedule
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PowerBiSchedule:
    """
    Scheduled Power BI dataset refreshes (Eastern), used to estimate when a load shows.

    Refreshes run every `interval` from `first_refresh` to `last_refresh` each day.
    A load must finish `lead` before a refresh to be picked up by it, and the
    report shows the new numbers `publish_delay` after that refresh starts.
    """
    first_refresh: time
    last_refresh: time
    interval: timedelta
    publish_delay: timedelta
    lead: timedelta

    @classmethod
    def from_config(cls, config):
        schedule = cls(
            first_refresh=_clock(config.get('WAVE_PBI_FIRST_REFRESH', '09:00')),
            last_refresh=_clock(config.get('WAVE_PBI_LAST_REFRESH', '17:00')),
            interval=timedelta(minutes=int(config.get('WAVE_PBI_REFRESH_INTERVAL_MINUTES', 60))),
            publish_delay=timedelta(minutes=int(config.get('WAVE_PBI_PUBLISH_MINUTES', 15))),
            lead=timedelta(minutes=int(config.get('WAVE_PBI_LEAD_MINUTES', 15))),
        )
        if (schedule.interval <= timedelta(0) or schedule.first_refresh > schedule.last_refresh
                or schedule.publish_delay < timedelta(0) or schedule.lead < timedelta(0)):
            raise ValueError('Invalid WAVE_PBI_* refresh schedule settings.')
        return schedule

    def estimate(self, finished_at):
        """Return the refresh that picks up a load finished at `finished_at`, and when it shows."""
        eastern = now_eastern().tzinfo
        if finished_at.tzinfo is None:  # Stored event times are naive Eastern.
            finished_at = finished_at.replace(tzinfo=eastern)
        finished_at = finished_at.astimezone(eastern)

        earliest = finished_at + self.lead
        day = earliest.date()
        while True:
            first = datetime.combine(day, self.first_refresh, tzinfo=eastern)
            last = datetime.combine(day, self.last_refresh, tzinfo=eastern)
            if earliest <= last:
                steps = max(0, -((first - earliest) // self.interval))  # ceiling division
                refresh_at = first + steps * self.interval
                if refresh_at <= last:
                    break
            day += timedelta(days=1)

        return {
            'finished_at': finished_at.isoformat(),
            'refresh_at': refresh_at.isoformat(),
            'visible_at': (refresh_at + self.publish_delay).isoformat(),
        }

    def describe(self):
        every = 'hour' if self.interval == timedelta(hours=1) else _span(self.interval)
        return (
            f'Power BI refreshes every {every} from {_clock_text(self.first_refresh)} '
            f'to {_clock_text(self.last_refresh)} ET and takes about {_span(self.publish_delay)} to publish. '
            f'A load must finish {_span(self.lead)} before a refresh to be included.'
        )


def _clock(value):
    try:
        return datetime.strptime(str(value).strip(), '%H:%M').time()
    except ValueError as exc:
        raise ValueError(f'Power BI refresh times must be 24-hour HH:MM, got {value!r}.') from exc


def _clock_text(value):
    return value.strftime('%I:%M %p').lstrip('0')


def _span(delta):
    minutes = int(delta.total_seconds() // 60)
    if minutes and minutes % 60 == 0:
        hours = minutes // 60
        return f'{hours} hour' if hours == 1 else f'{hours} hours'
    return f'{minutes} minutes'


# ---------------------------------------------------------------------------
# PBI database
# ---------------------------------------------------------------------------

def target_label(config):
    return f"{config.get('WAVE_DB_NAME')} on {config.get('WAVE_DB_SERVER')}"


def _connection_string(config):
    driver = config.get('WAVE_DB_DRIVER') or config.get('DB_DRIVER') or 'ODBC Driver 17 for SQL Server'
    server = config.get('WAVE_DB_SERVER')
    database = config.get('WAVE_DB_NAME')
    trusted = str(config.get('WAVE_DB_TRUSTED_CONNECTION') or 'yes').lower()
    if trusted == 'yes':
        return 'Driver={{{}}};Server={};Database={};Trusted_Connection=yes;'.format(driver, server, database)
    return 'Driver={{{}}};Server={};Database={};UID={};PWD={};'.format(
        driver, server, database, config.get('WAVE_DB_USER') or '', config.get('WAVE_DB_PASSWORD') or '',
    )


def connect(config):
    """Open an autocommit connection; refreshes manage their own explicit transaction."""
    connection = pyodbc.connect(
        _connection_string(config),
        timeout=int(config.get('WAVE_DB_TIMEOUT', 8) or 8),
        autocommit=True,
    )
    connection.timeout = QUERY_TIMEOUT_SECONDS
    return connection


def read_savings(cursor, year):
    """Dashboard savings by channel for one realization year (vw_MainSavings)."""
    return [
        {'channel': str(channel), 'total_savings': Decimal(total or 0)}
        for channel, total in cursor.execute(_SAVINGS_SQL, year).fetchall()
        if channel is not None
    ]


def _staging_snapshot(cursor):
    stamp, count = cursor.execute(_STAGING_SNAPSHOT_SQL).fetchone()
    return (stamp.date() if isinstance(stamp, datetime) else stamp), int(count or 0)


def current_totals(config, year):
    """Read-only: current dashboard totals and the last staging load."""
    with closing(connect(config)) as connection:
        cursor = connection.cursor()
        savings = read_savings(cursor, year)
        stamp, rows = _staging_snapshot(cursor)
    return {
        'realization_year': year,
        'savings': serialize_savings(savings),
        'staging_date': _iso(stamp),
        'staging_rows': rows,
        'queried_at': now_eastern().isoformat(),
    }


def compare_with_database(config, export):
    """Read-only preview: apply the date guard and report the current load."""
    with closing(connect(config)) as connection:
        stamp, rows = _staging_snapshot(connection.cursor())
    check_not_older(export, stamp)
    return {'previous_staging_date': _iso(stamp), 'previous_staging_rows': rows}


def apply_refresh(config, export, year):
    """
    Replace staging, run the merge and read totals in one transaction.

    Any failure (including an empty savings result) rolls everything back.
    Staging is cleared with DELETE rather than TRUNCATE so the service
    account needs no ALTER permission on the table.
    """
    with closing(connect(config)) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute('SET NOCOUNT ON; SET XACT_ABORT ON; SET LOCK_TIMEOUT 30000; BEGIN TRANSACTION;')
            lock_result = cursor.execute(_APPLOCK_SQL).fetchval()
            if lock_result is None or lock_result < 0:
                raise WaveRefreshError('Another Wave refresh is running. Try again in a minute.', status_code=409)

            previous_stamp, previous_rows = _staging_snapshot(cursor)
            check_not_older(export, previous_stamp)
            existing_columns = {row[0] for row in cursor.execute(_STAGING_COLUMNS_SQL).fetchall()}
            if existing_columns != set(STAGING_COLUMNS):
                raise WaveRefreshError(
                    'The PBI staging table no longer matches this upload. Contact the procurement data team.',
                    status_code=500,
                )

            before = read_savings(cursor, year)
            cursor.execute(f'DELETE FROM {_STAGING_TABLE};')
            cursor.executemany(_INSERT_SQL, export.staging_rows())
            loaded = cursor.execute(f'SELECT COUNT_BIG(*) FROM {_STAGING_TABLE}').fetchval()
            if loaded != len(export.rows):
                raise WaveRefreshError('Staging row count did not match the export. Nothing was changed.', status_code=500)

            cursor.execute('EXEC [SCSSaving].[sp_MergeInitiativesFromStage];')
            while cursor.nextset():
                pass

            after = read_savings(cursor, year)
            if not after:
                raise WaveRefreshError(
                    f'The merge left no included savings for {year}. Nothing was changed.',
                    status_code=500,
                )
            cursor.execute('COMMIT TRANSACTION;')
        except BaseException:
            try:
                cursor.execute('IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;')
            except pyodbc.Error:
                pass  # The connection is closed below, which also rolls back.
            raise

    return {
        'previous_staging_date': _iso(previous_stamp),
        'previous_staging_rows': previous_rows,
        'savings': compare_savings(before, after),
        'queried_at': now_eastern().isoformat(),
    }


def serialize_savings(savings):
    return [{'channel': row['channel'], 'total_savings': str(row['total_savings'])} for row in savings]


def compare_savings(before, after):
    """Per-channel before/after/change, including channels present on only one side."""
    before_map = {row['channel']: row['total_savings'] for row in before}
    after_map = {row['channel']: row['total_savings'] for row in after}
    channels = sorted(set(before_map) | set(after_map))
    return [
        {
            'channel': channel,
            'before': str(before_map.get(channel, Decimal(0))),
            'after': str(after_map.get(channel, Decimal(0))),
            'change': str(after_map.get(channel, Decimal(0)) - before_map.get(channel, Decimal(0))),
        }
        for channel in channels
    ]
