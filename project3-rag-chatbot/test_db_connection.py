# test_db_connection.py
# ─────────────────────────────────────────────────────────────────────────────
# One-time diagnostic: confirms Python can reach PostgreSQL and see all tables.
# Run this before building ingest.py — not part of the pipeline itself.
# ─────────────────────────────────────────────────────────────────────────────

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
import config

def get_engine():
    """
    Build SQLAlchemy engine using URL.create() — inherited P1/P2 pattern.
    URL.create() safely handles special characters (like @) in the password.
    """
    connection_url = URL.create(
        drivername = config.DB_CONFIG["drivername"],
        username   = config.DB_CONFIG["username"],
        password   = config.DB_CONFIG["password"],
        host       = config.DB_CONFIG["host"],
        port       = config.DB_CONFIG["port"],
        database   = config.DB_CONFIG["database"],
    )
    return create_engine(
        connection_url,
        connect_args={"sslmode": config.DB_SSLMODE}
    )

def run_connection_test():
    print("=" * 55)
    print("  P3 — PostgreSQL Connection Test")
    print("=" * 55)

    # ── Step 1: Try to connect ────────────────────────────────
    print("\n[1/3] Connecting to PostgreSQL...")
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("      ✓ Connection successful")
    except Exception as e:
        print(f"      ✗ Connection FAILED: {e}")
        print("\n  Check: .env file has correct DB_HOST, DB_USER, DB_PASSWORD")
        return  # Stop here — no point continuing if connection fails

    # ── Step 2: List all tables in the database ───────────────
    print("\n[2/3] Listing all tables visible to this user...")
    query_tables = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """
    tables_df = pd.read_sql(query_tables, engine)
    print(f"      Found {len(tables_df)} tables:")
    for t in tables_df["table_name"].tolist():
        print(f"        - {t}")

    # ── Step 3: Row counts for every table P3 will ingest ─────
    print("\n[3/3] Row counts for P3 ingestion tables:")
    print(f"  {'Table':<25} {'Rows':>8}")
    print(f"  {'-'*25} {'-'*8}")

    total_rows = 0
    for table in config.TABLES_TO_INGEST:
        try:
            result = pd.read_sql(
                f"SELECT COUNT(*) AS cnt FROM {table}", engine
            )
            count = result["cnt"].iloc[0]
            total_rows += count
            status = "✓" if count > 0 else "⚠ EMPTY"
            print(f"  {table:<25} {count:>8,}  {status}")
        except Exception as e:
            print(f"  {table:<25} {'ERROR':>8}  ✗ {e}")

    print(f"  {'-'*25} {'-'*8}")
    print(f"  {'TOTAL':<25} {total_rows:>8,}")

    print("\n" + "=" * 55)
    print("  Connection test complete — ready for ingest.py")
    print("=" * 55)

if __name__ == "__main__":
    run_connection_test()