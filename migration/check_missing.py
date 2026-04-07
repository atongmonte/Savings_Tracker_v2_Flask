import os, pyodbc
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

server = os.getenv('DB_SERVER', r'YNBBSTVWP02\PROCDATASRVPROD')
driver = 'ODBC Driver 17 for SQL Server'

src = pyodbc.connect(f'Driver={{{driver}}};Server={server};Database=savingstracker_backup;Trusted_Connection=yes;')
dst = pyodbc.connect(f'Driver={{{driver}}};Server={server};Database=savingstracker_v2;Trusted_Connection=yes;')

src.execute('SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED')

# All source initiative IDs
cur = src.cursor()
cur.execute('SELECT InitiativeID, Initiative_Type, Initiative_Desc, Status, IsDeleted FROM prod.INITIATIVE_MASTER ORDER BY InitiativeID')
src_rows = {r[0]: r for r in cur.fetchall()}

# All dest initiative IDs
cur2 = dst.cursor()
cur2.execute('SELECT id FROM initiatives')
dst_ids = {r[0] for r in cur2.fetchall()}

missing = {k: v for k, v in src_rows.items() if k not in dst_ids}
extra   = dst_ids - src_rows.keys()

print(f"Source total : {len(src_rows)}")
print(f"Dest total   : {len(dst_ids)}")
print(f"Missing in v2: {len(missing)}")
print(f"Extra in v2  : {len(extra)}")

if missing:
    print("\nMissing initiative IDs:")
    print(f"{'ID':>12}  {'Type':<20}  {'Status':<15}  {'IsDeleted'}  Description")
    print("-" * 90)
    for iid, row in sorted(missing.items()):
        desc = (row[2] or '')[:40]
        print(f"{row[0]:>12}  {str(row[1] or ''):<20}  {str(row[3] or ''):<15}  {str(row[4] or ''):<10}  {desc}")

src.close()
dst.close()
