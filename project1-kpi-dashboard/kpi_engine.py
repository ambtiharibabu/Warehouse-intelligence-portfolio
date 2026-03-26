# ============================================================
# kpi_engine.py
# Calculates all 6 warehouse KPIs by querying PostgreSQL.
# Each KPI is a standalone function returning a dict.
# Called by dashboard.py and alerts.py
# ============================================================

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from dotenv import load_dotenv
import os

load_dotenv()

# --- Reusable connection builder ---
# Defined once here so every KPI function can call get_engine()
# without repeating connection code
def get_engine():
    connection_url = URL.create(
        drivername = "postgresql+psycopg2",
        username   = os.getenv("DB_USER"),
        password   = os.getenv("DB_PASSWORD"),
        host       = os.getenv("DB_HOST"),
        port       = int(os.getenv("DB_PORT")),
        database   = os.getenv("DB_NAME")
    )
    return create_engine(connection_url)


# ============================================================
# KPI 1: Order Fulfillment Rate
# Formula: fulfilled orders / total orders × 100
# Alert: <95% | Warning: <98%
# ============================================================
def get_fulfillment_rate(start_date=None, end_date=None, shift=None):
    engine = get_engine()

    filters = ["1=1"]
    if start_date: filters.append(f"order_date >= '{start_date}'")
    if end_date:   filters.append(f"order_date <= '{end_date}'")
    if shift and shift != "All": filters.append(f"shift = '{shift}'")
    where = " AND ".join(filters)

    query = f"""
        SELECT
            COUNT(*) AS total_orders,
            COUNT(*) FILTER (WHERE status = 'fulfilled') AS fulfilled_orders
        FROM orders
        WHERE {where}
    """
    df = pd.read_sql(query, engine)

    total     = df["total_orders"][0]
    fulfilled = df["fulfilled_orders"][0]
    rate      = round((fulfilled / total * 100), 2) if total > 0 else 0

    return {
        "label":     "Order Fulfillment Rate",
        "value":     rate,
        "unit":      "%",
        "total":     int(total),
        "fulfilled": int(fulfilled)
    }


# ============================================================
# KPI 2: Inventory Accuracy
# Formula: sum(actual_count) / sum(expected_count) × 100
# Alert: <97% | Warning: <99%
# ============================================================
def get_inventory_accuracy(start_date=None, end_date=None):
    engine = get_engine()

    filters = ["1=1"]
    if start_date: filters.append(f"count_date >= '{start_date}'")
    if end_date:   filters.append(f"count_date <= '{end_date}'")
    where = " AND ".join(filters)

    query = f"""
        SELECT
            SUM(expected_count) AS expected,
            SUM(actual_count)   AS actual
        FROM inventory
        WHERE {where}
    """
    df = pd.read_sql(query, engine)

    expected = df["expected"][0]
    actual   = df["actual"][0]
    accuracy = round((actual / expected * 100), 2) if expected > 0 else 0

    return {
        "label":    "Inventory Accuracy",
        "value":    accuracy,
        "unit":     "%",
        "expected": int(expected),
        "actual":   int(actual)
    }


# ============================================================
# KPI 3: Labor Productivity
# Formula: total units processed / total hours worked
# Alert: <85 u/hr | Warning: <95 u/hr
# ============================================================
def get_labor_productivity(start_date=None, end_date=None,
                           shift=None, department=None):
    engine = get_engine()

    filters = ["1=1"]
    if start_date:  filters.append(f"work_date >= '{start_date}'")
    if end_date:    filters.append(f"work_date <= '{end_date}'")
    if shift and shift != "All": filters.append(f"shift = '{shift}'")
    if department and department != "All":
        filters.append(f"department = '{department}'")
    where = " AND ".join(filters)

    query = f"""
        SELECT
            SUM(units_processed) AS total_units,
            SUM(hours_worked)    AS total_hours
        FROM labor
        WHERE {where}
    """
    df = pd.read_sql(query, engine)

    units = df["total_units"][0]
    hours = df["total_hours"][0]
    productivity = round((units / hours), 2) if hours > 0 else 0

    return {
        "label":       "Labor Productivity",
        "value":       productivity,
        "unit":        "units/hr",
        "total_units": int(units),
        "total_hours": round(float(hours), 1)
    }


# ============================================================
# KPI 4: OSHA Incident Rate
# Formula: (total incidents × 10,000) / total hours worked
# Per 10,000 hours — appropriate scale for smaller workforces
# and sub-annual reporting periods (vs 200K for enterprise annual)
# Alert: >1.5 | Warning: >1.0
# ============================================================
def get_osha_rate(start_date=None, end_date=None, shift=None):
    engine = get_engine()

    inc_filters = ["1=1"]
    if start_date: inc_filters.append(f"incident_date >= '{start_date}'")
    if end_date:   inc_filters.append(f"incident_date <= '{end_date}'")
    if shift and shift != "All": inc_filters.append(f"shift = '{shift}'")
    inc_where = " AND ".join(inc_filters)

    incidents_query = f"""
        SELECT COUNT(*) AS incident_count
        FROM safety_incidents
        WHERE {inc_where}
    """

    hr_filters = ["1=1"]
    if start_date: hr_filters.append(f"work_date >= '{start_date}'")
    if end_date:   hr_filters.append(f"work_date <= '{end_date}'")
    if shift and shift != "All": hr_filters.append(f"shift = '{shift}'")
    hr_where = " AND ".join(hr_filters)

    hours_query = f"""
        SELECT SUM(hours_worked) AS total_hours
        FROM labor
        WHERE {hr_where}
    """

    inc_df = pd.read_sql(incidents_query, engine)
    hr_df  = pd.read_sql(hours_query, engine)

    incidents   = inc_df["incident_count"][0]
    total_hours = hr_df["total_hours"][0]

    # Per 10,000 hours — calibrated for our 30-associate, 90-day dataset
    osha_rate = round((incidents * 10000) / total_hours, 2) if total_hours > 0 else 0

    return {
        "label":       "OSHA Incident Rate",
        "value":       osha_rate,
        "unit":        "per 10K hrs",
        "incidents":   int(incidents),
        "total_hours": round(float(total_hours), 1)
    }


# ============================================================
# KPI 5: Shipping On-Time %
# Formula: on-time shipments / total shipments × 100
# Alert: <92% | Warning: <96%
# ============================================================
def get_shipping_ontime(start_date=None, end_date=None):
    engine = get_engine()

    filters = ["1=1"]
    if start_date: filters.append(f"ship_date >= '{start_date}'")
    if end_date:   filters.append(f"ship_date <= '{end_date}'")
    where = " AND ".join(filters)

    query = f"""
        SELECT
            COUNT(*) AS total_shipments,
            COUNT(*) FILTER (WHERE status = 'on-time') AS ontime_shipments
        FROM shipments
        WHERE {where}
    """
    df = pd.read_sql(query, engine)

    total  = df["total_shipments"][0]
    ontime = df["ontime_shipments"][0]
    rate   = round((ontime / total * 100), 2) if total > 0 else 0

    return {
        "label":   "Shipping On-Time %",
        "value":   rate,
        "unit":    "%",
        "total":   int(total),
        "on_time": int(ontime)
    }


# ============================================================
# KPI 6: Receiving Cycle Time
# Formula: AVG(actual_time - scheduled_time) in hours
# Using shipments table as proxy for receiving cycle time
# Alert: >4 hrs | Warning: >3 hrs
# ============================================================
def get_receiving_cycle_time(start_date=None, end_date=None):
    engine = get_engine()

    filters = ["1=1"]
    if start_date: filters.append(f"ship_date >= '{start_date}'")
    if end_date:   filters.append(f"ship_date <= '{end_date}'")
    where = " AND ".join(filters)

    # EPOCH converts the time difference to seconds; divide by 3600 for hours
    query = f"""
        SELECT
            AVG(EXTRACT(EPOCH FROM (actual_time - scheduled_time)) / 3600)
            AS avg_cycle_hrs
        FROM shipments
        WHERE {where}
    """
    df = pd.read_sql(query, engine)

    avg_hrs = round(float(df["avg_cycle_hrs"][0]), 2)

    return {
        "label": "Receiving Cycle Time",
        "value": avg_hrs,
        "unit":  "hrs"
    }


# ============================================================
# MASTER FUNCTION — returns all 6 KPIs in one call
# dashboard.py will call this once per page load
# ============================================================
def get_all_kpis(start_date=None, end_date=None,
                 shift=None, department=None):
    return {
        "fulfillment":  get_fulfillment_rate(start_date, end_date, shift),
        "inventory":    get_inventory_accuracy(start_date, end_date),
        "productivity": get_labor_productivity(start_date, end_date, shift, department),
        "osha":         get_osha_rate(start_date, end_date, shift),
        "shipping":     get_shipping_ontime(start_date, end_date),
        "cycle_time":   get_receiving_cycle_time(start_date, end_date)
    }


# ============================================================
# QUICK TEST — run this file directly to verify all KPIs work
# This block only runs when you execute: python kpi_engine.py
# It does NOT run when dashboard.py imports this file
# ============================================================
if __name__ == "__main__":
    print("Running KPI Engine test...\n")
    kpis = get_all_kpis()
    for key, result in kpis.items():
        print(f"{result['label']}: {result['value']} {result['unit']}")