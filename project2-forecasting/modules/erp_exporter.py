"""
erp_exporter.py
---------------
Reads reorder_params and formats output as SAP MM MRP II flat file.
Column mapping mirrors SAP MM module MRP II planning fields:
    MATNR | WERKS | MINBE | EISBE | MABST | BSTMI | BSTMA

This file can be imported directly into SAP via transaction MM17
or equivalent ERP batch upload — demonstrating direct integration
readiness with enterprise systems.

Writes : erp_export_log table (audit trail of every export)
Saves  : reports/sap_mrp_export_YYYYMMDD.csv

Run standalone : python modules/erp_exporter.py
Called by      : main.py
"""

import os
import sys
import pandas as pd
from sqlalchemy import text
from datetime import date, datetime
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.connection import get_engine

# Plant code — in SAP every material belongs to a plant (warehouse location)
# We use WH01 as our single warehouse plant code
PLANT_CODE = "WH01"


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 1 — Load reorder_params
# This is our single source of truth — all formulas already calculated
# ════════════════════════════════════════════════════════════════════════════
def load_reorder_params(engine):
    """
    Loads the completed reorder_params table.
    All EOQ, safety stock, and ROP values must already be populated
    (requires Steps 5 and 6 to have run first).
    """
    query = text("""
        SELECT
            sku,
            optimal_rop,
            safety_stock,
            eoq,
            current_stock,
            lead_time_days
        FROM reorder_params
        ORDER BY sku
    """)

    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    # Validate — check for any NULLs that would indicate Steps 5/6 didn't run
    null_check = df[["optimal_rop", "safety_stock", "eoq"]].isnull().sum().sum()
    if null_check > 0:
        raise ValueError(
            f"⚠️  {null_check} NULL values found in reorder_params. "
            "Run stockout_scorer.py and reorder_calculator.py first."
        )

    print(f"   📦 Loaded {len(df)} SKUs from reorder_params")
    return df


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 2 — Build SAP MM flat file format
# Renames and transforms columns to match SAP field naming exactly.
# All values rounded to integers — SAP MM planning fields don't use decimals.
# ════════════════════════════════════════════════════════════════════════════
def build_sap_export(df):
    """
    Transforms reorder_params into SAP MM MRP II format.

    SAP field mapping:
        MATNR → Material Number    = sku
        WERKS → Plant              = WH01 (hardcoded)
        MINBE → Reorder Point      = optimal_rop
        EISBE → Safety Stock       = safety_stock
        MABST → Maximum Stock      = optimal_rop × 3 (max before overstock)
        BSTMI → Minimum Lot Size   = eoq × 0.5 (smallest acceptable order)
        BSTMA → Maximum Lot Size   = eoq × 2   (largest acceptable order)

    Returns a DataFrame in SAP column order.
    """

    sap_df = pd.DataFrame()

    # Direct mappings
    sap_df["MATNR"] = df["sku"]
    sap_df["WERKS"] = PLANT_CODE

    # ROP → SAP Reorder Point (MINBE)
    # Round up — SAP doesn't accept fractional units
    sap_df["MINBE"] = df["optimal_rop"].apply(
        lambda x: max(1, int(round(x)))
    )

    # Safety Stock → SAP Safety Stock (EISBE)
    sap_df["EISBE"] = df["safety_stock"].apply(
        lambda x: max(0, int(round(x)))
    )

    # Max Stock → 3× ROP (proxy: enough for 3 full replenishment cycles)
    sap_df["MABST"] = (df["optimal_rop"] * 3).apply(
        lambda x: max(1, int(round(x)))
    )

    # Min Lot Size → 50% of EOQ (smallest order that still makes economic sense)
    sap_df["BSTMI"] = (df["eoq"] * 0.5).apply(
        lambda x: max(1, int(round(x)))
    )

    # Max Lot Size → 200% of EOQ (largest order before holding costs dominate)
    sap_df["BSTMA"] = (df["eoq"] * 2).apply(
        lambda x: max(1, int(round(x)))
    )

    return sap_df


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 3 — Save CSV to reports/ folder
# Filename includes today's date for easy versioning
# ════════════════════════════════════════════════════════════════════════════
def save_csv(sap_df):
    """
    Saves the SAP export DataFrame as a pipe-delimited CSV.
    Pipe delimiter (|) is standard for SAP flat file imports — 
    commas can appear in material descriptions and cause parsing errors.
    """

    # Ensure reports/ folder exists
    reports_dir = Path(__file__).parent.parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    filename  = f"sap_mrp_export_{date.today().strftime('%Y%m%d')}.csv"
    filepath  = reports_dir / filename

    # SAP flat files use pipe delimiter — safer than comma for ERP imports
    sap_df.to_csv(filepath, sep="|", index=False)

    print(f"\n   💾 SAP flat file saved:")
    print(f"      {filepath}")
    print(f"      {len(sap_df)} material records")
    print(f"      Delimiter: pipe (|) — SAP MM17 compatible")

    return str(filepath)


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 4 — Log the export to erp_export_log table
# Creates an audit trail — every export is recorded with timestamp
# ════════════════════════════════════════════════════════════════════════════
def log_export(engine, sku_count, file_path):
    """
    Writes one row to erp_export_log recording this export run.
    """
    insert_sql = text("""
        INSERT INTO erp_export_log (export_date, sku_count, file_path, exported_by)
        VALUES (NOW(), :sku_count, :file_path, 'p2_pipeline')
    """)

    with engine.connect() as conn:
        conn.execute(insert_sql, {
            "sku_count": sku_count,
            "file_path": file_path,
        })
        conn.commit()

    print(f"   ✅ Export logged to erp_export_log")


# ════════════════════════════════════════════════════════════════════════════
# BLOCK 5 — Print SAP export preview
# ════════════════════════════════════════════════════════════════════════════
def print_export_preview(sap_df):
    """
    Prints a formatted preview of the SAP flat file output.
    """
    print("\n   📋 SAP MM MRP II Export Preview (first 5 rows):")
    print(f"\n   {'MATNR':<12} {'WERKS':<6} {'MINBE':>7} "
          f"{'EISBE':>7} {'MABST':>7} {'BSTMI':>7} {'BSTMA':>7}")
    print("   " + "-" * 58)

    for _, row in sap_df.head(5).iterrows():
        print(f"   {row['MATNR']:<12} {row['WERKS']:<6} "
              f"{row['MINBE']:>7} {row['EISBE']:>7} "
              f"{row['MABST']:>7} {row['BSTMI']:>7} "
              f"{row['BSTMA']:>7}")

    print(f"   ... ({len(sap_df)} total rows)")

    print(f"""
   📌 SAP Field Reference:
      MATNR = Material Number    WERKS = Plant Code
      MINBE = Reorder Point      EISBE = Safety Stock
      MABST = Max Stock Level    BSTMI = Min Lot Size
      BSTMA = Max Lot Size

   📌 Import via SAP transaction MM17 or equivalent ERP batch upload.
   📌 Delimiter: pipe (|) — avoids conflicts with material descriptions.
    """)


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════
def run_erp_exporter(engine=None):
    """
    Full ERP export pipeline.
    Returns the SAP DataFrame for use in main.py and app.py.
    """
    print("\n" + "=" * 55)
    print("  Module 5 — ERP Exporter (SAP MM Format)")
    print("=" * 55)

    if engine is None:
        engine = get_engine()

    # Load, transform, save, log
    reorder_df = load_reorder_params(engine)
    sap_df     = build_sap_export(reorder_df)

    print_export_preview(sap_df)

    file_path  = save_csv(sap_df)
    log_export(engine, len(sap_df), file_path)

    print("\n   ✅ ERP Exporter complete!")
    print("=" * 55)

    return sap_df


if __name__ == "__main__":
    run_erp_exporter()