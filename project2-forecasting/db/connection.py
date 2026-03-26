"""
connection.py
-------------
Shared database connection utility for all Project 2 modules.

Works in two environments automatically:
    Streamlit Cloud    → reads from st.secrets["database"]
    Local development  → reads from .env file via python-dotenv
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


def get_engine():
    """
    Builds and returns a SQLAlchemy engine.
    Tries Streamlit secrets first, falls back to .env for local use.
    """

    # ── Try Streamlit secrets first ───────────────────────────────────────
    # We check for the secrets key explicitly rather than wrapping the
    # entire block in try/except — this way real errors still surface.
    try:
        import streamlit as st
        # hasattr check prevents AttributeError if st.secrets isn't available
        if hasattr(st, "secrets") and "database" in st.secrets:
            creds = st.secrets["database"]
            return create_engine(URL.create(
                drivername = "postgresql+psycopg2",
                username   = str(creds["DB_USER"]),
                password   = str(creds["DB_PASSWORD"]),
                host       = str(creds["DB_HOST"]),
                port       = int(creds["DB_PORT"]),
                database   = str(creds["DB_NAME"]),
            ))
    except Exception:
        # st not available (running outside Streamlit) — fall through to .env
        pass

    # ── Fall back to .env file (local development) ────────────────────────
    from dotenv import load_dotenv
    load_dotenv()

    host     = os.getenv("DB_HOST")
    port     = os.getenv("DB_PORT")
    name     = os.getenv("DB_NAME")
    user     = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    # Fail with a clear message if credentials are missing
    if not all([host, port, name, user, password]):
        raise ValueError(
            "Database credentials not found. "
            "Create a .env file locally or add secrets on Streamlit Cloud."
        )

    return create_engine(URL.create(
        drivername = "postgresql+psycopg2",
        username   = user,
        password   = password,
        host       = host,
        port       = int(port),
        database   = name,
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