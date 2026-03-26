# ============================================================
# charts/inventory_charts.py
# All Plotly charts for the Inventory Accuracy tab
# Called by dashboard.py Tab 3
# ============================================================

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
# CHART 1: Inventory Accuracy Trend Over Time
# Line chart — weekly accuracy % so managers can spot
# whether counts are improving or deteriorating
# ============================================================
def chart_inventory_trend(start_date, end_date):
    engine = get_engine()

    query = f"""
        SELECT
            count_date,
            SUM(expected_count) AS expected,
            SUM(actual_count)   AS actual
        FROM inventory
        WHERE count_date >= '{start_date}'
          AND count_date <= '{end_date}'
        GROUP BY count_date
        ORDER BY count_date
    """
    df = pd.read_sql(query, engine)
    df["accuracy"] = round(df["actual"] / df["expected"] * 100, 2)

    fig = px.line(
        df,
        x     = "count_date",
        y     = "accuracy",
        title = "Inventory Accuracy Trend",
        labels = {"count_date": "Count Date", "accuracy": "Accuracy (%)"}
    )
    # Alert threshold line at 97%
    fig.add_hline(
        y                = 97,
        line_dash        = "dash",
        line_color       = "#dc3545",
        annotation_text  = "Alert (97%)"
    )
    # Warning threshold line at 99%
    fig.add_hline(
        y                = 99,
        line_dash        = "dot",
        line_color       = "#ffc107",
        annotation_text  = "Warning (99%)"
    )
    fig.update_traces(line_color="#4da6ff", line_width=2)
    fig.update_layout(
        plot_bgcolor  = "rgba(0,0,0,0)",
        paper_bgcolor = "rgba(0,0,0,0)",
        font_color    = "#cccccc",
        yaxis         = {"range": [90, 101]}
    )
    return fig


# ============================================================
# CHART 2: Bottom 10 SKUs by Accuracy %
# Horizontal bar — worst performing SKUs ranked so
# managers know exactly where to focus cycle counts
# ============================================================
def chart_worst_skus(start_date, end_date):
    engine = get_engine()

    query = f"""
        SELECT
            sku,
            SUM(expected_count) AS expected,
            SUM(actual_count)   AS actual
        FROM inventory
        WHERE count_date >= '{start_date}'
          AND count_date <= '{end_date}'
        GROUP BY sku
        ORDER BY (SUM(actual_count)::float / NULLIF(SUM(expected_count),0)) ASC
        LIMIT 10
    """
    df = pd.read_sql(query, engine)
    df["accuracy"] = round(df["actual"] / df["expected"] * 100, 2)

    fig = px.bar(
        df,
        x           = "accuracy",
        y           = "sku",
        orientation = "h",
        title       = "Bottom 10 SKUs by Inventory Accuracy",
        labels      = {"accuracy": "Accuracy (%)", "sku": "SKU"},
        color       = "accuracy",
        color_continuous_scale = "RdYlGn",   # red=bad, green=good
        range_color = [93, 100]
    )
    fig.update_layout(
        plot_bgcolor        = "rgba(0,0,0,0)",
        paper_bgcolor       = "rgba(0,0,0,0)",
        font_color          = "#cccccc",
        yaxis               = {"categoryorder": "total ascending"},
        coloraxis_showscale = False
    )
    return fig


# ============================================================
# CHART 3: Expected vs Actual Count by Category
# Grouped bar — compares expected vs actual inventory
# volumes across product categories
# ============================================================
def chart_accuracy_by_category(start_date, end_date):
    engine = get_engine()

    query = f"""
        SELECT
            category,
            SUM(expected_count) AS expected,
            SUM(actual_count)   AS actual
        FROM inventory
        WHERE count_date >= '{start_date}'
          AND count_date <= '{end_date}'
        GROUP BY category
        ORDER BY category
    """
    df = pd.read_sql(query, engine)

    # Reshape from wide to long format so Plotly can color by metric
    # Wide:  category | expected | actual
    # Long:  category | metric   | value   ← Plotly needs this shape
    df_long = df.melt(
        id_vars    = "category",
        value_vars = ["expected", "actual"],
        var_name   = "metric",
        value_name = "count"
    )

    fig = px.bar(
        df_long,
        x        = "category",
        y        = "count",
        color    = "metric",
        barmode  = "group",
        title    = "Expected vs Actual Count by Category",
        labels   = {"count": "Unit Count", "category": "Category"},
        color_discrete_map = {
            "expected": "#4da6ff",
            "actual":   "#28a745"
        }
    )
    fig.update_layout(
        plot_bgcolor  = "rgba(0,0,0,0)",
        paper_bgcolor = "rgba(0,0,0,0)",
        font_color    = "#cccccc",
        legend_title  = "Count Type"
    )
    return fig