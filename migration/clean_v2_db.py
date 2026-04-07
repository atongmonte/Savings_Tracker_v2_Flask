"""
Wipe all savingstracker_v2 tables and reset identity counters to 1.
Uses pure pyodbc + TRUNCATE TABLE (auto-resets identity) with FK constraints
temporarily disabled so order doesn't matter.
Initiative IDs are NOT reset here — the migration script inserts them
with their original 88000001+ values via IDENTITY_INSERT.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

import pyodbc

server = os.getenv("DB_SERVER", r"YNBBSTVWP02\PROCDATASRVPROD")
dest_db = os.getenv("DB_NAME", "savingstracker_v2")
driver  = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

conn = pyodbc.connect(
    f"Driver={{{driver}}};Server={server};Database={dest_db};Trusted_Connection=yes;",
    autocommit=True   # DDL (TRUNCATE) needs autocommit
)
cur = conn.cursor()

# Child tables: nothing references them → safe to TRUNCATE (resets identity to 1)
TRUNCATE_TABLES = [
    "facility_allocations",
    "file_tracking",
    "cost_savings",
    "cost_avoidance",
    "rebates",
]

# Parent tables: other tables have FK constraints pointing at them.
# SQL Server blocks TRUNCATE on referenced tables even when empty.
# Use DELETE (respects FK order) + DBCC CHECKIDENT to reset identity.
# Order matters: delete deepest child first so FK checks pass.
#   initiatives   <- referenced by the 5 child tables above (already truncated)
#   users         <- referenced by initiatives (deleted next) and file_tracking (truncated)
#   facilities    <- referenced by facility_allocations (truncated)
#   user_roles    <- referenced by users (deleted)
DELETE_RESEED_TABLES = [
    "initiatives",
    "users",
    "facilities",
    "user_roles",
]

print(f"Cleaning {dest_db} on {server} ...")

# 1. TRUNCATE child tables — auto-resets identity to 1
for tbl in TRUNCATE_TABLES:
    cur.execute(f"TRUNCATE TABLE {tbl}")
    print(f"  Truncated   {tbl:<30} (identity → 1)")

# 2. DELETE parent tables in FK-safe order, then reseed identity
for tbl in DELETE_RESEED_TABLES:
    cur.execute(f"DELETE FROM {tbl}")
    cur.execute(f"DBCC CHECKIDENT('{tbl}', RESEED, 0)")
    print(f"  Deleted     {tbl:<30} (identity → 1)")

conn.close()
print("Done – v2 DB is clean. All identity counters reset to 1.")
