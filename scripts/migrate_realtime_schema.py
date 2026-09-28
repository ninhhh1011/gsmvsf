"""
Migration script to logically separate operational realtime state from core static data.
Creates schema 'realtime' and moves 'state_snapshots' and 'candidate_searches' into it,
while establishing backward-compatible views in 'public'.
"""
import sys
import psycopg2

def run_migration(db_url="postgresql://postgres:postgres@127.0.0.1:5432/ev_recommendation"):
    print(f"Connecting to {db_url}...")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()

    # 1. Create realtime schema
    cur.execute("CREATE SCHEMA IF NOT EXISTS realtime;")
    print("Schema 'realtime' ensured.")

    # 2. Check if state_snapshots is a base table in public
    cur.execute("""
        SELECT table_type FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'state_snapshots'
    """)
    res = cur.fetchone()
    if res and res[0] == 'BASE TABLE':
        print("Moving public.state_snapshots to realtime.state_snapshots...")
        cur.execute("ALTER TABLE public.state_snapshots SET SCHEMA realtime;")
        cur.execute("CREATE OR REPLACE VIEW public.state_snapshots AS SELECT * FROM realtime.state_snapshots;")
        print("Created public.state_snapshots view for backward compatibility.")
    elif not res:
        print("Creating realtime.state_snapshots if not exists...")
        with open("backend/app/services/snapshots/schema.sql", "r", encoding="utf-8") as f:
            sql = f.read()
        cur.execute("SET search_path TO realtime, public;")
        cur.execute(sql)
        cur.execute("SET search_path TO public;")
        cur.execute("CREATE OR REPLACE VIEW public.state_snapshots AS SELECT * FROM realtime.state_snapshots;")

    # 3. Check candidate_searches
    cur.execute("""
        SELECT table_type FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'candidate_searches'
    """)
    res = cur.fetchone()
    if res and res[0] == 'BASE TABLE':
        print("Moving public.candidate_searches to realtime.candidate_searches...")
        cur.execute("ALTER TABLE public.candidate_searches SET SCHEMA realtime;")
        cur.execute("CREATE OR REPLACE VIEW public.candidate_searches AS SELECT * FROM realtime.candidate_searches;")
        print("Created public.candidate_searches view for backward compatibility.")

    cur.close()
    conn.close()
    print("Migration finished successfully!")

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "postgresql://postgres:postgres@127.0.0.1:5432/ev_recommendation"
    run_migration(url)
