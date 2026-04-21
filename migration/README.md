# Migration: `savingstracker_backup` → `savingstracker_v2`

## Overview

This is a **full-refresh migration**. Every run:

1. Wipes all data in `savingstracker_v2` in FK-safe order.
2. Resets all identity (auto-increment) PKIDs to restart at **1** — *except* `initiatives.id`, which is preserved from the source.
3. Reloads all data from `savingstracker_backup` (`prod` schema).

The source database is never modified. It is opened read-only with `READ UNCOMMITTED` isolation.

> Both databases must be on the **same SQL Server instance**.

---

## ID Reset Behaviour

| Table                  | PKID after migration                        |
|------------------------|---------------------------------------------|
| `initiatives`          | **Inherited from backup** (e.g. `88000001`) — inserted with `IDENTITY_INSERT ON` |
| `users`                | Reset → starts at **1**                     |
| `user_roles`           | Reset → starts at **1**                     |
| `facilities`           | Reset → starts at **1**                     |
| `cost_savings`         | Reset → starts at **1**                     |
| `cost_avoidance`       | Reset → starts at **1**                     |
| `rebates`              | Reset → starts at **1**                     |
| `facility_allocations` | Reset → starts at **1**                     |
| `file_tracking`        | Reset → starts at **1**                     |
| `audit_logs`           | Reset → starts at **1**                     |

---

## Migration Steps

### Step 1 — Prerequisites

- Both databases are reachable on the same SQL Server host.
- `savingstracker_v2` already exists with the v2 schema created.  
  If it does not, run from the project root first:
  ```powershell
  python init_db.py
  ```
- Required Python packages are already in `requirements.txt`:  
  `pyodbc`, `Flask`, `Flask-SQLAlchemy`, `python-dotenv`

---

### Step 2 — Configure `.env`

Open `.env` in the project root and confirm these values are set:

```
DB_SERVER=<sql-server-host>              # used for BOTH source and destination
DB_NAME=savingstracker_v2                # destination database
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_TRUSTED_CONNECTION=yes                # set to "no" for SQL auth
DB_USER=                                 # only needed when not using Windows auth
DB_PASSWORD=

# Optional — only needed if the source DB name differs from the default:
SRC_DB_NAME=savingstracker_backup
```

---

### Step 3 — Activate the virtual environment

Run from the project root (`Savings_Tracker_v2_Flask/`):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

---

### Step 4 — Dry-run (no writes)

Always run dry-run first to verify connectivity and see what will be cleaned and migrated:

```powershell
python migration/migrate_prod_to_v2.py --dry-run
```

Review the output:
- Confirms both DB connections succeed.
- Lists each table, its current row count, and what will happen.
- **No data is written or deleted.**

---

### Step 5 — Run the migration

When the dry-run looks correct, run the live migration:

```powershell
python migration/migrate_prod_to_v2.py
```

What happens internally, in order:

| Phase | Action |
|-------|--------|
| **Clean** | DELETEs all rows from `audit_logs`, `file_tracking`, `facility_allocations`, `cost_savings`, `cost_avoidance`, `rebates`, `initiatives`, `users`, `facilities`, `user_roles` — in that FK-safe order |
| **Reseed** | Runs `DBCC CHECKIDENT(<table>, RESEED, 0)` on all tables above **except `initiatives`** so next inserts start at 1 |
| **Load roles** | Inserts 4 standard roles (`Admin`, `Reviewer`, `User`, `Read-Only`) |
| **Load users** | Copies `prod.USERS` → `users`; new PKIDs assigned from 1 |
| **Load facilities** | Inserts 8 hard-coded facility codes; new PKIDs assigned from 1 |
| **Load initiatives** | Copies `prod.INITIATIVE_MASTER` → `initiatives` with `IDENTITY_INSERT ON` so original `InitiativeID` values (e.g. `88000001`) are preserved exactly |
| **Load detail rows** | Copies `prod.INITIATIVE_COST_SAVINGS`, `INITIATIVE_COST_AVOIDANCE`, `INITIATIVE_REBATES` → respective v2 tables; new PKIDs from 1 |
| **Load allocations** | Normalises `MMC_ALLOC`, `BURKE_ALLOC`, … columns into `facility_allocations` rows; new PKIDs from 1 |
| **Load files** | Copies `prod.FILE_TRACKING_TABLE` → `file_tracking`; new PKIDs from 1 |

A full log is written to `migration/migration.log` on every run.

---

### Step 6 — Verify row counts

After the migration completes, the script prints a summary table.  
To additionally check for any `initiatives` that are in the backup but missing in v2:

```powershell
python migration/check_missing.py
```

Expected output when migration is complete:
```
Source total : <n>
Dest total   : <n>
Missing in v2: 0
Extra in v2  : 0
```

---

### Optional — Reset v2 without re-running migration

To wipe `savingstracker_v2` and reset all identity counters independently (e.g. before a fresh schema deploy):

```powershell
python migration/clean_v2_db.py
```

> Note: `clean_v2_db.py` uses `TRUNCATE TABLE` for child tables (auto-resets identity) and `DELETE` + `DBCC CHECKIDENT` for parent tables. It does **not** reseed `initiatives.id` by design — the migration script re-inserts those with their original IDs.

---

### Flags reference

```powershell
# Override the source DB name
python migration/migrate_prod_to_v2.py --src-db savingstracker_backup

# Skip file tracking table (faster; use when files are not yet ready)
python migration/migrate_prod_to_v2.py --skip-files

# Dry-run + skip files
python migration/migrate_prod_to_v2.py --dry-run --skip-files
```

---

## Reference: Tables Migrated

| Step | Source (`prod` schema)            | Destination (`savingstracker_v2`) |
|------|-----------------------------------|-----------------------------------|
| 1    | *(seeded from code)*              | `user_roles`                      |
| 2    | `prod.USERS`                      | `users`                           |
| 3    | *(seeded from code)*              | `facilities`                      |
| 4    | `prod.INITIATIVE_MASTER`          | `initiatives` *(IDs preserved)*   |
| 5    | `prod.INITIATIVE_COST_SAVINGS`    | `cost_savings` + `facility_allocations` |
| 6    | `prod.INITIATIVE_COST_AVOIDANCE`  | `cost_avoidance` + `facility_allocations` |
| 7    | `prod.INITIATIVE_REBATES`         | `rebates` + `facility_allocations` |
| 8    | `prod.FILE_TRACKING_TABLE`        | `file_tracking`                   |

---

## Reference: Data Transformations

**Status mapping**

| Old value (case-insensitive)             | New value        |
|------------------------------------------|------------------|
| `Approved`, `Closed`                     | `Approved`       |
| `Rejected`                               | `Rejected`       |
| `Pending`, `Pending Review`, `Under Review` | `Pending Review` |

**Role mapping** (`UserRoleDescription` → v2 role)

| Old description contains          | New role   |
|-----------------------------------|------------|
| "super" or `isSuperUser = Y`      | `Admin`    |
| "reviewer" / "review"             | `Reviewer` |
| anything else / submitter / owner | `User`     |

**Facility allocations**  
The old schema stores allocations as flat money columns (`MMC_ALLOC`, `BURKE_ALLOC`, etc.).  
The migration normalises these into individual `facility_allocations` rows.

**Missing users**  
If an initiative references a username not found in `prod.USERS`, it is assigned to a `system_migration` placeholder user created automatically.

**Allocation columns mapped**

`MMC_ALLOC` → `MMC` · `BURKE_ALLOC` → `BURKE` · `AECOM_ALLOC` → `AECOM` · `MMVO_ALLOC` → `MMVO` · `MSSO_ALLOC` → `MSSO` · `NYACK_ALLOC` → `NYACK` · `SLCH_ALLOC` → `SLCH` · `WPH_ALLOC` → `WPH`
