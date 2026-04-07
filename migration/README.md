# Migration: savingstracker_backup (prod) → savingstracker_v2

## What it does

`migrate_prod_to_v2.py` reads every row from the **backup** `savingstracker_backup` database
(`prod` schema) and inserts the corresponding records into the **new**
`savingstracker_v2` database via the Flask SQLAlchemy models.

Before loading, it performs a **full destination reset**:

1. Deletes all rows from migrated v2 tables
2. Reseeds identity values so next IDs start at `1` for all migrated tables
3. Keeps `initiatives.id` reseed untouched (initiative IDs are inserted from source with `IDENTITY_INSERT`)

> **Both databases live on the same SQL Server instance.**
> The source (`savingstracker_backup`) is opened in **read-only** mode with
> `READ UNCOMMITTED` isolation — no locks are placed and no data in the
> old database is ever modified.

### Tables migrated in order

| Step | Source (prod schema)          | Destination (v2)          |
|------|-------------------------------|---------------------------|
| 1    | *(none – seeded from code)*   | `user_roles`              |
| 2    | `prod.USERS`                  | `users`                   |
| 3    | *(none – seeded from code)*   | `facilities`              |
| 4    | `prod.INITIATIVE_MASTER`      | `initiatives`             |
| 5    | `prod.INITIATIVE_COST_SAVINGS`| `cost_savings` + `facility_allocations` |
| 6    | `prod.INITIATIVE_COST_AVOIDANCE` | `cost_avoidance` + `facility_allocations` |
| 7    | `prod.INITIATIVE_REBATES`     | `rebates` + `facility_allocations` |
| 8    | `prod.FILE_TRACKING_TABLE`    | `file_tracking`           |

The script is a **full-refresh migration**: each run clears destination data first,
then reloads from source.

---

## Prerequisites

1. Both SQL Server instances must be reachable from the machine running the script.
2. The `savingstracker_v2` database must already exist with the v2 schema
   applied (`python init_db.py` from the project root, or running the Flask
   migrations).
3. Python packages required (already in `requirements.txt`):
   - `pyodbc`
   - `Flask` / `Flask-SQLAlchemy`
   - `python-dotenv` *(optional – for `.env` loading)*

---

## Configuration

The script reads database settings from environment variables (same `.env` file
used by the main Flask app). **Only one server entry is needed** — source and
destination share the same SQL Server host.

```
DB_SERVER=<sql-server-host>         # used for BOTH source and destination
DB_NAME=savingstracker_v2           # destination database
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_TRUSTED_CONNECTION=yes           # "no" for SQL auth
DB_USER=                            # only needed for SQL auth
DB_PASSWORD=

# Optional – only if the source database has a non-default name:
SRC_DB_NAME=savingstracker_backup   # default
```

---

## Usage

Run from the **project root** (`Savings_Tracker_v2_Flask/`):

```powershell
# Activate virtual environment first
.\.venv\Scripts\Activate.ps1

# ── Dry-run (no writes, shows cleanup + migration plan) ───────────────────
python migration/migrate_prod_to_v2.py --dry-run

# ── Full-refresh migration ─────────────────────────────────────────────────
python migration/migrate_prod_to_v2.py

# ── Override source DB name if it differs from "savingstracker_backup" ────
python migration/migrate_prod_to_v2.py --src-db savingstracker_backup

# ── Skip file tracking ────────────────────────────────────────────────────
python migration/migrate_prod_to_v2.py --skip-files
```

A log file `migration/migration.log` is written on every run.

---

## Notes

- **Legacy ID tracking**: The old `InitiativeID` (e.g. `88000001`) is embedded
  in the initiative `description` field as `[LEGACY_ID:88000001]` so the
  mapping survives re-runs and can be used for auditing.

- **Facility allocations**: The old schema stores allocations as separate money
  columns (`MMC_ALLOC`, `BURKE_ALLOC`, …). These are normalized into the
  `facility_allocations` table as dollar amounts.

- **Users without a match**: If an initiative references a username not found in
  `prod.USERS`, it falls back to a `system_migration` placeholder user that is
  created automatically.

- **Status mapping**:

  | Old value (case-insensitive) | New value       |
  |------------------------------|-----------------|
  | Approved / Closed            | Approved        |
  | Rejected                     | Rejected        |
  | Pending / Pending Review / Under Review | Pending Review |

- **Role mapping** (old `UserRoleDescription` → new role):

  | Old description contains | New role  |
  |--------------------------|-----------|
  | "super" or `isSuperUser = Y` | Admin |
  | "reviewer" / "review"    | Reviewer  |
  | "submitter" / owner / anything else | User |
