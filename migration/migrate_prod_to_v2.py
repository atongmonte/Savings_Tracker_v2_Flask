"""
Migration script: savingstracker_backup (prod schema) --> savingstracker_v2
=======================================================================
Approach: two raw pyodbc connections, bulk executemany() inserts.
No Flask/SQLAlchemy ORM - runs in seconds instead of minutes.

This script performs a FULL refresh each run:
    A) wipes all destination data in savingstracker_v2
    B) resets identity seeds to 1 for all migrated tables EXCEPT initiatives.id
    C) reloads data from savingstracker_backup

  SOURCE (READ-ONLY): [savingstracker_backup].[prod].*
  DEST   (write):     [savingstracker_v2].dbo.*

Tables migrated (in order):
  1. user_roles        - 4 standard roles
  2. users             - prod.USERS
  3. facilities        - 8 hard-coded facility codes
  4. initiatives       - prod.INITIATIVE_MASTER  (original IDs preserved)
  5. cost_savings      - prod.INITIATIVE_COST_SAVINGS
  6. cost_avoidance    - prod.INITIATIVE_COST_AVOIDANCE
  7. rebates           - prod.INITIATIVE_REBATES
  8. facility_allocations - from ALLOC columns on each detail table
  9. file_tracking     - prod.FILE_TRACKING_TABLE

Usage
-----
    # Dry-run (shows what would be cleaned/migrated; no writes):
    python migration/migrate_prod_to_v2.py --dry-run

    # Live full-refresh migration:
    python migration/migrate_prod_to_v2.py
"""

import argparse
import logging
import os
import sys
from datetime import datetime, date

# ---------------------------------------------------------------------------
# Path setup + .env loading
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT   = os.path.dirname(_SCRIPT_DIR)
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

try:
    from dotenv import load_dotenv
    _env_path = os.path.join(_APP_ROOT, ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
        print(f"[INFO] Loaded environment from {_env_path}")
except ImportError:
    pass

import pyodbc

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(_SCRIPT_DIR, "migration.log"), mode="a", encoding="utf-8"
        ),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FACILITY_MAP = {
    "MMC":   "Montefiore Medical Center",
    "BURKE": "Burke Rehabilitation Hospital",
    "AECOM": "Albert Einstein College of Medicine",
    "MMVO":  "Montefiore Medical Center - Wakefield",
    "MSSO":  "Mount Sinai South Nassau",
    "NYACK": "Nyack Hospital",
    "SLCH":  "St. Luke's Cornwall Hospital",
    "WPH":   "White Plains Hospital",
}

ALLOC_COLS = ["MMC_ALLOC", "BURKE_ALLOC", "AECOM_ALLOC", "MMVO_ALLOC",
              "MSSO_ALLOC", "NYACK_ALLOC", "SLCH_ALLOC", "WPH_ALLOC"]

STATUS_MAP = {
    "approved":      "Approved",
    "rejected":      "Rejected",
    "pending":       "Pending Review",
    "pending review":"Pending Review",
    "under review":  "Pending Review",
    "closed":        "Approved",
}

TYPE_MAP = {
    "cost savings":   "Cost Savings",
    "rebate":         "Rebate",
    "rebates":        "Rebate",
    "cost avoidance": "Cost Avoidance",
}

NOW = datetime.utcnow()

DEST_DELETE_ORDER = [
    "audit_logs",
    "file_tracking",
    "facility_allocations",
    "cost_savings",
    "cost_avoidance",
    "rebates",
    "initiatives",
    "users",
    "facilities",
    "user_roles",
]

RESEED_TO_ONE_TABLES = [
    "audit_logs",
    "file_tracking",
    "facility_allocations",
    "cost_savings",
    "cost_avoidance",
    "rebates",
    "users",
    "facilities",
    "user_roles",
]

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _conn_str(server, db_name, driver, trusted, user, pw):
    if trusted.lower() == "yes":
        return f"Driver={{{driver}}};Server={server};Database={db_name};Trusted_Connection=yes;"
    return f"Driver={{{driver}}};Server={server};Database={db_name};UID={user};PWD={pw};"


def get_connections(src_db_override=None):
    server  = os.getenv("DB_SERVER",  r"YNBBSTVWP02\PROCDATASRVPROD")
    dest_db = os.getenv("DB_NAME",    "savingstracker_v2")
    src_db  = src_db_override or os.getenv("SRC_DB_NAME", "savingstracker_backup")
    driver  = os.getenv("DB_DRIVER",  "ODBC Driver 17 for SQL Server")
    trusted = os.getenv("DB_TRUSTED_CONNECTION", "yes")
    user    = os.getenv("DB_USER",    "")
    pw      = os.getenv("DB_PASSWORD","")

    log.info("SOURCE : Server=%s  DB=%s", server, src_db)
    log.info("DEST   : Server=%s  DB=%s", server, dest_db)

    src  = pyodbc.connect(_conn_str(server, src_db,  driver, trusted, user, pw), autocommit=False)
    dest = pyodbc.connect(_conn_str(server, dest_db, driver, trusted, user, pw), autocommit=False)
    src.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
    return src, dest


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def fetch(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _s(v, maxlen=None):
    """Clean string."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return s[:maxlen] if maxlen else s


def _dt(v):
    """Clean datetime - SQL Server-safe datetime or None."""
    if v is None:
        return None
    if isinstance(v, datetime):
        dt = v
    elif isinstance(v, date):
        dt = datetime(v.year, v.month, v.day)
    else:
        try:
            dt = datetime.fromisoformat(str(v))
        except Exception:
            return None
    if dt.year < 1753 or dt.year > 9999:
        return None
    return dt


def _d(v):
    """Clean date."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v), "%Y-%m-%d").date()
    except Exception:
        return None


def _f(v):
    """Clean float/money."""
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _b(v):
    """Clean bool."""
    if v is None:
        return False
    return str(v).strip().upper() in ("Y", "YES", "1", "TRUE")


def dest_execmany(dest, sql, rows):
    if not rows:
        return
    cur = dest.cursor()
    cur.fast_executemany = True
    cur.executemany(sql, rows)


def _table_exists(conn, table_name):
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=?",
        table_name,
    )
    return cur.fetchone() is not None


def _table_count(conn, table_name):
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT_BIG(1) FROM dbo.{table_name}")
    row = cur.fetchone()
    return int(row[0]) if row else 0


def reset_destination_db(dest, dry_run):
    """
    Wipe all v2 data and reset identities to 1 for all migrated tables,
    except initiatives.id which is intentionally NOT reseeded.
    """
    existing_delete_tables = [t for t in DEST_DELETE_ORDER if _table_exists(dest, t)]
    existing_reseed_tables = [t for t in RESEED_TO_ONE_TABLES if _table_exists(dest, t)]

    log.info("  Tables to clear: %s", ", ".join(existing_delete_tables) or "(none)")
    for tbl in existing_delete_tables:
        log.info("    %s rows before cleanup: %d", tbl, _table_count(dest, tbl))

    if dry_run:
        log.info("  [DRY-RUN] Destination cleanup skipped (no data changed).")
        log.info("  [DRY-RUN] Would reseed to 1: %s", ", ".join(existing_reseed_tables) or "(none)")
        log.info("  [DRY-RUN] Would NOT reseed: initiatives")
        return

    try:
        cur = dest.cursor()
        for tbl in existing_delete_tables:
            cur.execute(f"DELETE FROM dbo.{tbl}")

        # Reset identities so next insert starts at 1 (RESEED 0 => next is 1)
        for tbl in existing_reseed_tables:
            cur.execute(f"DBCC CHECKIDENT('dbo.{tbl}', RESEED, 0)")

        # Explicitly do not reseed initiatives per migration requirement.
        dest.commit()
    except Exception:
        dest.rollback()
        raise

    for tbl in existing_delete_tables:
        log.info("    %s rows after cleanup: %d", tbl, _table_count(dest, tbl))


# ---------------------------------------------------------------------------
# Step 1 - User Roles
# ---------------------------------------------------------------------------
ROLES = [
    ("Admin",    "Full access - manage users, approve everything",
     1,1,1,1,1,1,1,1,1),
    ("Reviewer", "Can review and approve initiatives",
     1,1,0,1,0,1,1,1,0),
    ("User",     "Standard user - create and manage own initiatives",
     1,1,0,1,0,0,0,1,0),
    ("ReadOnly", "View and export only",
     0,0,0,0,0,0,0,1,0),
]


def migrate_user_roles(src, dest, dry_run):
    existing = {r["name"]: r["id"]
                for r in fetch(dest, "SELECT id, name FROM user_roles")}
    role_map = dict(existing)

    insert_sql = (
        "INSERT INTO user_roles"
        "    (name, description, can_create, can_edit_own, can_edit_all,"
        "     can_delete_own, can_delete_all, can_review, can_approve,"
        "     can_export, can_manage_users, created_at, updated_at)"
        " OUTPUT inserted.id"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
    )
    created = 0
    for (name, desc, cc, ceo, cea, cdo, cda, cr, ca, ce, cmu) in ROLES:
        if name in existing:
            log.info("  Role '%s' already exists (id=%s)", name, existing[name])
            continue
        if not dry_run:
            cur = dest.cursor()
            cur.execute(insert_sql, (name, desc, cc, ceo, cea, cdo, cda, cr, ca, ce, cmu, NOW, NOW))
            new_id = cur.fetchone()[0]
            role_map[name] = new_id
            log.info("  Created role '%s' id=%s", name, new_id)
        else:
            log.info("  [DRY-RUN] Would create role '%s'", name)
        created += 1

    if not dry_run and created:
        dest.commit()

    log.info("  User Roles: %d created, %d already existed", created, len(existing))
    return role_map


# ---------------------------------------------------------------------------
# Step 2 - Users
# ---------------------------------------------------------------------------

def migrate_users(src, dest, role_map, dry_run):
    src_rows = fetch(src, "SELECT * FROM prod.USERS")
    log.info("  Source users: %d", len(src_rows))

    existing_rows = fetch(dest, "SELECT id, username, full_name FROM users")
    existing_users = {r["username"].lower(): r["id"] for r in existing_rows}
    user_map = dict(existing_users)
    # Also index by full_name so InitiativeOwner (which stores full names) resolves
    for r in existing_rows:
        fn = (r["full_name"] or "").strip().lower()
        if fn and fn not in user_map:
            user_map[fn] = r["id"]

    def map_role(row):
        desc     = (_s(row.get("UserRoleDescription"), 100) or "").lower()
        is_super = (_s(row.get("isSuperUser")) or "").upper()
        if "super" in desc or is_super == "Y":
            return "Admin"
        if "reviewer" in desc or "review" in desc:
            return "Reviewer"
        return "User"

    insert_sql = (
        "INSERT INTO users"
        "    (username, full_name, email, role_id, is_active,"
        "     created_at, updated_at, last_login)"
        " OUTPUT inserted.id"
        " VALUES (?,?,?,?,?,?,?,?)"
    )

    created = skipped = 0
    for row in src_rows:
        username = _s(row.get("UserName"), 100)
        if not username:
            continue
        if username.lower() in existing_users:
            user_map[username.lower()] = existing_users[username.lower()]
            skipped += 1
            continue

        role_name = map_role(row)
        role_id   = role_map.get(role_name) or role_map.get("User")
        full_name = _s(row.get("User_FullName"), 255) or username
        email     = _s(row.get("UserEmail"), 255) or f"{username}@montefiore.org"
        is_active = int(bool(row.get("ActiveFlag", 1)))

        if not dry_run:
            try:
                cur = dest.cursor()
                cur.execute(insert_sql, (
                    username, full_name, email, role_id, is_active,
                    _dt(row.get("CreationDate")) or NOW,
                    NOW,
                    _dt(row.get("LastSeenDate")),
                ))
                new_id = cur.fetchone()[0]
                user_map[username.lower()] = new_id
                # Also map full_name so InitiativeOwner lookups resolve
                fn = full_name.strip().lower()
                if fn and fn not in user_map:
                    user_map[fn] = new_id
                created += 1
            except Exception as exc:
                dest.rollback()
                log.warning("  SKIP user '%s': %s", username, exc)
                skipped += 1
        else:
            created += 1

    # Ensure system_migration fallback user exists
    if "system_migration" not in user_map and not dry_run:
        ro_role = role_map.get("ReadOnly") or list(role_map.values())[-1]
        cur = dest.cursor()
        cur.execute(insert_sql, (
            "system_migration", "System Migration",
            "system_migration@montefiore.org", ro_role, 0,
            NOW, NOW, None,
        ))
        user_map["system_migration"] = cur.fetchone()[0]
        log.info("  Created system_migration user id=%s", user_map["system_migration"])

    if not dry_run:
        dest.commit()

    log.info("  Users: %d created, %d skipped", created, skipped)
    return user_map


# ---------------------------------------------------------------------------
# Step 3 - Facilities
# ---------------------------------------------------------------------------

def migrate_facilities(src, dest, dry_run):
    existing = {r["code"]: r["id"]
                for r in fetch(dest, "SELECT id, code FROM facilities")}
    fac_map = dict(existing)

    insert_sql = (
        "INSERT INTO facilities (code, name, is_active, created_at, updated_at)"
        " OUTPUT inserted.id VALUES (?,?,1,?,?)"
    )
    created = 0
    for idx, (code, name) in enumerate(FACILITY_MAP.items(), start=1):
        if code in existing:
            log.info("  Facility '%s' already exists id=%s", code, existing[code])
            continue
        if not dry_run:
            cur = dest.cursor()
            cur.execute(insert_sql, (code, name, NOW, NOW))
            new_id = cur.fetchone()[0]
            fac_map[code] = new_id
            log.info("  Created facility '%s' id=%s", code, new_id)
        else:
            fac_map[code] = idx
            log.info("  [DRY-RUN] Would create facility '%s'", code)
        created += 1

    if not dry_run and created:
        dest.commit()

    log.info("  Facilities: %d created, %d already existed", created, len(existing))
    return fac_map


# ---------------------------------------------------------------------------
# Step 4 - Initiatives  (preserve original IDs with IDENTITY_INSERT)
# ---------------------------------------------------------------------------

def migrate_initiatives(src, dest, user_map, dry_run):
    src_rows = fetch(src, "SELECT * FROM prod.INITIATIVE_MASTER ORDER BY InitiativeID")
    log.info("  Source initiatives: %d", len(src_rows))

    existing_ids = {r["id"] for r in fetch(dest, "SELECT id FROM initiatives")}

    def resolve_username(username_str):
        """Direct username lookup (case-insensitive). Used for Created_By."""
        if not username_str:
            return None
        return user_map.get(username_str.strip().lower())

    def resolve_owner(name_str):
        """Match InitiativeOwner (full name) to v2 user id via full_name or username."""
        if not name_str:
            return None
        key = name_str.strip().lower()
        # Direct match — covers both full_name and username keys
        if key in user_map:
            return user_map[key]
        # Partial fallback: substring overlap
        for k, v in user_map.items():
            if k and (k in key or key in k):
                return v
        log.warning("  [resolve_owner] No match for InitiativeOwner=%r", name_str)
        return None

    # ReviewedBy has exactly 4 known values in the source:
    #   'Sean Farrell', 'seafarrell' -> username seafarrell
    #   'Joe Wilson'                 -> username joawilson
    #   NULL / ''                    -> None
    REVIEWER_MAP = {
        "sean farrell": "seafarrell",
        "seafarrell":   "seafarrell",
        "joe wilson":   "joawilson",
    }

    def resolve_reviewer(val):
        if not val or not val.strip():
            return None
        key = val.strip().lower()
        username = REVIEWER_MAP.get(key)
        if username:
            return user_map.get(username)
        # fallback: try direct username lookup
        return user_map.get(key)

    fallback_uid = (user_map.get("system_migration")
                    or (list(user_map.values())[0] if user_map else None))

    insert_sql = (
        "INSERT INTO initiatives"
        "    (id, initiative_type, description, wave_id, status,"
        "     owner_id, created_by_id, reviewed_by_id,"
        "     review_comments, review_date,"
        "     is_deleted, deleted_at, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    )

    rows_to_insert = []
    old_to_new_id  = {}
    skipped = 0

    for row in src_rows:
        old_id = row["InitiativeID"]
        if old_id in existing_ids:
            old_to_new_id[old_id] = old_id
            skipped += 1
            continue

        raw_type  = _s(row.get("Initiative_Type"), 50) or ""
        init_type = TYPE_MAP.get(raw_type.lower(), raw_type) or "Cost Savings"
        raw_stat  = _s(row.get("Status"), 100) or ""
        status    = STATUS_MAP.get(raw_stat.lower(), "Pending Review")
        owner_uid    = resolve_owner(row.get("InitiativeOwner")) or fallback_uid
        creator_uid  = resolve_username(row.get("Created_By")) or owner_uid or fallback_uid
        reviewer_uid = resolve_reviewer(row.get("ReviewedBy"))
        is_del       = int(_b(row.get("IsDeleted")))
        created_at   = _dt(row.get("CreateTime")) or NOW
        updated_at   = _dt(row.get("LastUpdateTime")) or NOW
        deleted_at   = updated_at if is_del else None

        rows_to_insert.append((
            old_id, init_type,
            _s(row.get("Initiative_Desc")),
            _s(row.get("Wave_ID"), 50),
            status,
            owner_uid, creator_uid, reviewer_uid,
            _s(row.get("LastReviewComments")),
            _dt(row.get("LastReviewStatusChangeTime")),
            is_del, deleted_at, created_at, updated_at,
        ))
        old_to_new_id[old_id] = old_id

    log.info("  Initiatives to insert: %d, skipped: %d", len(rows_to_insert), skipped)

    if not dry_run and rows_to_insert:
        dest.execute("SET IDENTITY_INSERT initiatives ON")
        dest_execmany(dest, insert_sql, rows_to_insert)
        dest.execute("SET IDENTITY_INSERT initiatives OFF")
        dest.commit()
        # Reseed identity so future auto-inserts do not collide
        dest.execute(
            "DECLARE @m INT=(SELECT ISNULL(MAX(id),0) FROM initiatives);"
            "DBCC CHECKIDENT('initiatives',RESEED,@m);"
        )
        dest.commit()

    log.info("  Initiatives: %d created, %d skipped", len(rows_to_insert), skipped)
    return old_to_new_id


# ---------------------------------------------------------------------------
# Helper: build allocation rows from a detail table row
# ---------------------------------------------------------------------------

def _alloc_rows(initiative_id, row, fac_map):
    result = []
    for col in ALLOC_COLS:
        code   = col.replace("_ALLOC", "")
        fac_id = fac_map.get(code)
        if fac_id is None:
            continue
        amount = _f(row.get(col))
        if amount is None or amount < 0:
            amount = 0.0  # clamp NULL/negative to 0 (satisfies chk_allocation_amount >= 0)
        result.append((initiative_id, fac_id, amount))
    return result


# ---------------------------------------------------------------------------
# Step 5 - Cost Savings + allocations
# ---------------------------------------------------------------------------

def migrate_cost_savings(src, dest, old_to_new_id, fac_map, dry_run):
    src_rows = fetch(src, "SELECT * FROM prod.INITIATIVE_COST_SAVINGS")
    log.info("  Source cost_savings: %d", len(src_rows))

    cs_sql = (
        "INSERT INTO cost_savings"
        "    (initiative_id, savings_type, contract_number,"
        "     contract_category, contract_source, gpo_tier, vendor_name,"
        "     start_date, end_date, baseline_spend, expected_spend,"
        "     total_savings_amount, annual_savings_amount, is_fixed_cost,"
        "     created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    )
    alloc_sql = (
        "INSERT INTO facility_allocations"
        "    (initiative_id, facility_id, allocation_amount,"
        "     allocation_percentage, created_at, updated_at)"
        " VALUES (?,?,?,NULL,?,?)"
    )

    cs_rows     = []
    alloc_rows  = []
    seen_allocs = set()
    skipped = 0

    for row in src_rows:
        old_id = row["InitiativeID"]
        new_id = old_to_new_id.get(old_id)
        if new_id is None:
            skipped += 1
            continue

        cs_rows.append((
            new_id,
            _s(row.get("Cost_Savings_Type"), 100),
            _s(row.get("Contract_Number"), 100),
            _s(row.get("Contract_Category"), 100),
            _s(row.get("Contract_Source"), 100),
            _s(row.get("GPO_Tier"), 500),
            _s(row.get("Vendor_Name"), 255),
            _d(row.get("Cost_Savings_Start_Date")),
            _d(row.get("Cost_Savings_End_Date")),
            _f(row.get("Cost_Savings_Baseline_Spend")),
            _f(row.get("Cost_Savings_Expected_Spend")),
            _f(row.get("Cost_Savings_Amount")),
            _f(row.get("Annual_Cost_Savings_Amount")),
            int(_b(row.get("fixed_Cost_Flag"))),
            NOW, NOW,
        ))

        for (init_id, fac_id, amount) in _alloc_rows(new_id, row, fac_map):
            key = (init_id, fac_id)
            if key not in seen_allocs:
                seen_allocs.add(key)
                alloc_rows.append((init_id, fac_id, amount, NOW, NOW))

    if not dry_run:
        dest_execmany(dest, cs_sql, cs_rows)
        dest_execmany(dest, alloc_sql, alloc_rows)
        dest.commit()

    log.info("  Cost Savings: %d created, %d skipped | Allocations: %d",
             len(cs_rows), skipped, len(alloc_rows))
    return seen_allocs


# ---------------------------------------------------------------------------
# Step 6 - Cost Avoidance + allocations
# ---------------------------------------------------------------------------

def migrate_cost_avoidance(src, dest, old_to_new_id, fac_map, dry_run, seen_allocs):
    src_rows = fetch(src, "SELECT * FROM prod.INITIATIVE_COST_AVOIDANCE")
    log.info("  Source cost_avoidance: %d", len(src_rows))

    ca_sql = (
        "INSERT INTO cost_avoidance"
        "    (initiative_id, avoidance_type, strata_project_id,"
        "     contract_number, contract_category, contract_source,"
        "     vendor_name, po_number, po_date, avoidance_date,"
        "     original_quote, new_quote, avoidance_amount,"
        "     created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    )
    alloc_sql = (
        "INSERT INTO facility_allocations"
        "    (initiative_id, facility_id, allocation_amount,"
        "     allocation_percentage, created_at, updated_at)"
        " VALUES (?,?,?,NULL,?,?)"
    )

    ca_rows    = []
    alloc_rows = []
    skipped = 0

    for row in src_rows:
        old_id = row["InitiativeID"]
        new_id = old_to_new_id.get(old_id)
        if new_id is None:
            skipped += 1
            continue

        ca_rows.append((
            new_id,
            _s(row.get("Cost_Avoidance_Type"), 100),
            _s(row.get("Strata_Proj_ID"), 100),
            _s(row.get("Contract_Number"), 100),
            _s(row.get("Contract_Category"), 100),
            _s(row.get("Contract_Source"), 100),
            _s(row.get("Vendor_Name"), 255),
            _s(row.get("PO_num"), 100),
            _d(row.get("PO_Date")),
            _d(row.get("Cost_Avoidance_Date")),
            _f(row.get("Original_Quote")),
            _f(row.get("New_Quote")),
            _f(row.get("Cost_Avoidance_Amount")),
            NOW, NOW,
        ))

        for (init_id, fac_id, amount) in _alloc_rows(new_id, row, fac_map):
            key = (init_id, fac_id)
            if key not in seen_allocs:
                seen_allocs.add(key)
                alloc_rows.append((init_id, fac_id, amount, NOW, NOW))

    if not dry_run:
        dest_execmany(dest, ca_sql, ca_rows)
        dest_execmany(dest, alloc_sql, alloc_rows)
        dest.commit()

    log.info("  Cost Avoidance: %d created, %d skipped | Allocations: %d",
             len(ca_rows), skipped, len(alloc_rows))


# ---------------------------------------------------------------------------
# Step 7 - Rebates + allocations
# ---------------------------------------------------------------------------

def migrate_rebates(src, dest, old_to_new_id, fac_map, dry_run, seen_allocs):
    src_rows = fetch(src, "SELECT * FROM prod.INITIATIVE_REBATES")
    log.info("  Source rebates: %d", len(src_rows))

    r_sql = (
        "INSERT INTO rebates"
        "    (initiative_id, rebate_type, contract_number,"
        "     contract_category, contract_source, gpo_tier, vendor_name,"
        "     rebate_check_date, check_number, rebate_amount,"
        "     rebate_payment_type, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
    )
    alloc_sql = (
        "INSERT INTO facility_allocations"
        "    (initiative_id, facility_id, allocation_amount,"
        "     allocation_percentage, created_at, updated_at)"
        " VALUES (?,?,?,NULL,?,?)"
    )

    r_rows     = []
    alloc_rows = []
    skipped = 0

    for row in src_rows:
        old_id = row["InitiativeID"]
        new_id = old_to_new_id.get(old_id)
        if new_id is None:
            skipped += 1
            continue

        r_rows.append((
            new_id,
            _s(row.get("Rebates_Type"), 100),
            _s(row.get("Contract_Number"), 100),
            _s(row.get("Contract_Category"), 100),
            _s(row.get("Contract_Source"), 100),
            _s(row.get("GPO_Tier"), 500),
            _s(row.get("Vendor_Name"), 255),
            _d(row.get("Rebate_Check_Date")),
            _s(row.get("Check_Number"), 500),
            _f(row.get("Rebate_amount")),
            _s(row.get("Rebate_Payment_Type"), 50),
            NOW, NOW,
        ))

        for (init_id, fac_id, amount) in _alloc_rows(new_id, row, fac_map):
            key = (init_id, fac_id)
            if key not in seen_allocs:
                seen_allocs.add(key)
                alloc_rows.append((init_id, fac_id, amount, NOW, NOW))

    if not dry_run:
        dest_execmany(dest, r_sql, r_rows)
        dest_execmany(dest, alloc_sql, alloc_rows)
        dest.commit()

    log.info("  Rebates: %d created, %d skipped | Allocations: %d",
             len(r_rows), skipped, len(alloc_rows))


# ---------------------------------------------------------------------------
# Step 8 - File Tracking
# ---------------------------------------------------------------------------

def migrate_file_tracking(src, dest, old_to_new_id, user_map, dry_run):
    src_rows = fetch(src, "SELECT * FROM prod.FILE_TRACKING_TABLE")
    log.info("  Source file_tracking: %d", len(src_rows))

    fallback_uid = (user_map.get("system_migration")
                    or (list(user_map.values())[0] if user_map else None))

    def resolve_user(name_str):
        if not name_str:
            return None
        key = name_str.strip().lower()
        if key in user_map:
            return user_map[key]
        for k, v in user_map.items():
            if k in key or key in k:
                return v
        return None

    insert_sql = (
        "INSERT INTO file_tracking"
        "    (initiative_id, file_name, file_path,"
        "     uploaded_by_id, upload_time,"
        "     is_deleted, deleted_at, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)"
    )

    rows_to_insert = []
    skipped = 0
    seen_files = set()

    for row in src_rows:
        old_id = row["InitiativeID"]
        new_id = old_to_new_id.get(old_id)
        if new_id is None:
            skipped += 1
            continue

        fname = _s(row.get("FILE_NAME"), 255)
        if not fname:
            skipped += 1
            continue

        key = (new_id, fname)
        if key in seen_files:
            skipped += 1
            continue
        seen_files.add(key)

        is_del   = int(_b(row.get("IS_DELETED")) or _b(row.get("IS_INIT_DELETED")))
        up_time  = _dt(row.get("UPLOAD_TIME")) or NOW
        uploader = resolve_user(row.get("UPLOADED_BY")) or fallback_uid

        rows_to_insert.append((
            new_id,
            fname,
            _s(row.get("FILE_PATH"), 500) or "",
            uploader,
            up_time,
            is_del,
            up_time if is_del else None,
            NOW, NOW,
        ))

    if not dry_run and rows_to_insert:
        dest_execmany(dest, insert_sql, rows_to_insert)
        dest.commit()

    log.info("  File Tracking: %d created, %d skipped", len(rows_to_insert), skipped)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Migrate savingstracker_backup -> savingstracker_v2"
    )
    p.add_argument("--dry-run",    action="store_true", help="Count only, no writes")
    p.add_argument("--src-db",     default=None, help="Override source database name")
    p.add_argument("--skip-users", action="store_true", help="Skip user migration")
    p.add_argument("--skip-files", action="store_true", help="Skip file tracking migration")
    return p.parse_args()


def main():
    args    = parse_args()
    dry_run = args.dry_run

    log.info("=" * 60)
    log.info("savingstracker_backup  -->  savingstracker_v2  MIGRATION")
    log.info("Mode: %s", "DRY-RUN" if dry_run else "LIVE")
    log.info("=" * 60)

    src, dest = get_connections(args.src_db)

    try:
        log.info("--- Step 0: Reset destination DB (full refresh) ---")
        reset_destination_db(dest, dry_run)

        log.info("--- Step 1: User Roles ---")
        role_map = migrate_user_roles(src, dest, dry_run)

        if not args.skip_users:
            log.info("--- Step 2: Users ---")
            user_map = migrate_users(src, dest, role_map, dry_run)
        else:
            log.info("--- Step 2: Users (SKIPPED) ---")
            user_map = {r["username"].lower(): r["id"]
                        for r in fetch(dest, "SELECT id, username FROM users")}

        log.info("--- Step 3: Facilities ---")
        fac_map = migrate_facilities(src, dest, dry_run)

        log.info("--- Step 4: Initiatives ---")
        old_to_new_id = migrate_initiatives(src, dest, user_map, dry_run)

        log.info("--- Step 5: Cost Savings + Allocations ---")
        seen_allocs = migrate_cost_savings(src, dest, old_to_new_id, fac_map, dry_run)

        log.info("--- Step 6: Cost Avoidance + Allocations ---")
        migrate_cost_avoidance(src, dest, old_to_new_id, fac_map, dry_run, seen_allocs)

        log.info("--- Step 7: Rebates + Allocations ---")
        migrate_rebates(src, dest, old_to_new_id, fac_map, dry_run, seen_allocs)

        if not args.skip_files:
            log.info("--- Step 8: File Tracking ---")
            migrate_file_tracking(src, dest, old_to_new_id, user_map, dry_run)
        else:
            log.info("--- Step 8: File Tracking (SKIPPED) ---")

    finally:
        src.close()
        dest.close()

    log.info("=" * 60)
    log.info("Migration %s", "DRY-RUN COMPLETE" if dry_run else "COMPLETE")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
