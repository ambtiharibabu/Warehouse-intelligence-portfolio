# ============================================================
# export_for_powerbi.py
# Exports all 5 PostgreSQL tables to CSV files
# so Power BI can load them without SSL issues
# ============================================================

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from dotenv import load_dotenv
import os

load_dotenv()

connection_url = URL.create(
    drivername = "postgresql+psycopg2",
    username   = os.getenv("DB_USER"),
    password   = os.getenv("DB_PASSWORD"),
    host       = os.getenv("DB_HOST"),
    port       = int(os.getenv("DB_PORT")),
    database   = os.getenv("DB_NAME")
)
engine = create_engine(connection_url)

# Output folder — save inside powerbi/ subfolder
output_dir = "powerbi"
os.makedirs(output_dir, exist_ok=True)

tables = ["orders", "inventory", "labor", "safety_incidents", "shipments"]

for table in tables:
    df = pd.read_sql(f"SELECT * FROM {table}", engine)
    path = os.path.join(output_dir, f"{table}.csv")
    df.to_csv(path, index=False)
    print(f"✅ {table}: {len(df):,} rows → {path}")

print("\n🎉 All CSVs exported to powerbi/ folder")