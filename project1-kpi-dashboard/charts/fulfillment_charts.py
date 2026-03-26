# ============================================================
# charts/fulfillment_charts.py
# All Plotly charts for the Fulfillment tab
# Called by dashboard.py Tab 2
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
# CHART 1: Fulfillment Status by Shift
# Bar chart — grouped bars showing fulfilled / late / failed
# per shift so supervisors can compare AM vs PM vs Night
# ============================================================
def chart_fulfillment_by_shift(start_date, end_date, shift):
    engine = get_engine()

    filters = [f"order_date >= '{start_date}'", f"order_date <= '{end_date}'"]
    if shift and shift != "All":
        filters.append(f"shift = '{shift}'")
    where = " AND ".join(filters)

    query = f"""
        SELECT
            shift,
            status,
            COUNT(*) AS order_count
        FROM orders
        WHERE {where}
        GROUP BY shift, status
        ORDER BY shift, status
    """
    df = pd.read_sql(query, engine)

    # Define consistent colors for each status
    color_map = {
        "fulfilled": "#28a745",
        "late":      "#ffc107",
        "failed":    "#dc3545"
    }

    fig = px.bar(
        df,
        x         = "shift",
        y         = "order_count",
        color     = "status",
        barmode   = "group",       # side-by-side bars, not stacked
        color_discrete_map = color_map,
        title     = "Order Status by Shift",
        labels    = {"order_count": "Number of Orders", "shift": "Shift"}
    )
    fig.update_layout(
        plot_bgcolor  = "rgba(0,0,0,0)",
        paper_bgcolor = "rgba(0,0,0,0)",
        font_color    = "#cccccc",
        legend_title  = "Status"
    )
    return fig


# ============================================================
# CHART 2: Top 10 SKUs by Late + Failed Orders
# Horizontal bar chart — shows which products cause the most
# fulfillment failures, sorted worst-to-best
# ============================================================
def chart_late_by_sku(start_date, end_date, shift):
    engine = get_engine()

    filters = [
        f"order_date >= '{start_date}'",
        f"order_date <= '{end_date}'",
        "status IN ('late', 'failed')"   # only problem orders
    ]
    if shift and shift != "All":
        filters.append(f"shift = '{shift}'")
    where = " AND ".join(filters)

    query = f"""
        SELECT
            sku,
            COUNT(*) AS problem_orders
        FROM orders
        WHERE {where}
        GROUP BY sku
        ORDER BY problem_orders DESC
        LIMIT 10
    """
    df = pd.read_sql(query, engine)

    fig = px.bar(
        df,
        x         = "problem_orders",
        y         = "sku",
        orientation = "h",           # horizontal bars
        title     = "Top 10 SKUs by Late + Failed Orders",
        labels    = {"problem_orders": "Late + Failed Orders", "sku": "SKU"},
        color     = "problem_orders",
        color_continuous_scale = "Reds"
    )
    fig.update_layout(
        plot_bgcolor  = "rgba(0,0,0,0)",
        paper_bgcolor = "rgba(0,0,0,0)",
        font_color    = "#cccccc",
        yaxis         = {"categoryorder": "total ascending"},
        coloraxis_showscale = False    # hide the color legend bar
    )
    return fig


# ============================================================
# CHART 3: Daily Fulfillment Rate Trend
# Line chart — fulfillment % over time so supervisors
# can spot deteriorating trends before they become crises
# ============================================================
def chart_fulfillment_trend(start_date, end_date, shift):
    engine = get_engine()

    filters = [f"order_date >= '{start_date}'", f"order_date <= '{end_date}'"]
    if shift and shift != "All":
        filters.append(f"shift = '{shift}'")
    where = " AND ".join(filters)

    query = f"""
        SELECT
            order_date,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status = 'fulfilled') AS fulfilled
        FROM orders
        WHERE {where}
        GROUP BY order_date
        ORDER BY order_date
    """
    df = pd.read_sql(query, engine)

    # Calculate daily fulfillment rate as a percentage
    df["fulfillment_rate"] = round(df["fulfilled"] / df["total"] * 100, 2)

    fig = px.line(
        df,
        x     = "order_date",
        y     = "fulfillment_rate",
        title = "Daily Fulfillment Rate Trend",
        labels = {"order_date": "Date", "fulfillment_rate": "Fulfillment Rate (%)"}
    )

    # Add a red dashed reference line at the 95% alert threshold
    fig.add_hline(
        y           = 95,
        line_dash   = "dash",
        line_color  = "#dc3545",
        annotation_text = "Alert Threshold (95%)"
    )
    # Add a yellow dashed line at the 98% warning threshold
    fig.add_hline(
        y           = 98,
        line_dash   = "dot",
        line_color  = "#ffc107",
        annotation_text = "Warning Threshold (98%)"
    )
    fig.update_traces(line_color="#4da6ff", line_width=2)
    fig.update_layout(
        plot_bgcolor  = "rgba(0,0,0,0)",
        paper_bgcolor = "rgba(0,0,0,0)",
        font_color    = "#cccccc",
        yaxis         = {"range": [85, 100]}   # zoom in on the relevant range
    )
    return fig