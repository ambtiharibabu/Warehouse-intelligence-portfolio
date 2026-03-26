"""
connection.py
-------------
Shared database connection utility for all Project 2 modules.

Works in two environments automatically:
    Local development  → reads credentials from .env file
    Streamlit Cloud    → reads credentials from st.secrets (Streamlit's
                         built-in secrets manager — no .env needed)

Usage in any module:
    from db.connection import get_engine
    engine = get_engine()
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


def get_engine():
    """
    Builds and returns a SQLAlchemy engine.

    Credential resolution order:
        1. Streamlit st.secrets — used when running on Streamlit Cloud
        2. Environment variables — used locally via python-dotenv
    """

    # ── Try Streamlit secrets first (Streamlit Cloud environment) ────────
    # st is only imported here — not at the top of the file — because this
    # module is also used by main.py, seeder, and other scripts that run
    # outside Streamlit. Importing st at the top would cause errors there.
    try:
        import streamlit as st
        creds = st.secrets["database"]
        return create_engine(URL.create(
            drivername = "postgresql+psycopg2",
            username   = creds["DB_USER"],
            password   = creds["DB_PASSWORD"],
            host       = creds["DB_HOST"],
            port       = int(creds["DB_PORT"]),
            database   = creds["DB_NAME"],
        ))
    except Exception:
        # Not running in Streamlit Cloud — fall through to .env
        pass

    # ── Fall back to .env file (local development) ────────────────────────
    from dotenv import load_dotenv
    load_dotenv()

    return create_engine(URL.create(
        drivername = "postgresql+psycopg2",
        username   = os.getenv("DB_USER"),
        password   = os.getenv("DB_PASSWORD"),
        host       = os.getenv("DB_HOST"),
        port       = int(os.getenv("DB_PORT")),
        database   = os.getenv("DB_NAME"),
    ))


# ── Self-test — only runs when you execute this file directly ────────────────
if __name__ == "__main__":
    print("Testing database connection...")
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM orders"))
        count  = result.scalar()
    print(f"✅ Connected successfully!")
    print(f"   orders table row count: {count:,}")