"""
reorder_calculator.py
---------------------
Runs EOQ, Safety Stock, and Reorder Point formulas per SKU.
Reads  : sku_master (cost params) + reorder_params (stock/lead time from Step 5)
         + orders (to calculate demand standard deviation)
Updates: reorder_params table — fills EOQ, safety_stock, optimal_rop,
         current_rop, gap, potential_savings_usd columns
Prints : savings summary across all 20 SKUs

Formulas:
    EOQ          = sqrt(2 × D × S / H)
    Safety Stock = Z × σ(demand) × sqrt(lead_time)    Z=1.65 for 95% SL
    ROP          = (avg_daily_demand × lead_time) + safety_stock

Run standalone : python modules/reorder_calculator.py
Called by      : main.py
"""

import os
import sys
import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.connection import get_engine

# Z-score for 95% service level — industry standard for warehouse operations
Z_95 = 1.65


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 1 — Load all inputs needed for the formulas
# Pulls sku_master (costs), reorder_params (stock/lead time), and
# orders (to compute demand variability / standard deviation)
# ════════════════════════════════════════════════════════════════════════════
def load_inputs(engine):
    """
    Returns three DataFrames:
        sku_master_df   : cost parameters per SKU
        reorder_df      : current stock + lead times (written by Step 5)
        demand_stats_df : avg and std dev of daily demand per SKU from orders
    """

    # Load sku_master — holds D (annual demand), S (order cost), H (holding cost)
    with engine.connect() as conn:
        sku_master_df = pd.read_sql(text("SELECT * FROM sku_master"), conn)
        reorder_df    = pd.read_sql(text("SELECT * FROM reorder_params"), conn)

    # Calculate demand statistics directly from the orders table
    # We need: avg daily orders per SKU + standard deviation of daily orders
    demand_query = text("""
        SELECT
            sku,
            order_date,
            COUNT(order_id) AS daily_orders
        FROM orders
        GROUP BY sku, order_date
        ORDER BY sku, order_date
    """)

    with engine.connect() as conn:
        daily_demand = pd.read_sql(demand_query, conn)

    # Group by SKU to get avg and std dev of daily demand
    demand_stats = daily_demand.groupby("sku")["daily_orders"].agg(
        avg_daily_demand = "mean",
        std_daily_demand = "std"
    ).reset_index()

    # Fill any NaN std dev with 0 — happens if a SKU has only one data point
    demand_stats["std_daily_demand"] = demand_stats["std_daily_demand"].fillna(0)

    print(f"   📋 Loaded {len(sku_master_df)} SKUs from sku_master")
    print(f"   📊 Calculated demand stats for {len(demand_stats)} SKUs")
    print(f"   📦 Loaded {len(reorder_df)} SKUs from reorder_params")

    return sku_master_df, reorder_df, demand_stats


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 2 — Run EOQ, Safety Stock, and ROP formulas
# All three formulas applied per SKU in one vectorised pass.
# ════════════════════════════════════════════════════════════════════════════
def calculate_reorder_params(sku_master_df, reorder_df, demand_stats_df):
    """
    Merges all inputs and applies the three supply chain formulas.
    Returns a DataFrame with one row per SKU containing all calculated values.
    """

    # Merge all three DataFrames on sku
    df = sku_master_df.merge(reorder_df[["sku", "lead_time_days",
                                          "current_stock", "avg_daily_forecast"]],
                              on="sku", how="left")
    df = df.merge(demand_stats_df, on="sku", how="left")

    # ── EOQ Formula ──────────────────────────────────────────────────────
    # EOQ = sqrt(2 × D × S / H)
    # D = annual_demand (from sku_master)
    # S = order_cost    (from sku_master) — fixed cost per purchase order
    # H = holding_cost_per_day × 365     — annual holding cost per unit
    # Result: optimal units to order each time you place an order

    df["annual_holding_cost"] = df["holding_cost_per_day"] * 365

    df["eoq"] = np.sqrt(
        (2 * df["annual_demand"] * df["order_cost"])
        / df["annual_holding_cost"]
    ).round(1)

    # ── Safety Stock Formula ─────────────────────────────────────────────
    # Safety Stock = Z × σ(demand) × sqrt(lead_time)
    # Z    = 1.65 (95% service level — we want to avoid stockouts 95% of time)
    # σ    = std_daily_demand — how variable daily orders are
    # sqrt(lead_time) — variability compounds over the lead time window

    df["safety_stock"] = (
        Z_95
        * df["std_daily_demand"]
        * np.sqrt(df["lead_time_days"])
    ).round(1)

    # ── Reorder Point Formula ────────────────────────────────────────────
    # ROP = (avg_daily_demand × lead_time) + safety_stock
    # This is the stock level at which you should place a new order.
    # By the time it arrives, you'll have consumed exactly safety_stock units.

    df["optimal_rop"] = (
        (df["avg_daily_demand"] * df["lead_time_days"])
        + df["safety_stock"]
    ).round(1)

    # ── Current ROP (reverse-engineered from current stock behaviour) ────
    # We don't have actual purchase order history to know what ROP they use.
    # Best proxy: current_stock / 2 — assumes they reorder at half their
    # stock level, which is a common informal rule in small warehouses.
    df["current_rop"] = (df["current_stock"] / 2).round(1)

    # ── Gap — difference between current and optimal ROP ─────────────────
    # Positive gap: current ROP is below optimal → reordering too late
    # Negative gap: current ROP is above optimal → reordering too early
    df["gap"] = (df["optimal_rop"] - df["current_rop"]).round(1)

    # ── Potential Savings ─────────────────────────────────────────────────
    # Estimated annual cost of the gap.
    # If reordering too late (positive gap): risk stockout cost
    # If reordering too early (negative gap): paying unnecessary holding cost
    # We use abs(gap) × holding_cost_per_day × 365 as a conservative estimate

    df["potential_savings_usd"] = (
        df["gap"].abs()
        * df["holding_cost_per_day"]
        * 365
    ).round(2)

    return df


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 3 — Update reorder_params table with calculated values
# Uses UPDATE — rows already exist from Step 5, we're filling blank columns
# ════════════════════════════════════════════════════════════════════════════
def update_reorder_params(engine, df):
    """
    Updates the EOQ, safety stock, ROP, gap, and savings columns
    in reorder_params. Rows were created in Step 5 — this fills the rest.
    """

    update_sql = text("""
        UPDATE reorder_params SET
            eoq                   = :eoq,
            safety_stock          = :safety_stock,
            optimal_rop           = :optimal_rop,
            current_rop           = :current_rop,
            gap                   = :gap,
            potential_savings_usd = :potential_savings_usd,
            updated_at            = NOW()
        WHERE sku = :sku
    """)

    with engine.connect() as conn:
        for _, row in df.iterrows():
            conn.execute(update_sql, {
                "sku":                    row["sku"],
                "eoq":                    float(row["eoq"]),
                "safety_stock":           float(row["safety_stock"]),
                "optimal_rop":            float(row["optimal_rop"]),
                "current_rop":            float(row["current_rop"]),
                "gap":                    float(row["gap"]),
                "potential_savings_usd":  float(row["potential_savings_usd"]),
            })
        conn.commit()

    print(f"\n   ✅ {len(df)} rows updated in reorder_params")


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 4 — Print savings summary
# The headline number for portfolio/executive storytelling
# ════════════════════════════════════════════════════════════════════════════
def print_savings_summary(df):
    """
    Prints a formatted savings summary table and total.
    """
    total_savings = df["potential_savings_usd"].sum()
    total_skus    = len(df)

    print("\n   💰 Reorder Optimisation Savings Summary:")
    print(f"   {'SKU':<12} {'EOQ':>8} {'Safety St':>10} "
          f"{'Curr ROP':>10} {'Opt ROP':>10} {'Gap':>8} {'Savings $':>12}")
    print("   " + "-" * 74)

    for _, row in df.sort_values("potential_savings_usd",
                                  ascending=False).iterrows():
        print(f"   {row['sku']:<12} "
              f"{row['eoq']:>8.1f} "
              f"{row['safety_stock']:>10.1f} "
              f"{row['current_rop']:>10.1f} "
              f"{row['optimal_rop']:>10.1f} "
              f"{row['gap']:>8.1f} "
              f"${row['potential_savings_usd']:>11,.2f}")

    print("   " + "-" * 74)
    print(f"   {'TOTAL POTENTIAL SAVINGS':<52} "
          f"${total_savings:>11,.2f}")
    print(f"\n   📌 Across {total_skus} SKUs — based on gap × holding cost × 365 days")
    print("   📌 Positive gap = reordering too late  "
          "(stockout risk)")
    print("   📌 Negative gap = reordering too early "
          "(excess holding cost)")


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════
def run_reorder_calculator(engine=None):
    """
    Full reorder calculation pipeline.
    Returns the results DataFrame for use in main.py and app.py.
    """
    print("\n" + "=" * 55)
    print("  Module 3 — Reorder Calculator (EOQ + ROP)")
    print("=" * 55)

    if engine is None:
        engine = get_engine()

    # Load inputs
    sku_master_df, reorder_df, demand_stats_df = load_inputs(engine)

    # Run formulas
    results_df = calculate_reorder_params(sku_master_df, reorder_df,
                                           demand_stats_df)

    # Print savings summary
    print_savings_summary(results_df)

    # Write to database
    update_reorder_params(engine, results_df)

    print("\n   ✅ Reorder Calculator complete!")
    print("=" * 55)

    return results_df


if __name__ == "__main__":
    run_reorder_calculator()