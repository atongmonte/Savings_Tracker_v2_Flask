"""Add allocation entities and zero backfills; preview unless --apply is supplied.

Run from the project root with:
    python -m migration.add_garnett_sjrh --environment development --apply
    python -m migration.add_garnett_sjrh --environment production --apply

Existing allocation values and environment-specific SQL definitions are preserved.
The daily distribution procedure is updated, but never executed by this migration.
"""
import argparse
import re

from sqlalchemy import create_engine, text

from app.config import config


FACILITIES = (("GARNETT", "Garnett"), ("SJRH", "SJRH"))
VIEW = "dbo.vw_initiative_dashboard"
PROCEDURE = "dbo.SAVINGS_TRACKER_DAILY_DISTRIBUTION_PROCEDURE"
REPORT = "dbo.SAVINGS_TRACKER_REPORT_DAILY_DISTRIBUTION"


def replace_checked(source, pattern, replacement, count):
    result, actual = re.subn(pattern, replacement, source, flags=re.I | re.M)
    if actual != count:
        raise ValueError(f"Unexpected SQL definition: {pattern!r} matched {actual}, expected {count}")
    return result


def extend_view(source):
    if all(f"{code}_ALLOC" in source.upper() for code, _ in FACILITIES):
        return source
    columns = "".join(f"  , ISNULL(FA_{code}.allocation_amount, 0) AS {code}_ALLOC\n" for code, _ in FACILITIES)
    joins = "".join(
        f"LEFT JOIN facility_allocations AS FA_{code}\n"
        f"    ON FA_{code}.initiative_id = I.id\n"
        f"   AND FA_{code}.facility_id = (SELECT id FROM facilities WHERE code = '{code}')\n\n"
        for code, _ in FACILITIES
    )
    source = replace_checked(source, r"^FROM initiatives AS I\s*$", columns + "\nFROM initiatives AS I", 1)
    source = replace_checked(source, r"^WHERE I\.is_deleted = 0;", joins + "WHERE I.is_deleted = 0;", 1)
    return replace_checked(source, r"\b(?:CREATE(?:\s+OR\s+ALTER)?|ALTER)\s+VIEW\b", "ALTER VIEW", 1)


def extend_procedure(source):
    if all(f"@alloc_{code}".upper() in source.upper() for code, _ in FACILITIES):
        return source
    # Copy just AECOM's declarations/calculation, preserving every other statement.
    for pattern in (
        r"^[ \t]*AECOM_alloc DECIMAL\(18, 2\),[ \t]*$",
        r"^[ \t]*daily_alloc_AECOM DECIMAL\(18, 2\),[ \t]*$",
        r"^DECLARE @alloc_AECOM DECIMAL\(18, 2\);[ \t]*$",
        r"^DECLARE @daily_alloc_AECOM DECIMAL\(18, 2\);[ \t]*$",
        r"^[ \t]*SET @daily_alloc_AECOM = @alloc_AECOM / @days;[ \t]*$",
    ):
        source = replace_checked(source, pattern, lambda m: m[0] + "\n" + "\n".join(m[0].replace("AECOM", code) for code, _ in FACILITIES), 1)
    source = replace_checked(source, r"^[ \t]*,AECOM_ALLOC[ \t]*$", lambda m: m[0] + "\n    ,GARNETT_ALLOC\n    ,SJRH_ALLOC", 1)
    for token, count in (("@alloc_AECOM", 3), ("@daily_alloc_AECOM", 1), ("AECOM_alloc", 1), ("daily_alloc_AECOM", 1)):
        replacement = token + ", " + ", ".join(token.replace("AECOM", code) for code, _ in FACILITIES) + ","
        source = replace_checked(source, r"(?<![\w@])" + re.escape(token) + r",", replacement, count)
    return replace_checked(source, r"\b(?:CREATE(?:\s+OR\s+ALTER)?|ALTER)\s+PROCEDURE\b", "ALTER PROCEDURE", 1)


def migrate(environment, apply=False):
    engine = create_engine(config[environment].SQLALCHEMY_DATABASE_URI)
    with engine.begin() as conn:
        conn.exec_driver_sql("SET XACT_ABORT ON; SET LOCK_TIMEOUT 15000;")
        database = conn.execute(text("SELECT DB_NAME()")).scalar_one()
        definitions = {}
        for name, transform in ((VIEW, extend_view), (PROCEDURE, extend_procedure)):
            original = conn.execute(text("SELECT OBJECT_DEFINITION(OBJECT_ID(:name))"), {"name": name}).scalar_one()
            if not original:
                raise ValueError(f"Cannot read {name} in {database}")
            original = original.replace("\r\n", "\n")
            definitions[name] = (original, transform(original))
        count = conn.execute(text("SELECT COUNT(*) FROM dbo.initiatives")).scalar_one()
        print(f"{database}: {count} initiatives; SQL definitions validated.")
        if not apply:
            print("Preview only. Use --apply to add entities, backfill zeros, and extend reporting.")
            return

        original_allocations = conn.execute(text("""
            SELECT a.id, a.initiative_id, a.facility_id, a.allocation_percentage, a.allocation_amount
            FROM dbo.facility_allocations a JOIN dbo.facilities f ON f.id = a.facility_id
            WHERE f.code NOT IN ('GARNETT', 'SJRH') ORDER BY a.id
        """)).all()
        for code, name in FACILITIES:
            conn.execute(text("""
                IF NOT EXISTS (SELECT 1 FROM dbo.facilities WITH (UPDLOCK, HOLDLOCK) WHERE code = :code)
                    INSERT INTO dbo.facilities (code, name, is_active, created_at, updated_at)
                    VALUES (:code, :name, 1, GETDATE(), GETDATE());
            """), {"code": code, "name": name})
            conn.execute(text("""
                INSERT INTO dbo.facility_allocations
                    (initiative_id, facility_id, allocation_percentage, allocation_amount, created_at, updated_at)
                SELECT i.id, f.id, NULL, 0, GETDATE(), GETDATE()
                FROM dbo.initiatives i CROSS JOIN dbo.facilities f
                WHERE f.code = :code AND NOT EXISTS (
                    SELECT 1 FROM dbo.facility_allocations a WITH (UPDLOCK, HOLDLOCK)
                    WHERE a.initiative_id = i.id AND a.facility_id = f.id
                );
            """), {"code": code})
        # Add zero columns to existing report rows without rebuilding the report.
        for code, _ in FACILITIES:
            for column in (f"{code}_alloc", f"daily_alloc_{code}"):
                conn.exec_driver_sql(f"""
                    IF OBJECT_ID('{REPORT}', 'U') IS NOT NULL
                       AND COL_LENGTH('{REPORT}', '{column}') IS NULL
                        ALTER TABLE {REPORT} ADD {column} DECIMAL(18, 2) NOT NULL
                        CONSTRAINT DF_daily_distribution_{column} DEFAULT (0) WITH VALUES;
                """)

        for original, modified in definitions.values():
            if original != modified:
                conn.exec_driver_sql(modified)

        current_allocations = conn.execute(text("""
            SELECT a.id, a.initiative_id, a.facility_id, a.allocation_percentage, a.allocation_amount
            FROM dbo.facility_allocations a JOIN dbo.facilities f ON f.id = a.facility_id
            WHERE f.code NOT IN ('GARNETT', 'SJRH') ORDER BY a.id
        """)).all()
        if current_allocations != original_allocations:
            raise ValueError("Existing entity allocations changed; rolling back")
        for code, _ in FACILITIES:
            row = conn.execute(text("""
                SELECT COUNT(*) AS allocations,
                    SUM(CASE WHEN a.allocation_amount = 0 OR a.allocation_percentage = 0 THEN 1 ELSE 0 END) AS zeros
                FROM dbo.facility_allocations a JOIN dbo.facilities f ON f.id = a.facility_id
                WHERE f.code = :code
            """), {"code": code}).one()
            if row.allocations != count:
                raise ValueError(f"Incomplete allocation backfill for {code}")
            print(f"  {code}: {row.allocations} allocations, {row.zeros or 0} zero values")
        conn.exec_driver_sql(f"SELECT TOP (1) GARNETT_ALLOC, SJRH_ALLOC FROM {VIEW}").all()
        print(f"  Verified: {len(original_allocations)} existing allocation rows unchanged.")
    print(f"{database}: committed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=("development", "production"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    migrate(args.environment, args.apply)
