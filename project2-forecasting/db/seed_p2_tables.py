"""
seed_p2_tables.py
-----------------
Creates and populates:
  - suppliers     (new P2 table)
  - sku_master    (new P2 table)
  - orders        (backfill: adds 9 months of history to P1's existing data)

Safe to re-run: suppliers and sku_master are dropped and recreated.
Orders backfill checks for existing BFILL- prefixed rows before inserting.
"""

import os
import numpy as np
import pandas as pd
from faker import Faker
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from datetime import date, timedelta

# ── Load credentials from .env ──────────────────────────────────────────────
load_dotenv()

connection_url = URL.create(
    drivername="postgresql+psycopg2",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    database=os.getenv("DB_NAME"),
)
engine = create_engine(connection_url)

fake = Faker()
np.random.seed(42)   # makes random results reproducible — same numbers every run

# ── Constants ────────────────────────────────────────────────────────────────
SKUS = [f"SKU-{str(i).zfill(4)}" for i in range(1, 21)]   # SKU-0001 to SKU-0020

CATEGORIES = {
    "SKU-0001": "Electronics",  "SKU-0002": "Electronics",
    "SKU-0003": "Electronics",  "SKU-0004": "Electronics",
    "SKU-0005": "Consumables",  "SKU-0006": "Consumables",
    "SKU-0007": "Consumables",  "SKU-0008": "Consumables",
    "SKU-0009": "Equipment",    "SKU-0010": "Equipment",
    "SKU-0011": "Equipment",    "SKU-0012": "Equipment",
    "SKU-0013": "Packaging",    "SKU-0014": "Packaging",
    "SKU-0015": "Packaging",    "SKU-0016": "Packaging",
    "SKU-0017": "Spare Parts",  "SKU-0018": "Spare Parts",
    "SKU-0019": "Spare Parts",  "SKU-0020": "Spare Parts",
}

# Cost parameters by category — realistic warehouse cost ranges
CATEGORY_PARAMS = {
    "Electronics": {
        "holding_cost_per_day": 0.85,
        "stockout_cost_per_unit": 45.00,
        "order_cost": 120.00,
        "cost_per_unit_range": (80, 250),
        "annual_demand_range": (800, 2000),
    },
    "Consumables": {
        "holding_cost_per_day": 0.15,
        "stockout_cost_per_unit": 8.00,
        "order_cost": 45.00,
        "cost_per_unit_range": (5, 30),
        "annual_demand_range": (3000, 8000),
    },
    "Equipment": {
        "holding_cost_per_day": 1.20,
        "stockout_cost_per_unit": 90.00,
        "order_cost": 200.00,
        "cost_per_unit_range": (150, 500),
        "annual_demand_range": (300, 900),
    },
    "Packaging": {
        "holding_cost_per_day": 0.05,
        "stockout_cost_per_unit": 3.00,
        "order_cost": 30.00,
        "cost_per_unit_range": (1, 10),
        "annual_demand_range": (5000, 15000),
    },
    "Spare Parts": {
        "holding_cost_per_day": 0.40,
        "stockout_cost_per_unit": 60.00,
        "order_cost": 85.00,
        "cost_per_unit_range": (20, 120),
        "annual_demand_range": (500, 1500),
    },
}


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 1 — Generate and write suppliers table
# Each SKU gets one primary supplier. 10 supplier companies serve 20 SKUs.
# ════════════════════════════════════════════════════════════════════════════
def seed_suppliers():
    print("\n📦 Seeding suppliers table...")

    # 10 supplier IDs — each serves 2 SKUs
    supplier_pool = [f"SUP-{str(i).zfill(3)}" for i in range(1, 11)]

    rows = []
    for i, sku in enumerate(SKUS):
        cat = CATEGORIES[sku]
        params = CATEGORY_PARAMS[cat]
        cost_low, cost_high = params["cost_per_unit_range"]

        rows.append({
            "supplier_id":       supplier_pool[i // 2],   # every 2 SKUs share a supplier
            "sku":               sku,
            "lead_time_days":    int(np.random.choice([3, 5, 7, 10, 14, 21],
                                     p=[0.10, 0.25, 0.30, 0.20, 0.10, 0.05])),
            "cost_per_unit":     round(np.random.uniform(cost_low, cost_high), 2),
            "min_order_qty":     int(np.random.choice([10, 25, 50, 100, 200],
                                     p=[0.15, 0.30, 0.30, 0.20, 0.05])),
            "reliability_score": round(np.random.uniform(0.72, 0.99), 2),
        })

    df = pd.DataFrame(rows)

    # Drop and recreate — safe for re-runs
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS suppliers"))
        conn.commit()

    df.to_sql("suppliers", engine, if_exists="replace", index=False)
    print(f"   ✅ suppliers: {len(df)} rows written")
    return df


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 2 — Generate and write sku_master table
# One row per SKU — holds all cost parameters used by EOQ and waste modules.
# ════════════════════════════════════════════════════════════════════════════
def seed_sku_master():
    print("\n📋 Seeding sku_master table...")

    rows = []
    for sku in SKUS:
        cat = CATEGORIES[sku]
        params = CATEGORY_PARAMS[cat]
        demand_low, demand_high = params["annual_demand_range"]

        rows.append({
            "sku":                    sku,
            "category":               cat,
            "holding_cost_per_day":   params["holding_cost_per_day"],
            "stockout_cost_per_unit": params["stockout_cost_per_unit"],
            "order_cost":             params["order_cost"],
            "annual_demand":          int(np.random.randint(demand_low, demand_high)),
        })

    df = pd.DataFrame(rows)

    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS sku_master"))
        conn.commit()

    df.to_sql("sku_master", engine, if_exists="replace", index=False)
    print(f"   ✅ sku_master: {len(df)} rows written")
    return df


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 3 — Backfill orders table with ~9 months of historical data
# Date range: today - 365 days  →  today - 91 days
# Uses "BFILL-" prefix on order_id — guarantees no collision with P1's IDs.
# Skips insert entirely if backfill rows already exist (safe to re-run).
# ════════════════════════════════════════════════════════════════════════════
def backfill_orders():
    print("\n🕐 Backfilling orders table with historical data...")

    # Check if backfill already exists — avoid duplicate inserts on re-run
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM orders WHERE order_id LIKE 'BFILL-%'")
        )
        existing = result.scalar()

    if existing > 0:
        print(f"   ⚠️  Backfill rows already exist ({existing} rows). Skipping.")
        print("      Delete BFILL- rows manually in DBeaver to re-seed.")
        return

    # Define the backfill date window
    today = date.today()
    start_date = today - timedelta(days=365)   # ~12 months ago
    end_date   = today - timedelta(days=91)    # where P1's data begins

    # Build a list of all dates in the window
    date_range = pd.date_range(start=start_date, end=end_date, freq="D")
    print(f"   Date window: {start_date} → {end_date} ({len(date_range)} days)")

    # Status distribution — mirrors P1's calibration
    statuses    = ["fulfilled", "late", "failed"]
    status_probs = [0.94, 0.04, 0.02]

    shifts       = ["AM", "PM", "Night"]
    shift_probs  = [0.40, 0.35, 0.25]

    rows = []
    order_counter = 1   # used to build unique BFILL- IDs

    for single_date in date_range:
        # Generate 40-60 orders per day (P1 averaged ~50/day)
        daily_order_count = np.random.randint(40, 61)

        for _ in range(daily_order_count):
            status = np.random.choice(statuses, p=status_probs)

            # Fulfillment time varies by status — mirrors realistic warehouse ops
            if status == "fulfilled":
                fulfillment_hrs = round(np.random.uniform(0.5, 4.0), 2)
            elif status == "late":
                fulfillment_hrs = round(np.random.uniform(4.0, 10.0), 2)
            else:   # failed
                fulfillment_hrs = round(np.random.uniform(8.0, 24.0), 2)

            rows.append({
                "order_id":            f"BFILL-{str(order_counter).zfill(6)}",
                "sku":                 np.random.choice(SKUS),
                "order_date":          single_date.date(),
                "shift":               np.random.choice(shifts, p=shift_probs),
                "status":              status,
                "fulfillment_time_hrs": fulfillment_hrs,
            })
            order_counter += 1

    df = pd.DataFrame(rows)

    # Write backfill rows — append so P1's data is untouched
    df.to_sql("orders", engine, if_exists="append", index=False)
    print(f"   ✅ orders backfill: {len(df)} rows written")
    print(f"   ✅ order_id range: BFILL-000001 → BFILL-{str(order_counter-1).zfill(6)}")


# ════════════════════════════════════════════════════════════════════════════
# MAIN — runs all three blocks in sequence
# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 55)
    print("  Project 2 — Database Seeder")
    print("=" * 55)

    seed_suppliers()
    seed_sku_master()
    backfill_orders()

    print("\n" + "=" * 55)
    print("  ✅ All seeding complete!")
    print("  Open DBeaver to verify all three tables.")
    print("=" * 55)