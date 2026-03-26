"""
forecaster.py
-------------
Reads daily order counts per SKU from PostgreSQL.
Trains a Facebook Prophet model per SKU.
Writes 30-day forecasts to the forecasts table.
Generates a Plotly chart per SKU showing history + forecast.

Run standalone : python modules/forecaster.py
Called by      : main.py
"""

import os
import sys
import warnings
import pandas as pd
import plotly.graph_objects as go
from prophet import Prophet
from sqlalchemy import text
from datetime import datetime

# Add project root to path so db.connection import works
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.connection import get_engine

# Suppress Prophet's verbose Stan output — it logs a lot during fitting
warnings.filterwarnings("ignore")
import logging
logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)


# ── Constants ────────────────────────────────────────────────────────────────
FORECAST_HORIZON = 30          # days forward to forecast
SKUS = [f"SKU-{str(i).zfill(4)}" for i in range(1, 21)]


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 1 — Read and prepare daily order counts from PostgreSQL
# Groups raw order rows into: one row per SKU per date, with order count
# ════════════════════════════════════════════════════════════════════════════
def load_order_history(engine):
    """
    Reads the orders table and returns a DataFrame of daily order counts per SKU.
    Output columns: sku | ds | y
    (ds and y are Prophet's required column names)
    """
    query = text("""
        SELECT
            sku,
            order_date          AS ds,
            COUNT(order_id)     AS y
        FROM orders
        GROUP BY sku, order_date
        ORDER BY sku, order_date
    """)

    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    # Prophet requires ds to be datetime type, not just date
    df["ds"] = pd.to_datetime(df["ds"])

    print(f"   📊 Loaded {len(df):,} daily SKU-date rows from orders table")
    print(f"   📅 Date range: {df['ds'].min().date()} → {df['ds'].max().date()}")
    return df


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 2 — Train Prophet and forecast for a single SKU
# Returns two DataFrames: forecast rows (for DB) + full history (for chart)
# ════════════════════════════════════════════════════════════════════════════
def forecast_sku(sku, sku_df):
    """
    Trains a Prophet model on one SKU's history and returns a 30-day forecast.

    Parameters:
        sku    : string like 'SKU-0001'
        sku_df : DataFrame with columns ds, y for this SKU only

    Returns:
        forecast_df : 30 future rows with yhat, yhat_lower, yhat_upper
        history_df  : the original sku_df (used for charting)
    """

    # Prophet requires at least 2 rows — skip if data is too sparse
    if len(sku_df) < 14:
        print(f"   ⚠️  {sku}: insufficient history ({len(sku_df)} rows). Skipping.")
        return None, None

    # Initialise Prophet model
    # weekly_seasonality: detects day-of-week patterns (Mon vs Fri order spikes)
    # yearly_seasonality: detects annual patterns (Q4 surge, summer dip)
    # changepoint_prior_scale: how flexible the trend is — 0.05 = moderately flexible
    model = Prophet(
        weekly_seasonality      = True,
        yearly_seasonality      = True,
        daily_seasonality       = False,   # daily noise would overfit on warehouse data
        changepoint_prior_scale = 0.05,
        interval_width          = 0.95,    # 95% confidence band
    )

    # Add US public holidays as special events — affects demand patterns
    model.add_country_holidays(country_name="US")

    # Fit the model on this SKU's historical data
    model.fit(sku_df[["ds", "y"]])

    # Build a future date DataFrame — 30 days beyond the last known date
    future = model.make_future_dataframe(periods=FORECAST_HORIZON, freq="D")

    # Generate forecast — returns history + future rows in one DataFrame
    forecast = model.predict(future)

    # Extract only the future rows (beyond the last historical date)
    last_date = sku_df["ds"].max()
    forecast_future = forecast[forecast["ds"] > last_date][
        ["ds", "yhat", "yhat_lower", "yhat_upper"]
    ].copy()

    # Clip negatives — you can't have negative orders
    forecast_future["yhat"]       = forecast_future["yhat"].clip(lower=0)
    forecast_future["yhat_lower"] = forecast_future["yhat_lower"].clip(lower=0)
    forecast_future["yhat_upper"] = forecast_future["yhat_upper"].clip(lower=0)

    # Add metadata columns for the database
    forecast_future["sku"]        = sku
    forecast_future["model_used"] = "prophet-1.3.0"
    forecast_future["generated_at"] = datetime.now()

    # Rename ds → forecast_date for the database table
    forecast_future = forecast_future.rename(columns={"ds": "forecast_date"})

    return forecast_future, forecast  # return full forecast for charting


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 3 — Build a Plotly chart for one SKU
# Shows: historical daily orders (blue) + forecast (orange) + confidence band
# ════════════════════════════════════════════════════════════════════════════
def build_chart(sku, history_df, forecast_df):
    """
    Builds and returns a Plotly figure for one SKU.
    history_df : full Prophet predict() output (includes historical fitted values)
    forecast_df: Prophet predict() output — we use last 30 rows for the forecast
    """

    last_hist_date = history_df["ds"].max() - pd.Timedelta(days=30)

    # Recent history only — last 90 days before forecast, keeps chart readable
    recent_history = history_df[history_df["ds"] > last_hist_date]

    fig = go.Figure()

    # Trace 1 — historical actual demand (blue dots)
    fig.add_trace(go.Scatter(
        x    = recent_history["ds"],
        y    = recent_history["yhat"].clip(lower=0),
        mode = "lines",
        name = "Historical (fitted)",
        line = dict(color="steelblue", width=1.5),
    ))

    # Trace 2 — forecast line (orange)
    future_rows = forecast_df[forecast_df["ds"] > history_df["ds"].max() - pd.Timedelta(days=1)]
    fig.add_trace(go.Scatter(
        x    = future_rows["ds"],
        y    = future_rows["yhat"].clip(lower=0),
        mode = "lines",
        name = "Forecast",
        line = dict(color="darkorange", width=2, dash="dash"),
    ))

    # Trace 3 — confidence band (shaded area between upper and lower bounds)
    fig.add_trace(go.Scatter(
        x    = pd.concat([future_rows["ds"], future_rows["ds"][::-1]]),
        y    = pd.concat([
                    future_rows["yhat_upper"].clip(lower=0),
                    future_rows["yhat_lower"].clip(lower=0)[::-1]
               ]),
        fill      = "toself",
        fillcolor = "rgba(255,165,0,0.15)",
        line      = dict(color="rgba(255,255,255,0)"),
        name      = "95% Confidence Band",
    ))

    fig.update_layout(
        title      = f"{sku} — 30-Day Demand Forecast",
        xaxis_title= "Date",
        yaxis_title= "Daily Orders",
        template   = "plotly_white",
        legend     = dict(orientation="h", y=-0.2),
        height     = 400,
    )

    return fig


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 4 — Write all forecast rows to PostgreSQL
# Uses append mode — clears old forecasts first to avoid duplicates on re-run
# ════════════════════════════════════════════════════════════════════════════
def write_forecasts(engine, all_forecasts_df):
    """
    Clears existing forecast rows and writes fresh ones.
    Truncate-then-append pattern keeps the table clean on every pipeline run.
    """
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE forecasts"))
        conn.commit()

    all_forecasts_df.to_sql(
        "forecasts",
        engine,
        if_exists = "append",
        index     = False,
    )
    print(f"\n   ✅ {len(all_forecasts_df)} forecast rows written to PostgreSQL")


# ════════════════════════════════════════════════════════════════════════════
# MAIN — orchestrates the full forecasting pipeline
# ════════════════════════════════════════════════════════════════════════════
def run_forecaster(engine=None, show_charts=True):
    """
    Full forecasting pipeline.
    Returns a dict of {sku: plotly_figure} for use in Streamlit app.
    """
    print("\n" + "=" * 55)
    print("  Module 1 — Demand Forecaster (Prophet)")
    print("=" * 55)

    if engine is None:
        engine = get_engine()

    # Step 1 — load data
    history = load_order_history(engine)

    all_forecasts = []
    charts        = {}

    # Step 2 — loop through every SKU, train model, generate forecast + chart
    print(f"\n   Training Prophet models for {len(SKUS)} SKUs...")
    for i, sku in enumerate(SKUS, 1):
        sku_df = history[history["sku"] == sku][["ds", "y"]].reset_index(drop=True)

        print(f"   [{i:02d}/{len(SKUS)}] {sku} — {len(sku_df)} days of history", end="")

        forecast_rows, full_forecast = forecast_sku(sku, sku_df)

        if forecast_rows is None:
            print("  ⚠️  skipped")
            continue

        print(f"  → forecast avg: {forecast_rows['yhat'].mean():.1f} orders/day")

        all_forecasts.append(forecast_rows)

        # Build chart — store in dict keyed by SKU
        fig = build_chart(sku, full_forecast, full_forecast)
        charts[sku] = fig

        # Optionally show chart immediately (useful when running standalone)
        if show_charts:
            fig.show()

    # Step 3 — combine all SKU forecasts and write to DB
    if all_forecasts:
        combined = pd.concat(all_forecasts, ignore_index=True)
        write_forecasts(engine, combined)

    print("\n   ✅ Forecaster complete!")
    print(f"   ✅ Charts generated for {len(charts)} SKUs")
    print("=" * 55)

    return charts


if __name__ == "__main__":
    run_forecaster(show_charts=True)