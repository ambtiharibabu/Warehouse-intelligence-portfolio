# ============================================================
# export_utils.py
# Builds an Excel workbook from the current dashboard data
# and returns it as a BytesIO object for Streamlit download.
#
# The workbook has 4 sheets:
#   1. KPI Summary     — the 6 headline numbers
#   2. Orders          — raw order data for the date range
#   3. Labor           — associate records for the period
#   4. Shipments       — shipment records for the period
# ============================================================

import pandas as pd
import io
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from dotenv import load_dotenv
import os
from datetime import date

load_dotenv()

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


def build_excel_export(kpis, start_date, end_date, shift, department):
    """
    Takes the evaluated KPI dict and filter parameters.
    Queries PostgreSQL for the underlying data matching
    those filters, then packages everything into a
    multi-sheet Excel file returned as a BytesIO buffer.
    """
    engine = get_engine()

    # ── Sheet 1: KPI Summary ──────────────────────────────
    # Flatten the KPI dict into a clean table with one row
    # per KPI showing value, unit, and status
    kpi_rows = []
    for key, data in kpis.items():
        kpi_rows.append({
            "KPI":    data["label"],
            "Value":  data["value"],
            "Unit":   data["unit"],
            "Status": data["status"].upper(),
        })
    kpi_df = pd.DataFrame(kpi_rows)

    # ── Sheet 2: Orders ───────────────────────────────────
    order_filters = [
        f"order_date >= '{start_date}'",
        f"order_date <= '{end_date}'"
    ]
    if shift and shift != "All":
        order_filters.append(f"shift = '{shift}'")
    order_where = " AND ".join(order_filters)

    orders_df = pd.read_sql(
        f"SELECT * FROM orders WHERE {order_where} ORDER BY order_date DESC",
        engine
    )

    # ── Sheet 3: Labor ────────────────────────────────────
    labor_filters = [
        f"work_date >= '{start_date}'",
        f"work_date <= '{end_date}'"
    ]
    if shift and shift != "All":
        labor_filters.append(f"shift = '{shift}'")
    if department and department != "All":
        labor_filters.append(f"department = '{department}'")
    labor_where = " AND ".join(labor_filters)

    labor_df = pd.read_sql(
        f"SELECT * FROM labor WHERE {labor_where} ORDER BY work_date DESC",
        engine
    )

    # ── Sheet 4: Shipments ────────────────────────────────
    ship_filters = [
        f"ship_date >= '{start_date}'",
        f"ship_date <= '{end_date}'"
    ]
    ship_where = " AND ".join(ship_filters)

    shipments_df = pd.read_sql(
        f"SELECT * FROM shipments WHERE {ship_where} ORDER BY ship_date DESC",
        engine
    )

    # ── Write all 4 sheets to an in-memory Excel file ─────
    # BytesIO is an in-memory file buffer — no disk writes needed.
    # ExcelWriter handles the multi-sheet structure.
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        kpi_df.to_excel(writer,       sheet_name="KPI Summary",  index=False)
        orders_df.to_excel(writer,    sheet_name="Orders",        index=False)
        labor_df.to_excel(writer,     sheet_name="Labor",         index=False)
        shipments_df.to_excel(writer, sheet_name="Shipments",     index=False)

    # Move buffer position back to the start so Streamlit
    # can read it from the beginning when serving the download
    buffer.seek(0)
    return buffer