# ============================================================
# charts/safety_charts.py
# All Plotly charts for the Safety & Compliance tab
# Called by dashboard.py Tab 5
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
# CHART 1: Incident Breakdown by Type and Severity
# Two donut charts side by side — type distribution and
# severity distribution give a quick risk profile
# ============================================================
def chart_incident_by_type(start_date, end_date, shift):
    engine = get_engine()

    filters = [f"incident_date >= '{start_date}'",
               f"incident_date <= '{end_date}'"]
    if shift and shift != "All":
        filters.append(f"shift = '{shift}'")
    where = " AND ".join(filters)

    query = f"""
        SELECT incident_type, COUNT(*) AS count
        FROM safety_incidents
        WHERE {where}
        GROUP BY incident_type
        ORDER BY count DESC
    """
    df = pd.read_sql(query, engine)

    color_map = {
        "near-miss":  "#ffc107",
        "injury":     "#dc3545",
        "violation":  "#fd7e14"
    }

    fig = px.pie(
        df,
        names  = "incident_type",
        values = "count",
        title  = "Incidents by Type",
        hole   = 0.45,          # makes it a donut chart
        color  = "incident_type",
        color_discrete_map = color_map
    )
    fig.update_layout(
        plot_bgcolor  = "rgba(0,0,0,0)",
        paper_bgcolor = "rgba(0,0,0,0)",
        font_color    = "#cccccc"
    )
    return fig


def chart_incident_by_severity(start_date, end_date, shift):
    engine = get_engine()

    filters = [f"incident_date >= '{start_date}'",
               f"incident_date <= '{end_date}'"]
    if shift and shift != "All":
        filters.append(f"shift = '{shift}'")
    where = " AND ".join(filters)

    query = f"""
        SELECT severity, COUNT(*) AS count
        FROM safety_incidents
        WHERE {where}
        GROUP BY severity
        ORDER BY count DESC
    """
    df = pd.read_sql(query, engine)

    color_map = {
        "low":    "#28a745",
        "medium": "#ffc107",
        "high":   "#dc3545"
    }

    fig = px.pie(
        df,
        names  = "severity",
        values = "count",
        title  = "Incidents by Severity",
        hole   = 0.45,
        color  = "severity",
        color_discrete_map = color_map
    )
    fig.update_layout(
        plot_bgcolor  = "rgba(0,0,0,0)",
        paper_bgcolor = "rgba(0,0,0,0)",
        font_color    = "#cccccc"
    )
    return fig


# ============================================================
# CHART 2: Incidents by Shift — Bar chart
# Shows which shift has the most safety events
# ============================================================
def chart_incidents_by_shift(start_date, end_date):
    engine = get_engine()

    query = f"""
        SELECT
            shift,
            severity,
            COUNT(*) AS count
        FROM safety_incidents
        WHERE incident_date >= '{start_date}'
          AND incident_date <= '{end_date}'
        GROUP BY shift, severity
        ORDER BY shift
    """
    df = pd.read_sql(query, engine)

    color_map = {
        "low":    "#28a745",
        "medium": "#ffc107",
        "high":   "#dc3545"
    }

    fig = px.bar(
        df,
        x        = "shift",
        y        = "count",
        color    = "severity",
        barmode  = "stack",
        title    = "Incidents by Shift and Severity",
        labels   = {"count": "Incident Count", "shift": "Shift"},
        color_discrete_map = color_map
    )
    fig.update_layout(
        plot_bgcolor  = "rgba(0,0,0,0)",
        paper_bgcolor = "rgba(0,0,0,0)",
        font_color    = "#cccccc",
        legend_title  = "Severity"
    )
    return fig


# ============================================================
# CHART 3: OSHA Rate Trend — Rolling monthly calculation
# Plots how the incident rate changes over time using
# a 30-day rolling window
# ============================================================
def chart_osha_trend(start_date, end_date):
    engine = get_engine()

    # Get daily incident counts
    inc_query = f"""
        SELECT
            incident_date AS date,
            COUNT(*) AS incidents
        FROM safety_incidents
        WHERE incident_date >= '{start_date}'
          AND incident_date <= '{end_date}'
        GROUP BY incident_date
        ORDER BY incident_date
    """

    # Get daily labor hours
    hr_query = f"""
        SELECT
            work_date AS date,
            SUM(hours_worked) AS hours
        FROM labor
        WHERE work_date >= '{start_date}'
          AND work_date <= '{end_date}'
        GROUP BY work_date
        ORDER BY work_date
    """

    inc_df = pd.read_sql(inc_query, engine)
    hr_df  = pd.read_sql(hr_query, engine)

    # Merge on date — outer join keeps all dates from both tables
    df = pd.merge(hr_df, inc_df, on="date", how="left")
    df["incidents"] = df["incidents"].fillna(0)

    # Rolling 30-day window for a smoother, more meaningful trend
    df["rolling_incidents"] = df["incidents"].rolling(30, min_periods=1).sum()
    df["rolling_hours"]     = df["hours"].rolling(30, min_periods=1).sum()
    df["osha_rate"] = round(
        (df["rolling_incidents"] * 10000) / df["rolling_hours"].replace(0, 1), 2
    )

    fig = px.line(
        df,
        x     = "date",
        y     = "osha_rate",
        title = "30-Day Rolling OSHA Rate (per 10K hrs)",
        labels = {"date": "Date", "osha_rate": "OSHA Rate"}
    )
    fig.add_hline(
        y               = 1.5,
        line_dash       = "dash",
        line_color      = "#dc3545",
        annotation_text = "Alert (1.5)"
    )
    fig.add_hline(
        y               = 1.0,
        line_dash       = "dot",
        line_color      = "#ffc107",
        annotation_text = "Warning (1.0)"
    )
    fig.update_traces(line_color="#4da6ff", line_width=2)
    fig.update_layout(
        plot_bgcolor  = "rgba(0,0,0,0)",
        paper_bgcolor = "rgba(0,0,0,0)",
        font_color    = "#cccccc"
    )
    return fig


# ============================================================
# TABLE: Full Incident Log
# Returns a clean DataFrame for st.dataframe() in dashboard
# ============================================================
def get_incident_log(start_date, end_date, shift):
    engine = get_engine()

    filters = [f"incident_date >= '{start_date}'",
               f"incident_date <= '{end_date}'"]
    if shift and shift != "All":
        filters.append(f"shift = '{shift}'")
    where = " AND ".join(filters)

    query = f"""
        SELECT
            incident_id     AS "ID",
            incident_date   AS "Date",
            shift           AS "Shift",
            incident_type   AS "Type",
            severity        AS "Severity"
        FROM safety_incidents
        WHERE {where}
        ORDER BY incident_date DESC
    """
    return pd.read_sql(query, engine)