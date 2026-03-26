# ============================================================
# run_schema.py — Connects to PostgreSQL and runs schema.sql
# Creates all 5 tables if they don't already exist
# ============================================================

import psycopg2
from dotenv import load_dotenv
import os

# --- Load credentials from .env file ---
# load_dotenv() finds your .env and makes each key available
# via os.getenv() — your password never appears in this code
load_dotenv()

# --- Read each credential from the environment ---
conn_params = {
    "host":     os.getenv("DB_HOST"),
    "port":     os.getenv("DB_PORT"),
    "dbname":   os.getenv("DB_NAME"),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "sslmode":  os.getenv("DB_SSLMODE")
}

# --- Read the SQL file from disk ---
# __file__ = this script's location, so we build a path
# relative to it — works regardless of where you run it from
schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

with open(schema_path, "r") as f:
    schema_sql = f.read()

# --- Connect to PostgreSQL and execute the schema ---
try:
    conn = psycopg2.connect(**conn_params)
    cur = conn.cursor()

    # Execute all CREATE TABLE statements in one shot
    cur.execute(schema_sql)

    # Commit = permanently save changes to the database
    # Without this line, PostgreSQL rolls back everything
    conn.commit()

    print("✅ Schema created successfully. All 5 tables are ready.")

except Exception as e:
    # If anything fails, print a clear error message
    print(f"❌ Error: {e}")

finally:
    # Always close the connection — even if an error occurred
    if conn:
        cur.close()
        conn.close()