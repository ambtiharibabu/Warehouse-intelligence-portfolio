"""
lean_detector.py
----------------
Applies three Lean waste detection rules per SKU:
    Type 1 — Excess Inventory   : safety_stock > 2x optimal
    Type 2 — Over-Ordering      : avg_order_qty > 1.5x EOQ
    Type 3 — Demand Planning    : stockout_rate > 5% trailing 90 days

Reads  : reorder_params, sku_master, orders
Writes : lean_waste_flags table
Prints : waste summary with total annual waste estimate

Run standalone : python modules/lean_detector.py
Called by      : main.py
"""

import os
import sys
import pandas as pd
import numpy as np
from sqlalchemy import text
from datetime import date, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.connection import get_engine


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 1 — Load all inputs
# ════════════════════════════════════════════════════════════════════════════
def load_inputs(engine):
    """
    Loads reorder_params, sku_master, and recent orders for waste detection.
    Returns three DataFrames.
    """

    with engine.connect() as conn:
        reorder_df = pd.read_sql(text("SELECT * FROM reorder_params"), conn)
        sku_df     = pd.read_sql(text("SELECT * FROM sku_master"), conn)

    # Load last 90 days of orders for stockout rate calculation
    # We use P1's original orders only (not BFILL) for recent performance
    cutoff = date.today() - timedelta(days=90)

    orders_query = text("""
        SELECT
            sku,
            order_date,
            status,
            COUNT(order_id) AS order_count
        FROM orders
        WHERE order_date >= :cutoff
        GROUP BY sku, order_date, status
        ORDER BY sku, order_date
    """)

    with engine.connect() as conn:
        orders_df = pd.read_sql(orders_query, conn, params={"cutoff": cutoff})

    print(f"   📦 Loaded {len(reorder_df)} SKUs from reorder_params")
    print(f"   📋 Loaded {len(sku_df)} SKUs from sku_master")
    print(f"   🗓️  Loaded orders from trailing 90 days "
          f"({cutoff} → {date.today()})")

    return reorder_df, sku_df, orders_df


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 2 — Waste Type 1: Excess Inventory
# Flag if current_stock > 2x the calculated safety_stock
# Logic: safety_stock is the scientifically correct buffer. Anything beyond
# 2x that level is pure waste — money sitting on a shelf.
# Severity:
#   Low    → stock is 2.0x – 3.0x safety stock
#   Medium → stock is 3.0x – 5.0x safety stock
#   High   → stock is > 5.0x safety stock
# ════════════════════════════════════════════════════════════════════════════
def detect_excess_inventory(reorder_df, sku_df):
    """
    Detects SKUs carrying significantly more stock than their safety stock
    level justifies.
    Returns a list of waste flag dicts.
    """
    flags = []

    merged = reorder_df.merge(
        sku_df[["sku", "holding_cost_per_day"]], on="sku", how="left"
    )

    for _, row in merged.iterrows():
        safety_stock = row["safety_stock"]

        # Avoid division by zero — skip if safety stock is essentially zero
        if safety_stock <= 0.1:
            continue

        ratio = row["current_stock"] / safety_stock

        if ratio <= 2.0:
            continue   # within acceptable range — no flag

        # Excess units = everything above 2x safety stock
        excess_units = row["current_stock"] - (2 * safety_stock)

        # Annual cost of holding those excess units
        annual_waste = excess_units * row["holding_cost_per_day"] * 365

        # Assign severity based on how extreme the ratio is
        if ratio <= 3.0:
            severity = "Low"
        elif ratio <= 5.0:
            severity = "Medium"
        else:
            severity = "High"

        flags.append({
            "sku":              row["sku"],
            "waste_type":       "excess_inventory",
            "severity":         severity,
            "annual_waste_usd": round(annual_waste, 2),
            "detail":           f"Stock is {ratio:.1f}x safety stock "
                                f"({row['current_stock']:.0f} units vs "
                                f"{safety_stock:.1f} optimal). "
                                f"Excess: {excess_units:.0f} units.",
        })

    print(f"\n   🔍 Waste Type 1 — Excess Inventory: {len(flags)} SKUs flagged")
    return flags


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 3 — Waste Type 2: Over-Ordering
# Flag if avg order quantity placed > 1.5x EOQ
# We approximate avg_order_qty from the orders table:
# total orders in trailing 90 days / number of distinct order events
# Note: our orders table tracks order lines not purchase orders,
# so we use daily order volume as a proxy for order quantity.
# Logic: if avg daily orders placed is far above EOQ/lead_time,
# the warehouse is receiving more per cycle than optimal.
# ════════════════════════════════════════════════════════════════════════════
def detect_over_ordering(reorder_df, sku_df, orders_df):
    """
    Detects SKUs where ordering behaviour significantly exceeds EOQ optimum.
    Returns a list of waste flag dicts.
    """
    flags = []

    # Calculate avg daily order volume per SKU from trailing 90 days
    daily_volume = orders_df.groupby("sku")["order_count"].sum().reset_index()
    daily_volume.columns = ["sku", "total_orders_90d"]
    daily_volume["avg_daily_orders"] = (daily_volume["total_orders_90d"] / 90).round(2)

    merged = reorder_df.merge(daily_volume, on="sku", how="left")
    merged = merged.merge(
        sku_df[["sku", "holding_cost_per_day", "order_cost"]], on="sku", how="left"
    )
    merged["avg_daily_orders"] = merged["avg_daily_orders"].fillna(0)

    for _, row in merged.iterrows():
        if row["eoq"] <= 0:
            continue

        # Effective order quantity proxy:
        # avg daily demand × lead time = how much arrives per replenishment cycle
        effective_order_qty = row["avg_daily_orders"] * row["lead_time_days"]

        ratio = effective_order_qty / row["eoq"] if row["eoq"] > 0 else 0

        if ratio <= 1.5:
            continue   # within 1.5x EOQ — acceptable

        # Excess quantity per order cycle
        excess_per_cycle = effective_order_qty - row["eoq"]

        # Approx number of order cycles per year
        annual_demand_proxy = row["avg_daily_orders"] * 365
        cycles_per_year     = (annual_demand_proxy / row["eoq"]
                                if row["eoq"] > 0 else 0)

        # Annual waste = excess units held per cycle × holding cost × cycles
        annual_waste = (excess_per_cycle
                        * row["holding_cost_per_day"]
                        * 365
                        / max(cycles_per_year, 1))

        if ratio <= 2.0:
            severity = "Low"
        elif ratio <= 3.0:
            severity = "Medium"
        else:
            severity = "High"

        flags.append({
            "sku":              row["sku"],
            "waste_type":       "over_ordering",
            "severity":         severity,
            "annual_waste_usd": round(annual_waste, 2),
            "detail":           f"Effective order qty {effective_order_qty:.1f} "
                                f"is {ratio:.1f}x EOQ ({row['eoq']:.1f}). "
                                f"Excess per cycle: {excess_per_cycle:.1f} units.",
        })

    print(f"   🔍 Waste Type 2 — Over-Ordering: {len(flags)} SKUs flagged")
    return flags


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 4 — Waste Type 3: Demand Planning Failure
# Flag if stockout_rate > 5% in trailing 90 days
# Stockout rate = failed orders / total orders per SKU
# A "failed" order in our data = status of 'failed' or 'late'
# ════════════════════════════════════════════════════════════════════════════
def detect_demand_planning_failure(reorder_df, sku_df, orders_df):
    """
    Detects SKUs where the historical stockout/failure rate exceeds 5%.
    Returns a list of waste flag dicts.
    """
    flags = []

    # Pivot orders by status to get fulfilled vs failed counts per SKU
    status_pivot = orders_df.pivot_table(
        index   = "sku",
        columns = "status",
        values  = "order_count",
        aggfunc = "sum",
        fill_value = 0
    ).reset_index()

    # Ensure both columns exist even if no failures in trailing window
    for col in ["fulfilled", "failed", "late"]:
        if col not in status_pivot.columns:
            status_pivot[col] = 0

    status_pivot["total_orders"]  = (status_pivot["fulfilled"]
                                     + status_pivot["failed"]
                                     + status_pivot["late"])
    status_pivot["failed_orders"] = (status_pivot["failed"]
                                     + status_pivot["late"])
    status_pivot["stockout_rate"] = (
        status_pivot["failed_orders"] / status_pivot["total_orders"]
    ).round(4)

    merged = status_pivot.merge(
        sku_df[["sku", "stockout_cost_per_unit"]], on="sku", how="left"
    )

    for _, row in merged.iterrows():
        if row["stockout_rate"] <= 0.05:
            continue   # under 5% threshold — acceptable

        # Annual waste estimate: failed orders × stockout cost per unit
        # Annualised from 90-day window
        annual_waste = (row["failed_orders"]
                        * row["stockout_cost_per_unit"]
                        * (365 / 90))

        rate_pct = row["stockout_rate"] * 100

        if rate_pct <= 8.0:
            severity = "Low"
        elif rate_pct <= 12.0:
            severity = "Medium"
        else:
            severity = "High"

        flags.append({
            "sku":              row["sku"],
            "waste_type":       "demand_planning_failure",
            "severity":         severity,
            "annual_waste_usd": round(annual_waste, 2),
            "detail":           f"Stockout rate {rate_pct:.1f}% "
                                f"({row['failed_orders']:.0f} failed/late "
                                f"of {row['total_orders']:.0f} orders "
                                f"in trailing 90 days).",
        })

    print(f"   🔍 Waste Type 3 — Demand Planning Failure: "
          f"{len(flags)} SKUs flagged")
    return flags


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 5 — Write all waste flags to lean_waste_flags table
# Truncate first so re-runs don't double-count
# ════════════════════════════════════════════════════════════════════════════
def write_waste_flags(engine, all_flags):
    """
    Clears existing flags and writes fresh ones.
    """
    if not all_flags:
        print("\n   ⚠️  No waste flags generated — nothing to write.")
        return

    flags_df = pd.DataFrame(all_flags)

    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE lean_waste_flags"))
        conn.commit()

    flags_df.to_sql(
        "lean_waste_flags",
        engine,
        if_exists = "append",
        index     = False,
    )

    print(f"\n   ✅ {len(flags_df)} waste flags written to lean_waste_flags")
    return flags_df


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 6 — Print waste summary
# ════════════════════════════════════════════════════════════════════════════
def print_waste_summary(all_flags):
    """
    Prints a formatted summary of all detected waste.
    """
    if not all_flags:
        print("\n   ✅ No waste flags detected across all 20 SKUs.")
        return

    flags_df = pd.DataFrame(all_flags)

    total_waste    = flags_df["annual_waste_usd"].sum()
    total_skus     = flags_df["sku"].nunique()
    total_flags    = len(flags_df)

    print("\n   📊 Lean Waste Summary by Type:")
    print(f"   {'Waste Type':<30} {'Flags':>6} {'Annual Waste $':>16}")
    print("   " + "-" * 55)

    for waste_type in ["excess_inventory", "over_ordering",
                       "demand_planning_failure"]:
        subset = flags_df[flags_df["waste_type"] == waste_type]
        if not subset.empty:
            print(f"   {waste_type:<30} "
                  f"{len(subset):>6} "
                  f"${subset['annual_waste_usd'].sum():>15,.2f}")

    print("   " + "-" * 55)
    print(f"   {'TOTAL':<30} {total_flags:>6} ${total_waste:>15,.2f}")

    print(f"\n   📊 Severity Breakdown:")
    for sev in ["High", "Medium", "Low"]:
        subset = flags_df[flags_df["severity"] == sev]
        bar    = "█" * len(subset)
        print(f"      {sev:<8} {bar} ({len(subset)} flags)")

    print(f"\n   🔴 Total estimated annual waste: "
          f"${total_waste:,.2f} across {total_skus} SKUs")


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════
def run_lean_detector(engine=None):
    """
    Full lean waste detection pipeline.
    Returns the flags DataFrame for use in main.py and app.py.
    """
    print("\n" + "=" * 55)
    print("  Module 4 — Lean Waste Detector")
    print("=" * 55)

    if engine is None:
        engine = get_engine()

    # Load inputs
    reorder_df, sku_df, orders_df = load_inputs(engine)

    # Run all three waste detectors
    flags_excess   = detect_excess_inventory(reorder_df, sku_df)
    flags_ordering = detect_over_ordering(reorder_df, sku_df, orders_df)
    flags_planning = detect_demand_planning_failure(reorder_df, sku_df,
                                                     orders_df)

    # Combine all flags
    all_flags = flags_excess + flags_ordering + flags_planning

    # Print summary
    print_waste_summary(all_flags)

    # Write to database
    flags_df = write_waste_flags(engine, all_flags)

    print("\n   ✅ Lean Detector complete!")
    print("=" * 55)

    return flags_df


if __name__ == "__main__":
    run_lean_detector()