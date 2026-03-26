# ============================================================
# charts/shipping_charts.py
# All Plotly charts for the Shipping & Receiving tab
# Called by dashboard.py Tab 6
# ============================================================

import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from dotenv import load_dotenv
import os

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


# ============================================================
# CHART 1: On-Time Rate by Carrier
# Horizontal bar — ranks carriers by reliability so
# procurement can use this in carrier negotiations
# ============================================================
def chart_ontime_by_carrier(start_date, end_date):
    engine = get_engine()

    # AFTER — wrap in subquery so alias is visible to ORDER BY
    query = f"""
    SELECT * FROM (
        SELECT
            carrier,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status = 'on-time') AS on_time
        FROM shipments
        WHERE ship_date >= '{start_date}'
          AND ship_date <= '{end_date}'
        GROUP BY carrier
    ) sub
    ORDER BY on_time::float / NULLIF(total, 0) DESC
    """

    df = pd.read_sql(query, engine)
    df["on_time_pct"] = round(df["on_time"] / df["total"] * 100, 2)

    fig = px.bar(
        df,
        x           = "on_time_pct",
        y           = "carrier",
        orientation = "h",
        title       = "On-Time Rate by Carrier",
        labels      = {"on_time_pct": "On-Time %", "carrier": "Carrier"},
        color       = "on_time_pct",
        color_continuous_scale = "RdYlGn",
        range_color = [85, 100]
    )
    fig.add_vline(
        x               = 92,
        line_dash       = "dash",
        line_color      = "#dc3545",
        annotation_text = "Alert (92%)"
    )
    fig.add_vline(
        x               = 96,
        line_dash       = "dot",
        line_color      = "#ffc107",
        annotation_text = "Warning (96%)"
    )
    fig.update_layout(
        plot_bgcolor        = "rgba(0,0,0,0)",
        paper_bgcolor       = "rgba(0,0,0,0)",
        font_color          = "#cccccc",
        yaxis               = {"categoryorder": "total ascending"},
        coloraxis_showscale = False,
        xaxis               = {"range": [85, 100]}
    )
    return fig


# ============================================================
# CHART 2: Daily Shipment Volume — On-Time vs Late
# Stacked bar — shows total daily volume with color split
# so you can spot high-volume days that coincide with delays
# ============================================================
def chart_daily_shipments(start_date, end_date):
    engine = get_engine()

    query = f"""
        SELECT
            ship_date,
            status,
            COUNT(*) AS shipment_count
        FROM shipments
        WHERE ship_date >= '{start_date}'
          AND ship_date <= '{end_date}'
        GROUP BY ship_date, status
        ORDER BY ship_date
    """
    df = pd.read_sql(query, engine)

    color_map = {
        "on-time": "#28a745",
        "late":    "#dc3545"
    }

    fig = px.bar(
        df,
        x        = "ship_date",
        y        = "shipment_count",
        color    = "status",
        barmode  = "stack",
        title    = "Daily Shipment Volume: On-Time vs Late",
        labels   = {"shipment_count": "Shipments", "ship_date": "Date"},
        color_discrete_map = color_map
    )
    fig.update_layout(
        plot_bgcolor  = "rgba(0,0,0,0)",
        paper_bgcolor = "rgba(0,0,0,0)",
        font_color    = "#cccccc",
        legend_title  = "Status"
    )
    return fig


# ============================================================
# CHART 3: Delay Distribution — Histogram
# Shows how late shipments are distributed by delay length
# Helps answer: "are delays mostly minor or seriously late?"
# ============================================================
def chart_delay_distribution(start_date, end_date):
    engine = get_engine()

    # Only look at late shipments — on-time ones have 0 delay
    query = f"""
        SELECT
            EXTRACT(EPOCH FROM (actual_time - scheduled_time)) / 60
                AS delay_minutes
        FROM shipments
        WHERE ship_date >= '{start_date}'
          AND ship_date <= '{end_date}'
          AND status = 'late'
        ORDER BY delay_minutes
    """
    df = pd.read_sql(query, engine)

    fig = px.histogram(
        df,
        x      = "delay_minutes",
        nbins  = 20,           # number of buckets
        title  = "Late Shipment Delay Distribution",
        labels = {"delay_minutes": "Delay (minutes)", "count": "Shipments"},
        color_discrete_sequence = ["#dc3545"]
    )
    fig.update_layout(
        plot_bgcolor  = "rgba(0,0,0,0)",
        paper_bgcolor = "rgba(0,0,0,0)",
        font_color    = "#cccccc",
        yaxis_title   = "Number of Shipments",
        bargap        = 0.1
    )
    return fig


# ============================================================
# CHART 4: Avg Delay by Carrier
# Bar chart — shows which carriers cause the longest delays
# when they ARE late, not just how often
# ============================================================
def chart_avg_delay_by_carrier(start_date, end_date):
    engine = get_engine()

    query = f"""
        SELECT
            carrier,
            ROUND(
                AVG(EXTRACT(EPOCH FROM (actual_time - scheduled_time)) / 60)::numeric
            , 1) AS avg_delay_mins
        FROM shipments
        WHERE ship_date >= '{start_date}'
          AND ship_date <= '{end_date}'
          AND status = 'late'
        GROUP BY carrier
        ORDER BY avg_delay_mins DESC
    """
    df = pd.read_sql(query, engine)

    fig = px.bar(
        df,
        x     = "carrier",
        y     = "avg_delay_mins",
        title = "Avg Delay by Carrier (Late Shipments Only)",
        labels = {"avg_delay_mins": "Avg Delay (mins)", "carrier": "Carrier"},
        color = "avg_delay_mins",
        color_continuous_scale = "Reds"
    )
    fig.update_layout(
        plot_bgcolor        = "rgba(0,0,0,0)",
        paper_bgcolor       = "rgba(0,0,0,0)",
        font_color          = "#cccccc",
        coloraxis_showscale = False
    )
    return fig