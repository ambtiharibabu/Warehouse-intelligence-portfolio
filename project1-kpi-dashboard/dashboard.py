# ============================================================
# dashboard.py
# Warehouse Operations KPI Dashboard — Streamlit Application
#
# This is the main entry point for the dashboard.
# It pulls live KPI data from PostgreSQL, evaluates alert
# thresholds, and renders 6 operational tabs plus an
# executive Power BI embed on Tab 1.
#
# To run: streamlit run dashboard.py
# ============================================================

import streamlit as st
import plotly.express as px
import pandas as pd
import streamlit.components.v1 as components
from datetime import date, timedelta, datetime
from kpi_engine import get_all_kpis
from alerts import evaluate_all_kpis
from export_utils import build_excel_export

# This must be the very first Streamlit call in the file.
# It sets the browser tab title, favicon, and page width.
st.set_page_config(
    page_title = "Warehouse KPI Dashboard",
    page_icon  = "🏭",
    layout     = "wide"
)

# ============================================================
# GLOBAL STYLING
#
# We inject custom CSS using st.markdown with unsafe_allow_html.
# This controls three things:
#   1. The full-page background — a light supply chain warehouse
#      photo with a soft white overlay so charts stay readable
#   2. The sidebar background — a forklift image with a strong
#      dark overlay so filter labels remain legible on top
#   3. Tab bar styling — bolder active tab with blue underline
#
# Why CSS injection? Streamlit doesn't expose these styling
# hooks natively, so this is the standard community workaround.
# ============================================================
st.markdown(
    """
    <style>

    /* ── Full page background ─────────────────────────────
       Warehouse floor photo behind the entire app canvas.
       The rgba(245,247,250,0.92) overlay makes it very subtle
       — just enough texture to break the plain white default,
       while keeping charts and cards perfectly readable.
    ── */
    .stApp {
        background-image:
            linear-gradient(rgba(245,247,250,0.92), rgba(245,247,250,0.92)),
            url('https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=1920&q=60');
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }

    /* ── Sidebar background ───────────────────────────────
       Forklift/warehouse image behind the filter panel.
       The dark overlay at 0.83 opacity is intentionally strong
       so all white filter labels, dropdowns and buttons
       stay readable against the background photo.
    ── */
    [data-testid="stSidebar"] {
        background-image:
            linear-gradient(rgba(15,23,42,0.83), rgba(15,23,42,0.83)),
            url('https://images.unsplash.com/photo-1595079676339-1534801ad6cf?w=800&q=60');
        background-size: cover;
        background-position: center top;
    }

    /* Force all sidebar text and widget labels to white */
    [data-testid="stSidebar"] * {
        color: #ffffff !important;
    }

    /* ── Tab bar styling ──────────────────────────────────
       Active tab gets a blue bottom border and bold weight.
       This makes it immediately clear which section you're in.
    ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 2px solid #e2e8f0;
    }
    .stTabs [data-baseweb="tab"] {
        font-weight: 500;
        font-size: 0.9rem;
        padding: 8px 16px;
        color: #475569;
    }
    .stTabs [aria-selected="true"] {
        color: #1d4ed8 !important;
        border-bottom: 3px solid #1d4ed8 !important;
        font-weight: 700 !important;
    }

    /* Small top padding reduction for the main content area */
    .block-container {
        padding-top: 1rem;
    }

    </style>
    """,
    unsafe_allow_html=True
)

# ============================================================
# APP HEADER
#
# Rendered at the very top of every page above the tabs.
# Contains the system name, a 2-3 sentence description of
# what the system monitors and who it's built for, plus a
# clear explanation of the two dashboard layers.
# ============================================================
st.markdown(
    """
    <div style="
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
        padding: 28px 36px 24px 36px;
        border-radius: 12px;
        margin-bottom: 20px;
        border-left: 6px solid #3b82f6;
        box-shadow: 0 4px 16px rgba(0,0,0,0.12);
    ">
        <div style="
            font-size: 1.75rem;
            font-weight: 800;
            color: #ffffff;
            letter-spacing: 0.02em;
            margin-bottom: 10px;
        ">
             Warehouse Operations Intelligence Platform
        </div>
        <div style="
            font-size: 0.96rem;
            color: #cbd5e1;
            line-height: 1.75;
            max-width: 980px;
        ">
            A real-time operational visibility system tracking
            <strong style="color:#93c5fd;">6 critical KPIs</strong>
            across order fulfillment, inventory accuracy, labor productivity,
            OSHA safety compliance, and shipping performance —
            powered by a live PostgreSQL pipeline with
            <strong style="color:#93c5fd;">90 days of warehouse data</strong>
            spanning 4,500 orders, 30 associates, 20 SKUs, and 5 carrier partners.
            <br><br>
            <span style="color:#94a3b8; font-size:0.87rem;">
            📊 <strong style="color:#60a5fa;">Tab 1 — Executive Summary:</strong>
            Embedded Power BI dashboard with conditional Red/Yellow/Green KPI cards,
            date + shift + department slicers, trend lines, and carrier/SKU drill-down matrices
            — built for management review and boardroom presentations.
            &nbsp;&nbsp;|&nbsp;&nbsp;
            📦 <strong style="color:#60a5fa;">Tabs 2 – 6 — Operational Deep Dives:</strong>
            Interactive Plotly charts for warehouse supervisors, filterable by date range,
            shift, and department in the left panel.
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# ============================================================
# SIDEBAR — Filters
#
# These filters drive all charts in Tabs 2–6.
# Tab 1 (Power BI) has its own internal slicers and is
# unaffected by these controls — it's a fully self-contained
# embedded report.
# ============================================================
st.sidebar.markdown(
    """
    <div style="text-align:center; padding: 14px 0 6px 0;">
        <div style="font-size:1.15rem; font-weight:800; letter-spacing:0.05em;">
            🔧 DASHBOARD FILTERS
        </div>
        <div style="font-size:0.73rem; color:#94a3b8; margin-top:4px;">
            Applies to Tabs 2 – 6 only
        </div>
    </div>
    """,
    unsafe_allow_html=True
)
st.sidebar.markdown("---")

# Date range — defaults to last 90 days to match our data window
default_end   = date.today()
default_start = default_end - timedelta(days=90)

start_date, end_date = st.sidebar.date_input(
    "📅 Date Range",
    value     = (default_start, default_end),
    min_value = date(2020, 1, 1),
    max_value = date.today()
)

# Shift filter — useful for comparing AM vs PM vs Night performance
shift = st.sidebar.selectbox(
    "🕐 Shift",
    options = ["All", "AM", "PM", "Night"]
)

# Department filter — most impactful on the Labor tab
department = st.sidebar.selectbox(
    "🏢 Department",
    options = ["All", "Receiving", "Putaway", "Picking", "Packing", "Shipping"]
)

st.sidebar.markdown("---")

# KPI threshold legend — helps new viewers understand color coding
st.sidebar.markdown(
    """
    <div style="font-size:0.78rem; line-height:2.0;">
        <div style="font-weight:700; margin-bottom:4px; font-size:0.82rem;">
            📌 KPI Alert Thresholds
        </div>
        <span style="color:#ef4444;">🔴 Red</span> — Below alert threshold<br>
        <span style="color:#f59e0b;">🟡 Yellow</span> — In warning zone<br>
        <span style="color:#22c55e;">🟢 Green</span> — Within target range
    </div>
    """,
    unsafe_allow_html=True
)

st.sidebar.markdown("---")

# ============================================================
# KPI DATA LOADING
#
# Cache means: if someone changes a filter, Streamlit checks
# whether it already ran this exact combination of inputs
# in the last 5 minutes. If yes, it returns the saved result
# instead of querying PostgreSQL again. Saves database load
# and makes the app feel instant after the first load.
# ============================================================
@st.cache_data(ttl=300)
def load_kpis(start, end, shift, department):
    raw       = get_all_kpis(start, end, shift, department)
    evaluated = evaluate_all_kpis(raw)
    return evaluated

# kpis is defined HERE — before the export button so it's
# always available when the button is clicked.
kpis = load_kpis(start_date, end_date, shift, department)

# ============================================================
# EXPORT BUTTON
#
# Placed AFTER kpis = load_kpis(...) on purpose.
# The export function needs the kpis dict, so it must be
# defined before this block runs. Streamlit renders sidebar
# widgets in the left panel visually, but the code still
# executes top-to-bottom — order matters here.
#
# Flow when clicked:
#   1. Button press triggers a re-run of the script
#   2. build_excel_export() queries PostgreSQL for the
#      current filter selection and builds a 4-sheet workbook
#   3. download_button() appears and serves the file to
#      the user's browser as a .xlsx download
# ============================================================
if st.sidebar.button("📥 Export to Excel"):
    with st.spinner("Building Excel export..."):
        excel_buffer = build_excel_export(
            kpis, start_date, end_date, shift, department
        )
    filename = f"warehouse_kpi_export_{datetime.today().strftime('%Y%m%d')}.xlsx"
    st.sidebar.download_button(
        label     = "⬇️ Download Now",
        data      = excel_buffer,
        file_name = filename,
        mime      = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ============================================================
# TAB BANNER HELPER
#
# Each tab opens with a full-width photo banner showing a
# contextually relevant supply chain image — warehouse floor,
# conveyor belt, racking aisle etc.
# A dark gradient overlay sits between the photo and the text
# so the title is always readable regardless of image content.
# ============================================================
def tab_banner(title, subtitle, image_url):
    st.markdown(
        f"""
        <div style="
            background-image: linear-gradient(
                rgba(0,0,0,0.65), rgba(0,0,0,0.65)
            ), url('{image_url}');
            background-size: cover;
            background-position: center;
            padding: 44px 36px 32px 36px;
            border-radius: 10px;
            margin-bottom: 20px;
        ">
            <div style="
                font-size: 1.85rem;
                font-weight: 800;
                color: #ffffff;
                letter-spacing: 0.02em;
            ">{title}</div>
            <div style="
                font-size: 0.93rem;
                color: #cbd5e1;
                margin-top: 6px;
            ">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ============================================================
# KPI CARD HELPER
#
# One card per KPI. The left border color signals status:
# red = alert, yellow = warning, green = on target.
# The light semi-transparent background works well on the
# light page background we set globally via CSS.
# ============================================================
def kpi_card(label, value, unit, color_hex, detail=""):
    st.markdown(
        f"""
        <div style="
            border-left: 6px solid {color_hex};
            padding: 14px 18px;
            border-radius: 8px;
            background-color: rgba(255,255,255,0.82);
            margin-bottom: 10px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        ">
            <div style="font-size:0.82rem; color:#64748b; font-weight:500;">
                {label}
            </div>
            <div style="
                font-size: 2rem;
                font-weight: 800;
                color: {color_hex};
                line-height: 1.2;
            ">
                {value}
                <span style="font-size:0.95rem; font-weight:500;">{unit}</span>
            </div>
            <div style="font-size:0.76rem; color:#94a3b8; margin-top:2px;">
                {detail}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ============================================================
# KPI ROW RENDERER
#
# Draws all 6 KPI cards in a 3-column grid.
# Called at the top of every tab so the overall health
# snapshot is always visible regardless of which tab
# the user is currently viewing.
# ============================================================
def render_kpi_row():
    col1, col2, col3 = st.columns(3)

    with col1:
        d = kpis["fulfillment"]
        kpi_card(d["label"], d["value"], d["unit"], d["color"],
                 f"{d['fulfilled']:,} of {d['total']:,} orders")

        d = kpis["productivity"]
        kpi_card(d["label"], d["value"], d["unit"], d["color"],
                 f"{d['total_units']:,} units / {d['total_hours']:,} hrs")

    with col2:
        d = kpis["inventory"]
        kpi_card(d["label"], d["value"], d["unit"], d["color"],
                 f"Actual {d['actual']:,} vs Expected {d['expected']:,}")

        d = kpis["shipping"]
        kpi_card(d["label"], d["value"], d["unit"], d["color"],
                 f"{d['on_time']:,} of {d['total']:,} shipments")

    with col3:
        d = kpis["osha"]
        kpi_card(d["label"], d["value"], d["unit"], d["color"],
                 f"{d['incidents']} incidents over {d['total_hours']:,} hrs")

        d = kpis["cycle_time"]
        kpi_card(d["label"], d["value"], d["unit"], d["color"],
                 "Avg arrival-to-putaway time")

# ============================================================
# TAB DEFINITIONS
# ============================================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Executive Summary",
    "📦 Fulfillment",
    "🏷️ Inventory",
    "👷 Labor",
    "🦺 Safety",
    "🚚 Shipping"
])

# ============================================================
# TAB 1 — EXECUTIVE SUMMARY
# ============================================================
with tab1:
    tab_banner(
        title     = "📊 Executive Summary",
        subtitle  = "Management-layer Power BI report + live operational KPI snapshot",
        image_url = "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=1400&q=70"
    )
    st.components.v1.iframe(
        src       = "https://app.powerbi.com/view?r=eyJrIjoiNTVhMzEzOWEtZjM4NC00MWM4LTgwOTYtNGM1OTRhMWJkMjMxIiwidCI6ImUwNWI2YjNmLTE5ODAtNGIyNC04NjM3LTU4MDc3MWY0NGRlZSIsImMiOjN9",
        height    = 660,
        scrolling = True
    )
    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.97rem; font-weight:700; color:#1e3a5f; margin-bottom:8px;'>"
        "⚡ Live KPI Snapshot — refreshed every 5 minutes from PostgreSQL"
        "</div>",
        unsafe_allow_html=True
    )
    render_kpi_row()

# ============================================================
# TAB 2 — FULFILLMENT
# ============================================================
with tab2:
    tab_banner(
        title     = "📦 Order Fulfillment Deep Dive",
        subtitle  = "On-time rate by shift, problem SKUs, and daily trend",
        image_url = "https://images.unsplash.com/photo-1553413077-190dd305871c?w=1400&q=70"
    )
    render_kpi_row()
    st.markdown("---")

    from charts.fulfillment_charts import (
        chart_fulfillment_by_shift,
        chart_late_by_sku,
        chart_fulfillment_trend
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.plotly_chart(
            chart_fulfillment_by_shift(start_date, end_date, shift),
            use_container_width=True
        )
    with col_b:
        st.plotly_chart(
            chart_late_by_sku(start_date, end_date, shift),
            use_container_width=True
        )
    st.plotly_chart(
        chart_fulfillment_trend(start_date, end_date, shift),
        use_container_width=True
    )

# ============================================================
# TAB 3 — INVENTORY
# ============================================================
with tab3:
    tab_banner(
        title     = "🏷️ Inventory Accuracy",
        subtitle  = "Cycle count variance — expected vs actual by SKU and category",
        image_url = "https://images.unsplash.com/photo-1504328345606-18bbc8c9d7d1?w=1400&q=70"
    )
    render_kpi_row()
    st.markdown("---")

    from charts.inventory_charts import (
        chart_inventory_trend,
        chart_worst_skus,
        chart_accuracy_by_category
    )

    st.plotly_chart(
        chart_inventory_trend(start_date, end_date),
        use_container_width=True
    )
    col_a, col_b = st.columns(2)
    with col_a:
        st.plotly_chart(
            chart_worst_skus(start_date, end_date),
            use_container_width=True
        )
    with col_b:
        st.plotly_chart(
            chart_accuracy_by_category(start_date, end_date),
            use_container_width=True
        )

# ============================================================
# TAB 4 — LABOR
# ============================================================
with tab4:
    tab_banner(
        title     = "👷 Labor Productivity",
        subtitle  = "Units per hour by associate, department, and shift heatmap",
        image_url = "https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?w=1400&q=70"
    )
    render_kpi_row()
    st.markdown("---")

    from charts.labor_charts import (
        chart_top_associates,
        chart_bottom_associates,
        chart_productivity_by_department,
        chart_shift_department_heatmap
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.plotly_chart(
            chart_top_associates(start_date, end_date, shift, department),
            use_container_width=True
        )
    with col_b:
        st.plotly_chart(
            chart_bottom_associates(start_date, end_date, shift, department),
            use_container_width=True
        )
    col_c, col_d = st.columns(2)
    with col_c:
        st.plotly_chart(
            chart_productivity_by_department(start_date, end_date, shift),
            use_container_width=True
        )
    with col_d:
        st.plotly_chart(
            chart_shift_department_heatmap(start_date, end_date),
            use_container_width=True
        )

# ============================================================
# TAB 5 — SAFETY
# ============================================================
with tab5:
    tab_banner(
        title     = "🦺 Safety & Compliance",
        subtitle  = "OSHA incident rate, severity breakdown, and 30-day rolling trend",
        image_url = "https://images.unsplash.com/photo-1578575437130-527eed3abbec?w=1400&q=70"
    )
    render_kpi_row()
    st.markdown("---")

    from charts.safety_charts import (
        chart_incident_by_type,
        chart_incident_by_severity,
        chart_incidents_by_shift,
        chart_osha_trend,
        get_incident_log
    )

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.plotly_chart(
            chart_incident_by_type(start_date, end_date, shift),
            use_container_width=True
        )
    with col_b:
        st.plotly_chart(
            chart_incident_by_severity(start_date, end_date, shift),
            use_container_width=True
        )
    with col_c:
        st.plotly_chart(
            chart_incidents_by_shift(start_date, end_date),
            use_container_width=True
        )
    st.plotly_chart(
        chart_osha_trend(start_date, end_date),
        use_container_width=True
    )
    st.markdown(
        "<div style='font-size:0.97rem; font-weight:700;"
        "color:#1e3a5f; margin:12px 0 6px 0;'>"
        "📋 Full Incident Log"
        "</div>",
        unsafe_allow_html=True
    )
    incident_df = get_incident_log(start_date, end_date, shift)
    if incident_df.empty:
        st.info("No incidents recorded for the selected filters.")
    else:
        st.dataframe(incident_df, use_container_width=True, hide_index=True)

# ============================================================
# TAB 6 — SHIPPING
# ============================================================
with tab6:
    tab_banner(
        title     = "🚚 Shipping & Receiving",
        subtitle  = "Carrier on-time rate, delay analysis, and daily shipment volume",
        image_url = "https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=1400&q=70"
    )
    render_kpi_row()
    st.markdown("---")

    from charts.shipping_charts import (
        chart_ontime_by_carrier,
        chart_daily_shipments,
        chart_delay_distribution,
        chart_avg_delay_by_carrier
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.plotly_chart(
            chart_ontime_by_carrier(start_date, end_date),
            use_container_width=True
        )
    with col_b:
        st.plotly_chart(
            chart_avg_delay_by_carrier(start_date, end_date),
            use_container_width=True
        )
    st.plotly_chart(
        chart_daily_shipments(start_date, end_date),
        use_container_width=True
    )
    st.plotly_chart(
        chart_delay_distribution(start_date, end_date),
        use_container_width=True
    )