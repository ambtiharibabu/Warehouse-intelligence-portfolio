"""
stockout_scorer.py
------------------
Reads current inventory, supplier lead times, and Prophet forecasts.
Calculates days-of-stock-remaining per SKU.
Assigns stockout risk tier: Critical / High / Medium / Low.
Writes initial rows to reorder_params table.

Risk logic:
    Critical → days_of_stock < 3
    High     → days_of_stock < lead_time_days
    Medium   → days_of_stock < lead_time_days * 2
    Low      → healthy stock level

Run standalone : python modules/stockout_scorer.py
Called by      : main.py
"""

import os
import sys
import pandas as pd
import numpy as np
from sqlalchemy import text
from datetime import date

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.connection import get_engine


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 1 — Load current inventory stock levels
# Uses the most recent actual_count per SKU from the inventory table.
# "Most recent" = the row with the latest count_date for each SKU.
# ════════════════════════════════════════════════════════════════════════════
def load_current_stock(engine):
    """
    Returns a DataFrame with one row per SKU showing the latest stock count.
    Columns: sku | current_stock | last_count_date
    """
    query = text("""
        SELECT
            sku,
            actual_count        AS current_stock,
            count_date          AS last_count_date
        FROM inventory
        WHERE (sku, count_date) IN (
            -- Subquery finds the most recent count date per SKU
            SELECT sku, MAX(count_date)
            FROM inventory
            GROUP BY sku
        )
    """)

    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    print(f"   📦 Loaded stock levels for {len(df)} SKUs")
    return df


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 2 — Load supplier lead times
# One row per SKU from the suppliers table we seeded in Step 2.
# ════════════════════════════════════════════════════════════════════════════
def load_lead_times(engine):
    """
    Returns a DataFrame with lead_time_days per SKU.
    Columns: sku | lead_time_days | supplier_id | reliability_score
    """
    query = text("""
        SELECT
            sku,
            lead_time_days,
            supplier_id,
            reliability_score
        FROM suppliers
    """)

    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    print(f"   🚚 Loaded lead times for {len(df)} SKUs")
    print(f"      Lead time range: {df['lead_time_days'].min()}–"
          f"{df['lead_time_days'].max()} days")
    return df


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 3 — Load forecasts and compute demand over each SKU's lead time
# For each SKU: sum the next lead_time_days worth of yhat values.
# This tells us: "how much demand will arrive during the replenishment window?"
# ════════════════════════════════════════════════════════════════════════════
def load_forecast_demand(engine, lead_times_df):
    """
    Reads the forecasts table and calculates:
        - avg_daily_forecast  : mean daily orders over the 30-day horizon
        - forecast_demand_in_lt: total demand during the lead time window

    Returns a DataFrame with columns: sku | avg_daily_forecast | forecast_demand_in_lt
    """
    query = text("""
        SELECT sku, forecast_date, yhat
        FROM forecasts
        ORDER BY sku, forecast_date
    """)

    with engine.connect() as conn:
        forecasts = pd.read_sql(query, conn)

    forecasts["forecast_date"] = pd.to_datetime(forecasts["forecast_date"])

    results = []

    for _, row in lead_times_df.iterrows():
        sku      = row["sku"]
        lt_days  = row["lead_time_days"]

        sku_fc = forecasts[forecasts["sku"] == sku].sort_values("forecast_date")

        if sku_fc.empty:
            results.append({
                "sku": sku,
                "avg_daily_forecast": 0,
                "forecast_demand_in_lt": 0,
            })
            continue

        # Average daily demand across full 30-day forecast
        avg_daily = sku_fc["yhat"].mean()

        # Total demand during the lead time window (first N days of forecast)
        # This is what we need to cover before replenishment arrives
        lt_demand = sku_fc.head(lt_days)["yhat"].sum()

        results.append({
            "sku":                    sku,
            "avg_daily_forecast":     round(avg_daily, 4),
            "forecast_demand_in_lt":  round(lt_demand, 2),
        })

    df = pd.DataFrame(results)
    print(f"   📈 Calculated forecast demand for {len(df)} SKUs")
    return df


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 4 — Calculate days of stock and assign risk tiers
# Core logic: days_of_stock = current_stock / avg_daily_forecast
# Risk tier based on how days_of_stock compares to lead time.
# ════════════════════════════════════════════════════════════════════════════
def calculate_risk(merged_df):
    """
    Takes the merged DataFrame (stock + lead times + forecast demand)
    and returns it with two new columns: days_of_stock and stockout_risk.

    Pipeline stock note:
        We assume pipeline_stock = 0 (no inbound PO data available).
        This is a conservative assumption — real ERP would add open POs here.
    """

    def days_of_stock(row):
        if row["avg_daily_forecast"] <= 0:
            return 999   # no demand forecast → no stockout risk
        return row["current_stock"] / row["avg_daily_forecast"]

    def risk_tier(row):
        dos  = row["days_of_stock"]
        lt   = row["lead_time_days"]

        if dos < 3:
            return "Critical"        # stockout within 3 days
        elif dos < lt:
            return "High"            # stockout before replenishment arrives
        elif dos < lt * 2:
            return "Medium"          # stockout within double the lead time
        else:
            return "Low"             # healthy stock level

    merged_df["days_of_stock"]  = merged_df.apply(days_of_stock, axis=1).round(1)
    merged_df["stockout_risk"]  = merged_df.apply(risk_tier, axis=1)

    return merged_df


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 5 — Write initial rows to reorder_params table
# We INSERT or UPDATE one row per SKU.
# Columns filled here: sku, current_stock, avg_daily_forecast,
#                      days_of_stock, lead_time_days,
#                      forecast_demand_in_lt, stockout_risk
# Remaining columns (eoq, safety_stock, rop, savings) filled by Step 6.
# ════════════════════════════════════════════════════════════════════════════
def write_reorder_params(engine, df):
    """
    Upserts stockout risk data into reorder_params.
    Uses INSERT ... ON CONFLICT to safely handle re-runs.
    """
    upsert_sql = text("""
        INSERT INTO reorder_params (
            sku, current_stock, avg_daily_forecast,
            days_of_stock, lead_time_days,
            forecast_demand_in_lt, stockout_risk, updated_at
        )
        VALUES (
            :sku, :current_stock, :avg_daily_forecast,
            :days_of_stock, :lead_time_days,
            :forecast_demand_in_lt, :stockout_risk, NOW()
        )
        ON CONFLICT (sku) DO UPDATE SET
            current_stock         = EXCLUDED.current_stock,
            avg_daily_forecast    = EXCLUDED.avg_daily_forecast,
            days_of_stock         = EXCLUDED.days_of_stock,
            lead_time_days        = EXCLUDED.lead_time_days,
            forecast_demand_in_lt = EXCLUDED.forecast_demand_in_lt,
            stockout_risk         = EXCLUDED.stockout_risk,
            updated_at            = NOW()
    """)

    with engine.connect() as conn:
        for _, row in df.iterrows():
            conn.execute(upsert_sql, {
                "sku":                    row["sku"],
                "current_stock":          float(row["current_stock"]),
                "avg_daily_forecast":     float(row["avg_daily_forecast"]),
                "days_of_stock":          float(row["days_of_stock"]),
                "lead_time_days":         int(row["lead_time_days"]),
                "forecast_demand_in_lt":  float(row["forecast_demand_in_lt"]),
                "stockout_risk":          row["stockout_risk"],
            })
        conn.commit()

    print(f"\n   ✅ {len(df)} rows written to reorder_params")


# ════════════════════════════════════════════════════════════════════════════
# MAIN — orchestrates the full stockout scoring pipeline
# ════════════════════════════════════════════════════════════════════════════
def run_stockout_scorer(engine=None):
    """
    Full stockout scoring pipeline.
    Returns the scored DataFrame for use in main.py and app.py.
    """
    print("\n" + "=" * 55)
    print("  Module 2 — Stockout Scorer")
    print("=" * 55)

    if engine is None:
        engine = get_engine()

    # Load all three inputs
    stock_df     = load_current_stock(engine)
    lead_df      = load_lead_times(engine)
    forecast_df  = load_forecast_demand(engine, lead_df)

    # Merge into one working DataFrame
    # Left join on sku — suppliers table is our anchor (20 SKUs)
    merged = lead_df.merge(stock_df,    on="sku", how="left")
    merged = merged.merge(forecast_df,  on="sku", how="left")

    # Fill any missing stock values with 0 (conservative)
    merged["current_stock"] = merged["current_stock"].fillna(0)

    # Calculate risk
    merged = calculate_risk(merged)

    # Print risk summary
    print("\n   📊 Stockout Risk Summary:")
    risk_counts = merged["stockout_risk"].value_counts()
    for tier in ["Critical", "High", "Medium", "Low"]:
        count = risk_counts.get(tier, 0)
        bar   = "█" * count
        print(f"      {tier:<10} {bar} ({count} SKUs)")

    print("\n   📋 Full SKU Risk Table:")
    print(f"   {'SKU':<12} {'Stock':>8} {'Days':>8} {'Lead':>6} "
          f"{'Fcst/LT':>10} {'Risk':<10}")
    print("   " + "-" * 60)

    for _, row in merged.sort_values("days_of_stock").iterrows():
        dos_display = f"{row['days_of_stock']:.1f}" if row['days_of_stock'] < 900 else "N/A"
        print(f"   {row['sku']:<12} "
              f"{row['current_stock']:>8.0f} "
              f"{dos_display:>8} "
              f"{row['lead_time_days']:>6} "
              f"{row['forecast_demand_in_lt']:>10.1f} "
              f"{row['stockout_risk']:<10}")

    # Write to database
    write_reorder_params(engine, merged)

    print("\n   ✅ Stockout Scorer complete!")
    print("=" * 55)

    return merged


if __name__ == "__main__":
    run_stockout_scorer()