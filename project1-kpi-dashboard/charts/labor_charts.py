# ============================================================
# charts/labor_charts.py
# All Plotly charts for the Labor Productivity tab
# Called by dashboard.py Tab 4
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
# CHART 1: Top 10 Associates by Productivity
# FIX: cast entire division to ::numeric before ROUND()
# PostgreSQL ROUND(x,2) only accepts numeric, not float
# ============================================================
def chart_top_associates(start_date, end_date, shift, department):
    engine = get_engine()

    filters = [f"work_date >= '{start_date}'", f"work_date <= '{end_date}'"]
    if shift and shift != "All":
        filters.append(f"shift = '{shift}'")
    if department and department != "All":
        filters.append(f"department = '{department}'")
    where = " AND ".join(filters)

    query = f"""
        SELECT
            associate_id,
            ROUND(
                (SUM(units_processed) / NULLIF(SUM(hours_worked), 0))::numeric
            , 2) AS productivity
        FROM labor
        WHERE {where}
        GROUP BY associate_id
        ORDER BY productivity DESC
        LIMIT 10
    """
    df = pd.read_sql(query, engine)

    fig = px.bar(
        df,
        x           = "productivity",
        y           = "associate_id",
        orientation = "h",
        title       = "Top 10 Associates by Productivity",
        labels      = {"productivity": "Units / Hr", "associate_id": "Associate"},
        color       = "productivity",
        color_continuous_scale = "Greens"
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
# CHART 1b: Bottom 10 Associates by Productivity
# ============================================================
def chart_bottom_associates(start_date, end_date, shift, department):
    engine = get_engine()

    filters = [f"work_date >= '{start_date}'", f"work_date <= '{end_date}'"]
    if shift and shift != "All":
        filters.append(f"shift = '{shift}'")
    if department and department != "All":
        filters.append(f"department = '{department}'")
    where = " AND ".join(filters)

    query = f"""
        SELECT
            associate_id,
            ROUND(
                (SUM(units_processed) / NULLIF(SUM(hours_worked), 0))::numeric
            , 2) AS productivity
        FROM labor
        WHERE {where}
        GROUP BY associate_id
        ORDER BY productivity ASC
        LIMIT 10
    """
    df = pd.read_sql(query, engine)

    fig = px.bar(
        df,
        x           = "productivity",
        y           = "associate_id",
        orientation = "h",
        title       = "Bottom 10 Associates by Productivity",
        labels      = {"productivity": "Units / Hr", "associate_id": "Associate"},
        color       = "productivity",
        color_continuous_scale = "Reds_r"
    )
    fig.update_layout(
        plot_bgcolor        = "rgba(0,0,0,0)",
        paper_bgcolor       = "rgba(0,0,0,0)",
        font_color          = "#cccccc",
        yaxis               = {"categoryorder": "total descending"},
        coloraxis_showscale = False
    )
    return fig


# ============================================================
# CHART 2: Productivity by Department
# ============================================================
def chart_productivity_by_department(start_date, end_date, shift):
    engine = get_engine()

    filters = [f"work_date >= '{start_date}'", f"work_date <= '{end_date}'"]
    if shift and shift != "All":
        filters.append(f"shift = '{shift}'")
    where = " AND ".join(filters)

    query = f"""
        SELECT
            department,
            ROUND(
                (SUM(units_processed) / NULLIF(SUM(hours_worked), 0))::numeric
            , 2) AS avg_productivity
        FROM labor
        WHERE {where}
        GROUP BY department
        ORDER BY avg_productivity DESC
    """
    df = pd.read_sql(query, engine)

    fig = px.bar(
        df,
        x     = "department",
        y     = "avg_productivity",
        title = "Avg Productivity by Department",
        labels = {"avg_productivity": "Units / Hr", "department": "Department"},
        color = "avg_productivity",
        color_continuous_scale = "Blues"
    )
    fig.add_hline(
        y               = 85,
        line_dash       = "dash",
        line_color      = "#dc3545",
        annotation_text = "Alert (85 u/hr)"
    )
    fig.add_hline(
        y               = 95,
        line_dash       = "dot",
        line_color      = "#ffc107",
        annotation_text = "Warning (95 u/hr)"
    )
    fig.update_layout(
        plot_bgcolor        = "rgba(0,0,0,0)",
        paper_bgcolor       = "rgba(0,0,0,0)",
        font_color          = "#cccccc",
        coloraxis_showscale = False
    )
    return fig


# ============================================================
# CHART 3: Shift × Department Productivity Heatmap
# ============================================================
def chart_shift_department_heatmap(start_date, end_date):
    engine = get_engine()

    query = f"""
        SELECT
            shift,
            department,
            ROUND(
                (SUM(units_processed) / NULLIF(SUM(hours_worked), 0))::numeric
            , 2) AS avg_productivity
        FROM labor
        WHERE work_date >= '{start_date}'
          AND work_date <= '{end_date}'
        GROUP BY shift, department
        ORDER BY shift, department
    """
    df = pd.read_sql(query, engine)

    pivot = df.pivot(
        index   = "department",
        columns = "shift",
        values  = "avg_productivity"
    )

    fig = px.imshow(
        pivot,
        title                  = "Productivity Heatmap: Shift × Department",
        labels                 = {"color": "Units/Hr"},
        color_continuous_scale = "RdYlGn",
        aspect                 = "auto",
        text_auto              = True
    )
    fig.update_layout(
        plot_bgcolor  = "rgba(0,0,0,0)",
        paper_bgcolor = "rgba(0,0,0,0)",
        font_color    = "#cccccc",
        xaxis_title   = "Shift",
        yaxis_title   = "Department"
    )
    return fig