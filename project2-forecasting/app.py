"""
app.py
------
Project 2 — Inventory Forecasting & Lean Waste Detection Engine
Streamlit operational dashboard.

Six pages, one sidebar:
    🏠  Home              — welcome screen, pipeline summary, KPI cards
    📈  Demand Forecast   — Prophet forecast chart per SKU + data table
    ⚠️   Stockout Risk     — risk tier breakdown + filterable SKU table
    🔧  Reorder Params    — EOQ/ROP comparison charts + savings table
    🗑️   Lean Waste        — waste flag charts + drill-down table
    📦  ERP Export        — SAP flat file preview + download buttons

Filters available:
    Sidebar  → global category filter (flows through every page)
    Forecast → history window slider (30/60/90/180/365 days)
    Reorder  → minimum savings threshold slider
    Waste    → minimum annual waste threshold slider

How to run:
    streamlit run app.py
"""

import os
import sys
import warnings
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from sqlalchemy import text
from datetime import date, datetime
from pathlib import Path

# Suppress Prophet/Stan noise that sometimes leaks into Streamlit logs
warnings.filterwarnings("ignore")

# Make sure Python can find db/connection.py from this file's location
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db.connection import get_engine


# ── This must be the very first Streamlit call in the file ──────────────────
st.set_page_config(
    page_title            = "Warehouse Intelligence | P2",
    page_icon             = "🏭",
    layout                = "wide",
    initial_sidebar_state = "expanded",
)


# ── Visual theme: dark navy background, amber (#F0C040) as the accent colour ─
st.markdown("""
<style>
    /* ── Page background ── */
    .stApp { background-color: #0F1923; }

    /* ── Sidebar: darker gradient panel on the left ── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1A2634 0%, #0F1923 100%);
        border-right: 1px solid #2E4057;
    }

    /* ── Make all body text readable on the dark background ── */
    .stApp, .stMarkdown, p, h1, h2, h3, label {
        color: #E8EDF2 !important;
    }

    /* ── KPI metric cards ── */
    [data-testid="stMetric"] {
        background: #1A2634;
        border: 1px solid #2E4057;
        border-radius: 8px;
        padding: 12px 16px;
    }
    [data-testid="stMetricLabel"] { color: #8FA3B1 !important; font-size: 12px; }
    [data-testid="stMetricValue"] { color: #F0C040 !important; font-size: 24px; font-weight: 700; }
    [data-testid="stMetricDelta"] { font-size: 12px; }

    /* ── Tab bar: inactive = grey, active = amber underline ── */
    [data-testid="stTabs"] button {
        color: #8FA3B1 !important;
        font-weight: 600;
    }
    [data-testid="stTabs"] button[aria-selected="true"] {
        color: #F0C040 !important;
        border-bottom: 2px solid #F0C040;
    }

    /* ── Section headers: left amber border, navy background ── */
    .section-header {
        background: linear-gradient(90deg, #1F3864 0%, #1A2634 100%);
        border-left: 4px solid #F0C040;
        padding: 10px 16px;
        border-radius: 0 6px 6px 0;
        margin: 16px 0 12px 0;
        font-weight: 700;
        font-size: 15px;
        color: #F0C040 !important;
    }

    /* ── Info box: blue border, used for explanatory text ── */
    .info-box {
        background: #1A2634;
        border: 1px solid #2E75B6;
        border-radius: 8px;
        padding: 14px 18px;
        margin: 8px 0;
        font-size: 13px;
        color: #C5D5E4 !important;
    }

    /* ── Warning box: amber border, used for action callouts ── */
    .warn-box {
        background: #2A1F0F;
        border: 1px solid #F0C040;
        border-radius: 8px;
        padding: 14px 18px;
        margin: 8px 0;
        font-size: 13px;
        color: #F0C040 !important;
    }

    /* ── Filter active banner ── */
    .filter-banner {
        background: #0D2137;
        border: 1px solid #2E75B6;
        border-left: 4px solid #2E75B6;
        border-radius: 0 6px 6px 0;
        padding: 8px 14px;
        margin: 8px 0 12px 0;
        font-size: 12px;
        color: #8FA3B1 !important;
    }

    /* ── Risk badges: coloured pill labels ── */
    .badge-critical { background:#C0392B; color:white; padding:3px 10px;
                      border-radius:12px; font-size:11px; font-weight:700; }
    .badge-high     { background:#E67E22; color:white; padding:3px 10px;
                      border-radius:12px; font-size:11px; font-weight:700; }
    .badge-medium   { background:#F39C12; color:white; padding:3px 10px;
                      border-radius:12px; font-size:11px; font-weight:700; }
    .badge-low      { background:#27AE60; color:white; padding:3px 10px;
                      border-radius:12px; font-size:11px; font-weight:700; }

    /* ── Download buttons: amber outline, inverts on hover ── */
    .stDownloadButton button {
        background: #1F3864;
        color: #F0C040 !important;
        border: 1px solid #F0C040;
        border-radius: 6px;
        font-weight: 600;
    }
    .stDownloadButton button:hover {
        background: #F0C040;
        color: #0F1923 !important;
    }

    /* ── Selectbox and multiselect: dark background ── */
    [data-testid="stSelectbox"] > div > div {
        background: #1A2634;
        border: 1px solid #2E4057;
        color: #E8EDF2;
    }
    div[data-baseweb="select"] span { color: #E8EDF2 !important; }

    /* ── Slider: amber accent ── */
    [data-testid="stSlider"] > div > div > div {
        background: #F0C040 !important;
    }

    /* ── Rounded corners on dataframes and charts ── */
    [data-testid="stDataFrame"] { border-radius: 8px; }
    .js-plotly-plot { border-radius: 8px; }

    /* ── Sidebar brand title ── */
    .sidebar-title {
        font-size: 20px;
        font-weight: 800;
        color: #F0C040 !important;
        letter-spacing: 1px;
    }

    /* ── Sidebar filter section label ── */
    .filter-label {
        font-size: 11px;
        font-weight: 700;
        color: #8FA3B1 !important;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin: 4px 0 6px 0;
    }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# CHART THEME
# Only sets background colour and font.
# Individual charts set their own xaxis, yaxis, legend, margin — keeping
# CHART_THEME minimal avoids Plotly's "multiple values" error when we also
# pass those same keys explicitly in update_layout().
# ════════════════════════════════════════════════════════════════════════════
CHART_THEME = dict(
    paper_bgcolor = "#1A2634",
    plot_bgcolor  = "#1A2634",
    font          = dict(color="#E8EDF2", family="Arial"),
)

# Reusable grid colour for axis definitions
GRID = "#2E4057"


# ════════════════════════════════════════════════════════════════════════════
# DATABASE LOADERS
# Each function returns one DataFrame from PostgreSQL.
# @st.cache_data(ttl=300) reuses the result for 5 minutes so page navigation
# feels instant — no database round-trip on every click.
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def load_forecasts():
    """All 600 Prophet forecast rows — 20 SKUs × 30 days."""
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text("""
            SELECT sku, forecast_date, yhat, yhat_lower, yhat_upper
            FROM forecasts
            ORDER BY sku, forecast_date
        """), conn)


@st.cache_data(ttl=300)
def load_reorder_params():
    """reorder_params joined to sku_master so we have category on every row."""
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text("""
            SELECT r.*, s.category
            FROM reorder_params r
            JOIN sku_master s USING (sku)
            ORDER BY potential_savings_usd DESC
        """), conn)


@st.cache_data(ttl=300)
def load_waste_flags():
    """All Lean waste flags, highest annual cost first."""
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text("""
            SELECT * FROM lean_waste_flags
            ORDER BY annual_waste_usd DESC
        """), conn)


@st.cache_data(ttl=300)
def load_order_history():
    """
    Daily order counts per SKU — the raw demand signal Prophet trained on.
    One row per SKU per date with a count of how many orders arrived.
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text("""
            SELECT sku, order_date, COUNT(order_id) AS daily_orders
            FROM orders
            GROUP BY sku, order_date
            ORDER BY sku, order_date
        """), conn)


@st.cache_data(ttl=300)
def load_erp_export():
    """
    SAP MM MRP II export view — same values as the CSV file but pulled
    live from the database for the in-app preview table.
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text("""
            SELECT
                sku                                               AS "MATNR",
                'WH01'                                           AS "WERKS",
                GREATEST(1, ROUND(optimal_rop::numeric, 0)::int) AS "MINBE",
                GREATEST(0, ROUND(safety_stock::numeric, 0)::int)AS "EISBE",
                GREATEST(1, ROUND(optimal_rop::numeric*3,0)::int)AS "MABST",
                GREATEST(1, ROUND(eoq::numeric*0.5, 0)::int)     AS "BSTMI",
                GREATEST(1, ROUND(eoq::numeric*2,   0)::int)     AS "BSTMA"
            FROM reorder_params
            ORDER BY sku
        """), conn)


# ════════════════════════════════════════════════════════════════════════════
# HELPER — filter active banner
# Shows a small blue strip whenever a filter is narrowing the view.
# Keeps users aware they're not seeing the full dataset.
# ════════════════════════════════════════════════════════════════════════════
def show_filter_banner(selected_cats, sku_count, extra=""):
    """Renders a subtle banner when the category filter is active."""
    if len(selected_cats) < 5:
        cats_str = ", ".join(selected_cats)
        st.markdown(
            f'<div class="filter-banner">'
            f'🔍 <b>Category filter active:</b> {cats_str} '
            f'— {sku_count} SKUs shown{extra}'
            f'</div>',
            unsafe_allow_html=True
        )


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# Returns both the selected page name AND the active category filter list.
# Every page function receives selected_cats so it can narrow its data.
# ════════════════════════════════════════════════════════════════════════════
def render_sidebar():
    with st.sidebar:
        # Brand header
        st.markdown(
            '<p class="sidebar-title">🏭 WAREHOUSE<br>INTELLIGENCE</p>',
            unsafe_allow_html=True
        )
        st.markdown(
            "**Project 2 — Forecasting &<br>Lean Waste Engine**",
            unsafe_allow_html=True
        )
        st.markdown("---")

        # Page navigation radio buttons
        page = st.radio(
            "Navigate",
            options = [
                "🏠  Home",
                "📈  Demand Forecast",
                "⚠️   Stockout Risk",
                "🔧  Reorder Parameters",
                "🗑️   Lean Waste",
                "📦  ERP Export",
            ],
            label_visibility = "collapsed",
        )

        st.markdown("---")

        # ── Global category filter ────────────────────────────────────────
        # Selecting categories here narrows every page simultaneously.
        # All 5 selected by default means no filtering is applied.
        st.markdown(
            '<p class="filter-label">🔍 Filter by Category</p>',
            unsafe_allow_html=True
        )

        all_cats = [
            "Electronics", "Consumables", "Equipment",
            "Packaging", "Spare Parts"
        ]

        selected_cats = st.multiselect(
            "Categories",
            options          = all_cats,
            default          = all_cats,
            label_visibility = "collapsed",
            help             = (
                "Narrows all pages to the selected SKU categories. "
                "Deselect a category to exclude its SKUs from every view."
            ),
        )

        # Safety net — if the user accidentally deselects everything, show all
        if not selected_cats:
            selected_cats = all_cats
            st.caption("⚠️ Nothing selected — showing all categories.")

        # Small pill showing how many SKUs are currently in scope
        active_count = 20 if len(selected_cats) == 5 else len(selected_cats) * 4
        filter_colour = "#27AE60" if len(selected_cats) == 5 else "#F0C040"
        st.markdown(
            f'<p style="font-size:11px; color:{filter_colour}; margin:4px 0;">'
            f'{"All 20 SKUs visible" if len(selected_cats) == 5 else f"~{active_count} SKUs in scope"}'
            f'</p>',
            unsafe_allow_html=True
        )

        st.markdown("---")

        # Metadata footer
        st.markdown(
            '<p style="font-size:11px; color:#4A6580;">'
            f'Last run: {datetime.now().strftime("%Y-%m-%d %H:%M")}<br>'
            'DB: DigitalOcean PostgreSQL<br>'
            'Model: Facebook Prophet 1.3.0<br>'
            'SKUs monitored: 20'
            '</p>',
            unsafe_allow_html=True
        )

    return page, selected_cats


# ════════════════════════════════════════════════════════════════════════════
# PAGE 1 — HOME
# ════════════════════════════════════════════════════════════════════════════
def page_home(selected_cats):
    # Hero banner
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1F3864 0%,#0F1923 100%);
                border-radius:12px; padding:32px 36px; margin-bottom:24px;
                border:1px solid #2E4057;">
        <h1 style="color:#F0C040 !important; font-size:32px; margin:0;
                   letter-spacing:1px;">
            🏭 Inventory Forecasting & Lean Waste Engine
        </h1>
        <p style="color:#8FA3B1; font-size:15px; margin:10px 0 0 0;">
            Reads live warehouse data from PostgreSQL → runs ML demand forecasting
            → optimises reorder parameters → surfaces Lean waste
            → exports SAP-ready files.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Load data and apply category filter
    reorder_df  = load_reorder_params()
    waste_df    = load_waste_flags()
    forecast_df = load_forecasts()

    reorder_df = reorder_df[reorder_df["category"].isin(selected_cats)]
    waste_df   = waste_df[waste_df["sku"].isin(reorder_df["sku"])]

    # Show filter banner if not all categories are selected
    show_filter_banner(selected_cats, len(reorder_df))

    total_waste   = waste_df["annual_waste_usd"].sum()
    total_savings = reorder_df["potential_savings_usd"].sum()
    at_risk       = len(reorder_df[
        reorder_df["stockout_risk"].isin(["Critical", "High"])
    ])

    # KPI cards
    st.markdown(
        '<p class="section-header">📊 Pipeline Output Summary</p>',
        unsafe_allow_html=True
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("SKUs in Scope",        str(len(reorder_df)),
              help="SKUs matching current category filter")
    c2.metric("Forecast Rows",        f"{len(forecast_df):,}",
              help="30-day Prophet forecasts generated (20 SKUs × 30 days)")
    c3.metric("SKUs At Risk",         str(at_risk),
              help="SKUs flagged Critical or High stockout risk")
    c4.metric("Reorder Savings",      f"${total_savings:,.0f}",
              help="Estimated annual savings from ROP optimisation")
    c5.metric("Annual Waste Detected",f"${total_waste:,.0f}",
              help="Total Lean waste cost across all flag types")

    st.markdown("<br>", unsafe_allow_html=True)

    col_left, col_right = st.columns([1.2, 1])

    with col_left:
        st.markdown(
            '<p class="section-header">🔄 Pipeline Architecture</p>',
            unsafe_allow_html=True
        )
        st.markdown("""
        <div class="info-box">
        <b>Data flows end-to-end without manual intervention:</b><br><br>
        📂 <b>PostgreSQL</b> (DigitalOcean Droplet)<br>
        &nbsp;&nbsp;&nbsp;↓ orders · inventory · suppliers · sku_master<br><br>
        🤖 <b>Module 1 — Prophet Forecaster</b><br>
        &nbsp;&nbsp;&nbsp;↓ 12 months of history → 30-day SKU-level forecast<br><br>
        ⚠️ <b>Module 2 — Stockout Scorer</b><br>
        &nbsp;&nbsp;&nbsp;↓ forecast demand vs current stock vs lead time<br><br>
        🔧 <b>Module 3 — Reorder Calculator</b><br>
        &nbsp;&nbsp;&nbsp;↓ EOQ + Safety Stock + Reorder Point formulas<br><br>
        🗑️ <b>Module 4 — Lean Waste Detector</b><br>
        &nbsp;&nbsp;&nbsp;↓ excess inventory · over-ordering · planning failure<br><br>
        📦 <b>Module 5 — ERP Exporter</b><br>
        &nbsp;&nbsp;&nbsp;↓ SAP MM MRP II flat file (MM17 import ready)<br><br>
        📊 <b>Module 6 — Excel MRP Report</b><br>
        &nbsp;&nbsp;&nbsp;↓ 5-sheet workbook for warehouse directors
        </div>
        """, unsafe_allow_html=True)

    with col_right:
        # Donut chart — filtered SKU category breakdown
        st.markdown(
            '<p class="section-header">📦 SKUs by Category</p>',
            unsafe_allow_html=True
        )
        cat_counts = reorder_df["category"].value_counts().reset_index()
        cat_counts.columns = ["Category", "SKU Count"]
        sku_label  = f"{len(reorder_df)}<br>SKUs"

        fig_pie = px.pie(
            cat_counts,
            values = "SKU Count",
            names  = "Category",
            hole   = 0.55,
            color_discrete_sequence = [
                "#2E75B6", "#F0C040", "#27AE60", "#E67E22", "#8E44AD"
            ],
        )
        fig_pie.update_layout(
            **CHART_THEME,
            showlegend  = True,
            height      = 300,
            margin      = dict(l=10, r=10, t=10, b=10),
            legend      = dict(
                orientation = "v", x=1.0, y=0.5,
                font        = dict(size=11, color="#E8EDF2"),
                bgcolor     = "#1A2634",
            ),
            annotations = [dict(
                text      = sku_label,
                x=0.5, y=0.5,
                font      = dict(size=16, color="#F0C040", family="Arial"),
                showarrow = False,
            )],
        )
        fig_pie.update_traces(textfont_color="#E8EDF2")
        st.plotly_chart(fig_pie, use_container_width=True)

        # Horizontal bar — annual waste by type (filtered)
        st.markdown(
            '<p class="section-header">🗑️ Annual Waste by Type</p>',
            unsafe_allow_html=True
        )
        waste_by_type = (
            waste_df.groupby("waste_type")["annual_waste_usd"]
            .sum().reset_index()
        )
        waste_by_type.columns = ["Waste Type", "Annual Waste USD"]
        waste_by_type["Waste Type"] = (
            waste_by_type["Waste Type"].str.replace("_", " ").str.title()
        )

        if waste_by_type.empty:
            st.info("No waste flags for the selected categories.")
        else:
            fig_bar = px.bar(
                waste_by_type,
                x                       = "Annual Waste USD",
                y                       = "Waste Type",
                orientation             = "h",
                color_discrete_sequence = ["#C0392B"],
                text = waste_by_type["Annual Waste USD"].apply(
                           lambda v: f"${v:,.0f}"
                       ),
            )
            fig_bar.update_layout(
                **CHART_THEME,
                height     = 180,
                margin     = dict(l=10, r=60, t=10, b=10),
                xaxis      = dict(gridcolor=GRID, showgrid=True, zeroline=False),
                yaxis      = dict(gridcolor=GRID, showgrid=False, zeroline=False),
                showlegend = False,
            )
            fig_bar.update_traces(
                textposition = "outside",
                textfont     = dict(color="#E8EDF2", size=11),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("""
    <div class="info-box">
    💡 <b>How to navigate:</b> Use the sidebar links to explore each module's output.
    Use the <b>Filter by Category</b> control in the sidebar to narrow all pages
    to specific SKU categories at once.
    &nbsp;<b>Demand Forecast</b> → pick any SKU to see its Prophet chart + history window.
    &nbsp;<b>Reorder Parameters</b> → use the savings slider to focus on high-impact SKUs.
    &nbsp;<b>Lean Waste</b> → filter by waste type, severity, and minimum dollar value.
    &nbsp;<b>ERP Export</b> → download the SAP MM17-ready file directly.
    </div>
    """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# PAGE 2 — DEMAND FORECAST
# Category filter narrows the SKU dropdown.
# History window slider controls how many days of history appear on the chart.
# ════════════════════════════════════════════════════════════════════════════
def page_forecast(selected_cats):
    st.markdown("## 📈 Demand Forecast — Prophet ML Engine")
    st.markdown(
        '<div class="info-box">'
        'Facebook Prophet was trained on ~12 months of daily order history per SKU. '
        'The model automatically detects weekly patterns, yearly trends, and '
        'US public holidays. '
        'Select a SKU to explore its 30-day forward forecast and 95% confidence band. '
        'Use the <b>History Window</b> slider to control how much past data is shown.'
        '</div>',
        unsafe_allow_html=True
    )

    forecast_df = load_forecasts()
    history_df  = load_order_history()
    reorder_df  = load_reorder_params()

    history_df["order_date"]     = pd.to_datetime(history_df["order_date"])
    forecast_df["forecast_date"] = pd.to_datetime(forecast_df["forecast_date"])

    # Only show SKUs that belong to the selected categories
    cat_skus = reorder_df[reorder_df["category"].isin(selected_cats)]["sku"].tolist()
    skus     = sorted([s for s in forecast_df["sku"].unique()
                       if s in cat_skus])

    show_filter_banner(selected_cats, len(skus), " SKUs in dropdown")

    if not skus:
        st.warning("No SKUs match the selected categories. "
                   "Adjust the category filter in the sidebar.")
        return

    # Controls row: SKU selector + history window slider
    col_sel, col_slider, col_spacer = st.columns([1, 1, 2])
    with col_sel:
        selected_sku = st.selectbox("Select SKU", skus)
    with col_slider:
        history_days = st.select_slider(
            "History Window",
            options = [30, 60, 90, 180, 365],
            value   = 90,
            help    = (
                "Controls how many days of historical order data appear "
                "on the chart. The forecast always shows 30 days forward."
            ),
        )

    # Filter to selected SKU
    sku_hist = history_df[history_df["sku"] == selected_sku].copy()
    sku_fc   = forecast_df[forecast_df["sku"] == selected_sku].copy()

    # Get this SKU's category for context
    sku_cat  = reorder_df[reorder_df["sku"] == selected_sku]["category"].values
    sku_cat  = sku_cat[0] if len(sku_cat) > 0 else "—"

    avg_hist  = sku_hist["daily_orders"].mean()
    avg_fc    = sku_fc["yhat"].mean()
    delta_pct = ((avg_fc - avg_hist) / avg_hist * 100) if avg_hist > 0 else 0

    # Per-SKU metric cards
    with col_spacer:
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Category",           sku_cat)
        m2.metric("History Days",        f"{len(sku_hist)}")
        m3.metric("Avg Historical/Day",  f"{avg_hist:.1f}")
        m4.metric("Avg Forecast/Day",    f"{avg_fc:.1f}",
                  delta=f"{delta_pct:+.1f}%")
        m5.metric("Forecast Horizon",    "30 days")

    tab_chart, tab_table = st.tabs(["📊 Forecast Chart", "📋 Forecast Table"])

    with tab_chart:
        fig = go.Figure()

        # Blue line — historical orders for the chosen window
        hist_recent = sku_hist.tail(history_days)
        fig.add_trace(go.Scatter(
            x      = hist_recent["order_date"],
            y      = hist_recent["daily_orders"],
            mode   = "lines+markers",
            name   = f"Historical Orders (last {history_days}d)",
            line   = dict(color="#2E75B6", width=2),
            marker = dict(size=4, color="#2E75B6"),
        ))

        # Confidence band — convert dates to strings to avoid pandas
        # Timestamp arithmetic errors in newer versions
        fc_dates_fwd = sku_fc["forecast_date"].dt.strftime("%Y-%m-%d")
        fc_dates_rev = sku_fc["forecast_date"][::-1].dt.strftime("%Y-%m-%d")

        fig.add_trace(go.Scatter(
            x         = pd.concat([fc_dates_fwd, fc_dates_rev],
                                  ignore_index=True),
            y         = pd.concat([
                            sku_fc["yhat_upper"].clip(lower=0),
                            sku_fc["yhat_lower"].clip(lower=0)[::-1],
                        ], ignore_index=True),
            fill      = "toself",
            fillcolor = "rgba(240,192,64,0.15)",
            line      = dict(color="rgba(0,0,0,0)"),
            name      = "95% Confidence Band",
        ))

        # Amber dashed line — forecast
        fig.add_trace(go.Scatter(
            x    = sku_fc["forecast_date"],
            y    = sku_fc["yhat"].clip(lower=0),
            mode = "lines",
            name = "Forecast (Prophet)",
            line = dict(color="#F0C040", width=2.5, dash="dash"),
        ))

        # Forecast start marker — drawn as a Scatter trace because
        # add_vline() breaks in Plotly 6.x when the x axis contains dates
        split_date_str = sku_fc["forecast_date"].min().strftime("%Y-%m-%d")
        y_max          = hist_recent["daily_orders"].max() * 1.2 if not hist_recent.empty else 10
        fig.add_trace(go.Scatter(
            x          = [split_date_str, split_date_str],
            y          = [0, y_max],
            mode       = "lines",
            name       = "Forecast Start",
            line       = dict(color="#4A6580", width=1.5, dash="dot"),
            showlegend = True,
        ))

        fig.update_layout(
            **CHART_THEME,
            title  = f"{selected_sku} ({sku_cat}) — 30-Day Demand Forecast",
            height = 420,
            xaxis  = dict(title="Date",         gridcolor=GRID,
                          showgrid=True,  zeroline=False),
            yaxis  = dict(title="Daily Orders", gridcolor=GRID,
                          showgrid=True,  zeroline=False),
            legend = dict(orientation="h", y=-0.2,
                          font=dict(color="#E8EDF2"), bgcolor="#1A2634"),
            margin = dict(l=20, r=20, t=50, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("""
        <div class="info-box">
        📌 <b>Reading this chart:</b>
        The <span style="color:#2E75B6;"><b>blue line</b></span> shows actual
        historical daily orders for the selected history window.
        The <span style="color:#F0C040;"><b>amber dashed line</b></span> is
        Prophet's 30-day forward forecast.
        The <span style="color:rgba(240,192,64,0.6);"><b>shaded band</b></span>
        is the 95% confidence interval — demand is expected to land within
        this range 95% of the time. Wider bands signal more uncertain demand.
        </div>
        """, unsafe_allow_html=True)

    with tab_table:
        display_fc = sku_fc[["forecast_date","yhat",
                              "yhat_lower","yhat_upper"]].copy()
        display_fc.columns = ["Forecast Date","Predicted Orders",
                               "Lower Bound","Upper Bound"]
        display_fc["Predicted Orders"] = display_fc["Predicted Orders"].round(2)
        display_fc["Lower Bound"]      = display_fc["Lower Bound"].round(2)
        display_fc["Upper Bound"]      = display_fc["Upper Bound"].round(2)
        st.dataframe(display_fc, use_container_width=True, height=400)


# ════════════════════════════════════════════════════════════════════════════
# PAGE 3 — STOCKOUT RISK
# Category filter + risk tier filter narrow the table.
# ════════════════════════════════════════════════════════════════════════════
def page_stockout(selected_cats):
    st.markdown("## ⚠️ Stockout Risk Analysis")
    st.markdown(
        '<div class="info-box">'
        'Stockout risk is calculated by comparing <b>days of stock remaining</b> '
        'against each SKU\'s supplier lead time. '
        '<b>Critical</b> = stockout within 3 days. '
        '<b>High</b> = stockout before replenishment arrives. '
        '<b>Medium</b> = stockout within 2× lead time. '
        '<b>Low</b> = healthy stock levels — no immediate action needed.'
        '</div>',
        unsafe_allow_html=True
    )

    reorder_df = load_reorder_params()
    reorder_df = reorder_df[reorder_df["category"].isin(selected_cats)]

    show_filter_banner(selected_cats, len(reorder_df))

    col_chart, col_metrics = st.columns([1.5, 1])

    with col_chart:
        st.markdown(
            '<p class="section-header">Risk Distribution</p>',
            unsafe_allow_html=True
        )
        risk_counts = reorder_df["stockout_risk"].value_counts().reset_index()
        risk_counts.columns = ["Risk", "Count"]
        all_tiers   = pd.DataFrame({"Risk": ["Critical","High","Medium","Low"]})
        risk_counts = (all_tiers.merge(risk_counts, on="Risk", how="left")
                                .fillna(0))
        risk_counts["Count"] = risk_counts["Count"].astype(int)

        colour_map  = {
            "Critical": "#C0392B", "High": "#E67E22",
            "Medium":   "#F39C12", "Low":  "#27AE60",
        }
        bar_colours = [colour_map[r] for r in risk_counts["Risk"]]

        fig = go.Figure(go.Bar(
            x            = risk_counts["Risk"],
            y            = risk_counts["Count"],
            marker_color = bar_colours,
            text         = risk_counts["Count"],
            textposition = "outside",
            textfont     = dict(color="#E8EDF2", size=14),
        ))
        fig.update_layout(
            **CHART_THEME,
            height     = 300,
            showlegend = False,
            xaxis      = dict(gridcolor=GRID, showgrid=False, zeroline=False),
            yaxis      = dict(title="SKU Count", gridcolor=GRID,
                              showgrid=True, zeroline=False),
            margin     = dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_metrics:
        st.markdown(
            '<p class="section-header">Risk Counts</p>',
            unsafe_allow_html=True
        )
        for _, row in risk_counts.iterrows():
            badge_class = f"badge-{row['Risk'].lower()}"
            st.markdown(
                f'<div style="display:flex; align-items:center; '
                f'margin:10px 0; gap:12px;">'
                f'<span class="{badge_class}">{row["Risk"]}</span>'
                f'<span style="font-size:22px; font-weight:700; '
                f'color:#F0C040;">{int(row["Count"])} SKUs</span>'
                f'</div>',
                unsafe_allow_html=True
            )

    # Table filters: risk tier + category (within current global filter)
    st.markdown(
        '<p class="section-header">📋 Full SKU Risk Table</p>',
        unsafe_allow_html=True
    )

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        risk_filter = st.multiselect(
            "Filter by Risk Tier",
            options = ["Critical","High","Medium","Low"],
            default = ["Critical","High","Medium","Low"],
        )
    with filter_col2:
        cat_filter = st.multiselect(
            "Filter by Category",
            options = sorted(reorder_df["category"].unique().tolist()),
            default = sorted(reorder_df["category"].unique().tolist()),
        )

    filtered = reorder_df[
        (reorder_df["stockout_risk"].isin(risk_filter)) &
        (reorder_df["category"].isin(cat_filter))
    ]

    display = filtered[[
        "sku","category","current_stock","days_of_stock",
        "lead_time_days","forecast_demand_in_lt","stockout_risk"
    ]].copy()
    display.columns = [
        "SKU","Category","Current Stock","Days of Stock",
        "Lead Time (days)","Forecast Demand in LT","Risk"
    ]
    display["Days of Stock"]         = display["Days of Stock"].round(1)
    display["Forecast Demand in LT"] = display["Forecast Demand in LT"].round(1)
    display["Current Stock"]         = display["Current Stock"].astype(int)

    st.caption(f"{len(display)} SKUs shown after filters")
    st.dataframe(
        display.sort_values("Days of Stock"),
        use_container_width = True,
        height = 420,
    )

    st.markdown("""
    <div class="info-box">
    📌 <b>Days of Stock</b> = Current Stock ÷ Avg Daily Forecast Demand.
    If this number is less than the lead time, a new order placed today
    won't arrive before stockout — that's what "High" risk means here.
    Pipeline stock (in-transit orders) is assumed zero — a deliberately
    conservative assumption in the absence of live purchase order data.
    </div>
    """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# PAGE 4 — REORDER PARAMETERS
# Category filter + minimum savings slider narrow the charts and table.
# ════════════════════════════════════════════════════════════════════════════
def page_reorder(selected_cats):
    st.markdown("## 🔧 Reorder Parameter Optimisation")
    st.markdown(
        '<div class="info-box">'
        'EOQ (Economic Order Quantity) calculates the order size that minimises '
        'total inventory cost by balancing ordering costs against holding costs. '
        'The Reorder Point (ROP) tells you <i>when</i> to order so that stock '
        'arrives just as your safety buffer begins depleting. '
        'Use the <b>Minimum Savings</b> slider below to focus on the highest-impact SKUs.'
        '</div>',
        unsafe_allow_html=True
    )

    reorder_df = load_reorder_params()
    reorder_df = reorder_df[reorder_df["category"].isin(selected_cats)]

    show_filter_banner(selected_cats, len(reorder_df))

    if reorder_df.empty:
        st.warning("No SKUs match the selected categories.")
        return

    # Minimum savings threshold slider
    max_savings = int(reorder_df["potential_savings_usd"].max())
    min_savings = st.slider(
        "Minimum Annual Savings to Show ($)",
        min_value = 0,
        max_value = max_savings,
        value     = 0,
        step      = 500,
        help      = (
            "Drag right to focus on SKUs with the largest savings potential. "
            "All SKUs visible at $0."
        ),
    )

    filtered_df = reorder_df[reorder_df["potential_savings_usd"] >= min_savings]

    if min_savings > 0:
        st.caption(
            f"Showing {len(filtered_df)} of {len(reorder_df)} SKUs "
            f"with savings ≥ ${min_savings:,}"
        )

    if filtered_df.empty:
        st.info("No SKUs above the savings threshold. Lower the slider.")
        return

    # KPI cards reflect the filtered set
    total_savings = filtered_df["potential_savings_usd"].sum()
    avg_eoq       = filtered_df["eoq"].mean()
    avg_ss        = filtered_df["safety_stock"].mean()
    negative_gaps = len(filtered_df[filtered_df["gap"] < 0])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Potential Savings",   f"${total_savings:,.0f}",
              help="Annual savings across filtered SKUs if ROPs are optimised")
    m2.metric("Avg EOQ (filtered)",        f"{avg_eoq:.0f} units",
              help="Average optimal order quantity for filtered SKUs")
    m3.metric("Avg Safety Stock",          f"{avg_ss:.0f} units",
              help="Average buffer stock at 95% service level")
    m4.metric("SKUs Reordering Too Early", f"{negative_gaps}/{len(filtered_df)}",
              help="SKUs with negative gap = ordering earlier than needed")

    tab1, tab2 = st.tabs(
        ["📊 Current vs Optimal ROP", "📋 Full Parameters Table"]
    )

    with tab1:
        st.markdown(
            '<p class="section-header">Current ROP vs Optimal ROP per SKU</p>',
            unsafe_allow_html=True
        )
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name         = "Current ROP",
            x            = filtered_df["sku"],
            y            = filtered_df["current_rop"],
            marker_color = "#2E75B6",
        ))
        fig.add_trace(go.Bar(
            name         = "Optimal ROP",
            x            = filtered_df["sku"],
            y            = filtered_df["optimal_rop"],
            marker_color = "#F0C040",
        ))
        fig.update_layout(
            **CHART_THEME,
            barmode = "group",
            height  = 380,
            xaxis   = dict(title="SKU", tickangle=-45,
                           gridcolor=GRID, showgrid=False, zeroline=False),
            yaxis   = dict(title="Reorder Point (units)",
                           gridcolor=GRID, showgrid=True, zeroline=False),
            legend  = dict(orientation="h", y=-0.28,
                           font=dict(color="#E8EDF2"), bgcolor="#1A2634"),
            margin  = dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("""
        <div class="warn-box">
        ⚠️ <b>Every Current ROP bar is significantly higher than the Optimal ROP.</b>
        The warehouse is triggering new purchase orders much earlier than the
        EOQ model recommends — building up excess stock and incurring avoidable
        holding costs. The gap between the blue and amber bars is the direct
        savings opportunity per SKU.
        </div>
        """, unsafe_allow_html=True)

        st.markdown(
            '<p class="section-header">💰 Savings Potential by SKU</p>',
            unsafe_allow_html=True
        )
        fig2 = px.bar(
            filtered_df,
            x                       = "sku",
            y                       = "potential_savings_usd",
            color                   = "category",
            color_discrete_sequence = [
                "#2E75B6","#F0C040","#27AE60","#E67E22","#8E44AD"
            ],
            text = filtered_df["potential_savings_usd"].apply(
                       lambda v: f"${v:,.0f}"
                   ),
        )
        fig2.update_layout(
            **CHART_THEME,
            height = 340,
            xaxis  = dict(title="SKU",
                          gridcolor=GRID, showgrid=False, zeroline=False),
            yaxis  = dict(title="Potential Annual Savings ($)",
                          gridcolor=GRID, showgrid=True, zeroline=False),
            legend = dict(orientation="h", y=-0.28,
                          font=dict(color="#E8EDF2"), bgcolor="#1A2634"),
            margin = dict(l=20, r=20, t=20, b=20),
        )
        fig2.update_traces(
            textposition = "outside",
            textfont     = dict(color="#E8EDF2", size=10),
        )
        st.plotly_chart(fig2, use_container_width=True)

    with tab2:
        display = filtered_df[[
            "sku","category","eoq","safety_stock",
            "current_rop","optimal_rop","gap","potential_savings_usd"
        ]].copy()
        display.columns = [
            "SKU","Category","EOQ","Safety Stock",
            "Current ROP","Optimal ROP","Gap","Savings ($)"
        ]
        for col in ["EOQ","Safety Stock","Current ROP","Optimal ROP","Gap"]:
            display[col] = display[col].round(1)
        display["Savings ($)"] = display["Savings ($)"].round(2)
        st.dataframe(display, use_container_width=True, height=480)


# ════════════════════════════════════════════════════════════════════════════
# PAGE 5 — LEAN WASTE
# Category filter + waste type + severity + minimum $ threshold filters.
# ════════════════════════════════════════════════════════════════════════════
def page_waste(selected_cats):
    st.markdown("## 🗑️ Lean Waste Detection")
    st.markdown(
        '<div class="info-box">'
        'Lean Manufacturing defines waste (Muda) as any resource or activity '
        'that does not add value for the customer. '
        'This engine flags three inventory-specific waste types: '
        '<b>Excess Inventory</b> — holding more than 2× calculated safety stock; '
        '<b>Over-Ordering</b> — placing orders more than 1.5× the EOQ optimum; '
        '<b>Demand Planning Failure</b> — stockout rate exceeding 5% in the trailing 90 days. '
        'Use the filters below to focus on what matters most.</div>',
        unsafe_allow_html=True
    )

    waste_df   = load_waste_flags()
    reorder_df = load_reorder_params()

    # Apply category filter — waste flags don't carry category directly
    # so we join via the SKU list from reorder_params
    cat_skus = reorder_df[reorder_df["category"].isin(selected_cats)]["sku"]
    waste_df = waste_df[waste_df["sku"].isin(cat_skus)]

    show_filter_banner(selected_cats, waste_df["sku"].nunique(), " SKUs with flags")

    if waste_df.empty:
        st.warning("No waste flags found for the selected categories.")
        return

    # Minimum annual waste threshold slider
    max_waste = int(waste_df["annual_waste_usd"].max())
    min_waste = st.slider(
        "Minimum Annual Waste to Show ($)",
        min_value = 0,
        max_value = max_waste,
        value     = 0,
        step      = 1000,
        help      = (
            "Drag right to hide smaller waste flags and focus on "
            "the most costly ones. All flags visible at $0."
        ),
    )
    waste_df = waste_df[waste_df["annual_waste_usd"] >= min_waste]

    if min_waste > 0:
        st.caption(f"{len(waste_df)} flags shown above ${min_waste:,} threshold")

    if waste_df.empty:
        st.info("No flags above the threshold. Lower the slider.")
        return

    total_waste = waste_df["annual_waste_usd"].sum()
    total_flags = len(waste_df)
    total_skus  = waste_df["sku"].nunique()
    high_flags  = len(waste_df[waste_df["severity"] == "High"])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Annual Waste",  f"${total_waste:,.0f}",
              help="Sum of all visible waste flags")
    m2.metric("Total Flags",         str(total_flags))
    m3.metric("SKUs Flagged",        str(total_skus))
    m4.metric("High Severity Flags", str(high_flags),
              help="Flags requiring immediate attention")

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown(
            '<p class="section-header">Waste by Type ($)</p>',
            unsafe_allow_html=True
        )
        by_type = (
            waste_df.groupby("waste_type")["annual_waste_usd"]
            .sum().reset_index()
        )
        by_type["waste_type"] = (
            by_type["waste_type"].str.replace("_", " ").str.title()
        )
        by_type.columns = ["Waste Type", "Annual Waste"]

        fig = px.bar(
            by_type,
            x                       = "Annual Waste",
            y                       = "Waste Type",
            orientation             = "h",
            color                   = "Waste Type",
            color_discrete_sequence = ["#C0392B","#E67E22","#F39C12"],
            text = by_type["Annual Waste"].apply(lambda v: f"${v:,.0f}"),
        )
        fig.update_layout(
            **CHART_THEME,
            height     = 260,
            showlegend = False,
            xaxis      = dict(gridcolor=GRID, showgrid=True, zeroline=False),
            yaxis      = dict(gridcolor=GRID, showgrid=False, zeroline=False),
            margin     = dict(l=10, r=60, t=10, b=10),
        )
        fig.update_traces(
            textposition = "outside",
            textfont     = dict(color="#E8EDF2", size=11),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown(
            '<p class="section-header">Flags by Severity</p>',
            unsafe_allow_html=True
        )
        by_sev = (
            waste_df.groupby("severity")
            .agg(flags=("sku","count"), waste=("annual_waste_usd","sum"))
            .reset_index()
        )
        sev_colours = {"High":"#C0392B","Medium":"#F39C12","Low":"#27AE60"}
        colours     = [sev_colours.get(s, "#2E75B6") for s in by_sev["severity"]]

        fig2 = go.Figure(go.Bar(
            x            = by_sev["severity"],
            y            = by_sev["flags"],
            marker_color = colours,
            text         = by_sev["flags"],
            textposition = "outside",
            textfont     = dict(color="#E8EDF2", size=14),
        ))
        fig2.update_layout(
            **CHART_THEME,
            height     = 260,
            showlegend = False,
            xaxis      = dict(gridcolor=GRID, showgrid=False, zeroline=False),
            yaxis      = dict(title="Flag Count",
                              gridcolor=GRID, showgrid=True, zeroline=False),
            margin     = dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig2, use_container_width=True)

    # Detail table with type + severity filters
    st.markdown(
        '<p class="section-header">📋 All Waste Flags — Detail View</p>',
        unsafe_allow_html=True
    )

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        type_filter = st.multiselect(
            "Filter by Waste Type",
            options = waste_df["waste_type"].unique().tolist(),
            default = waste_df["waste_type"].unique().tolist(),
        )
    with filter_col2:
        sev_filter = st.multiselect(
            "Filter by Severity",
            options = ["High","Medium","Low"],
            default = ["High","Medium","Low"],
        )

    filtered = waste_df[
        (waste_df["waste_type"].isin(type_filter)) &
        (waste_df["severity"].isin(sev_filter))
    ]

    display = filtered[[
        "sku","waste_type","severity","annual_waste_usd","detail"
    ]].copy()
    display.columns      = ["SKU","Waste Type","Severity",
                             "Annual Waste ($)","Detail"]
    display["Annual Waste ($)"] = display["Annual Waste ($)"].round(2)
    display["Waste Type"]       = (
        display["Waste Type"].str.replace("_"," ").str.title()
    )

    st.caption(f"{len(display)} flags shown")
    st.dataframe(display, use_container_width=True, height=400)

    st.markdown(f"""
    <div class="warn-box">
    🔴 <b>Total estimated annual waste: ${total_waste:,.2f} across {total_skus} SKUs.</b><br>
    The dominant waste type is <b>Excess Inventory</b> — every SKU is carrying
    significantly more stock than its scientifically calculated safety stock level
    justifies. This is a systemic over-stocking pattern, not an isolated issue.<br><br>
    Recommended action: align reorder points to the optimal ROP values shown in
    the Reorder Parameters page. This alone would eliminate the majority of the
    holding cost waste identified here.
    </div>
    """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# PAGE 6 — ERP EXPORT
# Category filter narrows the material records in the export preview.
# ════════════════════════════════════════════════════════════════════════════
def page_erp(selected_cats):
    st.markdown("## 📦 ERP Export — SAP MM MRP II Format")
    st.markdown(
        '<div class="info-box">'
        'This export mirrors SAP MM module MRP II planning fields exactly. '
        'The file can be imported directly into SAP via transaction <b>MM17</b> '
        '(Mass Maintenance of Material Master) or equivalent ERP batch upload — '
        'demonstrating direct integration readiness with enterprise systems. '
        'Pipe delimiter (<b>|</b>) is used instead of comma to avoid conflicts '
        'with material description text. '
        'The category filter in the sidebar narrows which materials appear in the export.'
        '</div>',
        unsafe_allow_html=True
    )

    sap_df     = load_erp_export()
    reorder_df = load_reorder_params()

    # Filter to selected categories
    cat_skus = reorder_df[reorder_df["category"].isin(selected_cats)]["sku"]
    sap_df   = sap_df[sap_df["MATNR"].isin(cat_skus)]

    show_filter_banner(
        selected_cats, len(sap_df),
        f" material records in export"
    )

    # SAP field reference cards
    st.markdown(
        '<p class="section-header">SAP Field Reference</p>',
        unsafe_allow_html=True
    )
    fields = [
        ("MATNR", "Material Number", "SKU identifier"),
        ("WERKS", "Plant Code",      "Warehouse = WH01"),
        ("MINBE", "Reorder Point",   "Trigger order at this level"),
        ("EISBE", "Safety Stock",    "Minimum buffer to hold"),
        ("MABST", "Max Stock Level", "Upper stocking limit"),
        ("BSTMI", "Min Lot Size",    "Smallest acceptable order"),
        ("BSTMA", "Max Lot Size",    "Largest acceptable order"),
    ]
    cols = st.columns(7)
    for col, (code, name, desc) in zip(cols, fields):
        col.markdown(
            f'<div style="background:#1A2634; border:1px solid #2E4057; '
            f'border-top:3px solid #F0C040; border-radius:6px; '
            f'padding:10px 8px; text-align:center;">'
            f'<p style="color:#F0C040; font-weight:800; font-size:15px; '
            f'margin:0;">{code}</p>'
            f'<p style="color:#8FA3B1; font-size:10px; margin:4px 0 0 0;">'
            f'{name}<br><i>{desc}</i></p>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Data preview
    st.markdown(
        '<p class="section-header">📋 Export Data Preview</p>',
        unsafe_allow_html=True
    )
    st.caption(f"{len(sap_df)} material records")
    st.dataframe(sap_df, use_container_width=True, height=460)

    # Download buttons
    st.markdown(
        '<p class="section-header">⬇️ Download</p>',
        unsafe_allow_html=True
    )
    col_dl1, col_dl2, col_dl3 = st.columns(3)

    # Filtered pipe-delimited CSV
    csv_bytes = sap_df.to_csv(sep="|", index=False).encode("utf-8")
    col_dl1.download_button(
        label     = "⬇️ SAP Flat File (.csv pipe-delimited)",
        data      = csv_bytes,
        file_name = f"sap_mrp_export_{date.today().strftime('%Y%m%d')}.csv",
        mime      = "text/csv",
        help      = "Pipe-delimited — ready for SAP MM17 batch import",
    )

    # Latest Excel MRP report
    reports_dir = Path(__file__).parent / "reports"
    excel_files = list(reports_dir.glob("mrp_report_*.xlsx"))
    if excel_files:
        latest_excel = max(excel_files, key=lambda f: f.stat().st_mtime)
        with open(latest_excel, "rb") as f:
            col_dl2.download_button(
                label     = "⬇️ Full MRP Report (.xlsx)",
                data      = f.read(),
                file_name = latest_excel.name,
                mime      = ("application/vnd.openxmlformats-officedocument"
                             ".spreadsheetml.sheet"),
                help      = "5-sheet Excel workbook with all pipeline outputs",
            )
    else:
        col_dl2.info("Run main.py first to generate the Excel report.")

    st.markdown("""
    <div class="info-box" style="margin-top:16px;">
    📌 <b>How to import this file into SAP:</b><br>
    1. Open SAP GUI → Transaction <b>MM17</b>
       (Mass Maintenance of Material Master)<br>
    2. Select views <b>MRP 1</b> and <b>MRP 2</b><br>
    3. Upload the pipe-delimited CSV file<br>
    4. Map columns: MATNR→Material, WERKS→Plant,
       MINBE→Reorder Pt, EISBE→Safety Stock<br>
    5. Execute — all selected SKUs update in one batch<br><br>
    📌 Compatible with SAP ECC 6.0, SAP S/4HANA, and any ERP system
    that supports MRP II parameter batch upload via flat file.
    </div>
    """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# ROUTER
# render_sidebar() now returns (page, selected_cats).
# Every page function receives selected_cats so it can filter its own data.
# ════════════════════════════════════════════════════════════════════════════
def main():
    page, selected_cats = render_sidebar()

    if   "Home"     in page: page_home(selected_cats)
    elif "Forecast" in page: page_forecast(selected_cats)
    elif "Stockout" in page: page_stockout(selected_cats)
    elif "Reorder"  in page: page_reorder(selected_cats)
    elif "Waste"    in page: page_waste(selected_cats)
    elif "ERP"      in page: page_erp(selected_cats)


if __name__ == "__main__":
    main()