# ============================================================
# generate_data.py
# Generates synthetic warehouse data using Faker and writes
# all 5 tables directly to PostgreSQL on DigitalOcean
# ============================================================

import random
import pandas as pd
from faker import Faker
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta

# --- Setup ---
load_dotenv()
fake = Faker()
random.seed(42)   # Makes output reproducible every run

# --- Build connection using individual parameters ---
# This avoids URL parsing issues when password contains
# special characters like @, #, or /
from sqlalchemy.engine import URL

connection_url = URL.create(
    drivername = "postgresql+psycopg2",
    username   = os.getenv("DB_USER"),
    password   = os.getenv("DB_PASSWORD"),
    host       = os.getenv("DB_HOST"),
    port       = int(os.getenv("DB_PORT")),
    database   = os.getenv("DB_NAME")
)
engine = create_engine(connection_url)

# --- Config: how much data to generate ---
NUM_DAYS   = 90    # 3 months of history
NUM_SKUS   = 20    # distinct product codes in the warehouse
NUM_ASSOCIATES = 30  # warehouse staff

# --- Build reference lists used across all tables ---
skus        = [f"SKU-{str(i).zfill(4)}" for i in range(1, NUM_SKUS + 1)]
shifts      = ["AM", "PM", "Night"]
departments = ["Receiving", "Putaway", "Picking", "Packing", "Shipping"]
carriers    = ["FedEx", "UPS", "DHL", "USPS", "OnTrac"]
associates  = [f"EMP-{str(i).zfill(3)}" for i in range(1, NUM_ASSOCIATES + 1)]

# Base date: generate data for the last 90 days up to today
end_date   = datetime.today().date()
start_date = end_date - timedelta(days=NUM_DAYS)

def random_date(start, end):
    """Returns a random date between start and end."""
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))

# ============================================================
# TABLE 1: orders
# ~50 orders per day across 90 days = ~4,500 rows
# ============================================================
print("Generating orders...")
orders_rows = []

for _ in range(50 * NUM_DAYS):
    order_date = random_date(start_date, end_date)
    
    # 94% of orders are fulfilled on time — leaves room for KPI alerts
    status = random.choices(
        ["fulfilled", "late", "failed"],
        weights=[94, 4, 2]
    )[0]
    
    # Fulfillment time: on-time orders are faster than late ones
    if status == "fulfilled":
        fulfillment_hrs = round(random.uniform(1.0, 8.0), 2)
    elif status == "late":
        fulfillment_hrs = round(random.uniform(8.1, 24.0), 2)
    else:
        fulfillment_hrs = None   # Failed orders have no fulfillment time

    orders_rows.append({
        "order_id":             f"ORD-{fake.unique.random_int(min=10000, max=99999)}",
        "sku":                  random.choice(skus),
        "order_date":           order_date,
        "shift":                random.choice(shifts),
        "status":               status,
        "fulfillment_time_hrs": fulfillment_hrs
    })

orders_df = pd.DataFrame(orders_rows)

# ============================================================
# TABLE 2: inventory
# 2 cycle counts per SKU per week = ~360 rows
# ============================================================
print("Generating inventory...")
inventory_rows = []

for sku in skus:
    for week in range(NUM_DAYS // 7):
        count_date     = start_date + timedelta(weeks=week)
        expected_count = random.randint(100, 500)
        
        # 96% accuracy on average — will trigger KPI warnings
        accuracy       = random.uniform(0.93, 1.00)
        actual_count   = int(expected_count * accuracy)

        inventory_rows.append({
            "sku":            sku,
            "count_date":     count_date,
            "expected_count": expected_count,
            "actual_count":   actual_count,
            "location":       f"AISLE-{random.randint(1, 20)}-BIN-{random.randint(1, 50)}",
            "category":       random.choice(["Electronics", "Apparel", "Grocery", "Hardware", "Fragile"])
        })

inventory_df = pd.DataFrame(inventory_rows)

# ============================================================
# TABLE 3: labor
# Each associate works ~5 days/week = ~1,800 rows
# ============================================================
print("Generating labor...")
labor_rows = []

for associate in associates:
    dept = random.choice(departments)   # Each associate stays in one dept
    for day_offset in range(NUM_DAYS):
        work_date = start_date + timedelta(days=day_offset)
        
        # Associates work 5 out of 7 days — skip weekends randomly
        if random.random() < 0.28:
            continue

        hours_worked    = round(random.uniform(7.5, 9.5), 2)
        units_processed = int(random.uniform(75, 115) * hours_worked)

        labor_rows.append({
            "associate_id":    associate,
            "shift":           random.choice(shifts),
            "work_date":       work_date,
            "units_processed": units_processed,
            "hours_worked":    hours_worked,
            "department":      dept
        })

labor_df = pd.DataFrame(labor_rows)

# ============================================================
# TABLE 4: safety_incidents
# Low frequency — ~2 incidents per week = ~25 rows
# ============================================================
print("Generating safety incidents...")
safety_rows = []

for _ in range(4):   # Realistic: ~4 incidents per 30 workers over 90 days
    incident_date = random_date(start_date, end_date)

    safety_rows.append({
        "incident_id":    f"INC-{fake.unique.random_int(min=1000, max=9999)}",
        "incident_date":  incident_date,
        "shift":          random.choice(shifts),
        "incident_type":  random.choices(
                              ["near-miss", "injury", "violation"],
                              weights=[60, 20, 20]
                          )[0],
        "severity":       random.choices(
                              ["low", "medium", "high"],
                              weights=[65, 25, 10]
                          )[0]
    })

safety_df = pd.DataFrame(safety_rows)

# ============================================================
# TABLE 5: shipments
# ~15 shipments per day = ~1,350 rows
# ============================================================
print("Generating shipments...")
shipment_rows = []

for _ in range(15 * NUM_DAYS):
    ship_date      = random_date(start_date, end_date)
    
    # Scheduled departure: sometime between 8am and 6pm
    sched_hour     = random.randint(8, 18)
    scheduled_time = datetime.combine(ship_date, datetime.min.time()).replace(
                         hour=sched_hour, minute=random.randint(0, 59)
                     )
    
    # 93% on-time — slight delay for late shipments
    status         = random.choices(["on-time", "late"], weights=[93, 7])[0]
    delay_minutes  = 0 if status == "on-time" else random.randint(30, 240)
    actual_time    = scheduled_time + timedelta(minutes=delay_minutes)

    shipment_rows.append({
        "shipment_id":    f"SHIP-{fake.unique.random_int(min=10000, max=99999)}",
        "ship_date":      ship_date,
        "scheduled_time": scheduled_time,
        "actual_time":    actual_time,
        "status":         status,
        "carrier":        random.choice(carriers)
    })

shipments_df = pd.DataFrame(shipment_rows)

# ============================================================
# WRITE ALL 5 TABLES TO POSTGRESQL
# if_exists='append' → adds rows without dropping the table
# index=False       → don't write the DataFrame row numbers
# ============================================================
print("\nWriting to PostgreSQL...")

tables = {
    "orders":           orders_df,
    "inventory":        inventory_df,
    "labor":            labor_df,
    "safety_incidents": safety_df,
    "shipments":        shipments_df
}

with engine.connect() as conn:
    for table_name, df in tables.items():
        df.to_sql(table_name, conn, if_exists="append", index=False)
        print(f"  ✅ {table_name}: {len(df):,} rows written")

print("\n🎉 All data loaded. Your warehouse is stocked!")