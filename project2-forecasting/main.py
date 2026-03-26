"""
main.py
-------
Project 2 — Inventory Forecasting & Lean Waste Detection Engine
Full pipeline orchestrator. Runs all 6 modules in sequence.

Execution order (dependency chain):
    1. forecaster.py          → writes forecasts table
    2. stockout_scorer.py     → writes reorder_params (initial)
    3. reorder_calculator.py  → updates reorder_params (EOQ/ROP/savings)
    4. lean_detector.py       → writes lean_waste_flags
    5. erp_exporter.py        → writes erp_export_log + CSV
    6. excel_reporter.py      → writes MRP Excel report

Usage:
    python main.py                  ← full pipeline, no charts
    python main.py --charts         ← full pipeline + Plotly charts per SKU
    python main.py --skip-forecast  ← skips Prophet (uses existing forecasts)

Run time: ~60-90 seconds (Prophet fitting dominates)
"""

import sys
import time
import logging
import argparse
from datetime import datetime

from db.connection import get_engine

# ── Import all pipeline modules ──────────────────────────────────────────────
from modules.forecaster          import run_forecaster
from modules.stockout_scorer     import run_stockout_scorer
from modules.reorder_calculator  import run_reorder_calculator
from modules.lean_detector       import run_lean_detector
from modules.erp_exporter        import run_erp_exporter
from modules.excel_reporter      import run_excel_reporter


# ── Logging setup ─────────────────────────────────────────────────────────────
# Writes to both terminal AND a log file in reports/
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)s  %(message)s",
    datefmt = "%H:%M:%S",
    handlers = [
        logging.StreamHandler(sys.stdout),          # terminal output
    ]
)
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# HELPER — Step runner with timing and error handling
# Wraps each module call so we get consistent timing + error messages
# ════════════════════════════════════════════════════════════════════════════
def run_step(step_name, func, *args, **kwargs):
    """
    Runs a pipeline step, measures execution time, and handles errors.

    Parameters:
        step_name : display name for logging
        func      : the run_*() function to call
        *args     : positional arguments to pass to func
        **kwargs  : keyword arguments to pass to func

    Returns:
        (result, elapsed_seconds) on success
        (None, elapsed_seconds)   on failure
    """
    print(f"\n{'─' * 55}")
    logger.info(f"▶  Starting: {step_name}")
    start = time.time()

    try:
        result  = func(*args, **kwargs)
        elapsed = round(time.time() - start, 1)
        logger.info(f"✅ Completed: {step_name} ({elapsed}s)")
        return result, elapsed

    except Exception as e:
        elapsed = round(time.time() - start, 1)
        logger.error(f"❌ FAILED: {step_name} ({elapsed}s)")
        logger.error(f"   Error: {e}")
        # Re-raise so main() can decide whether to stop or continue
        raise


# ════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ════════════════════════════════════════════════════════════════════════════
def main():

    # ── Parse command-line arguments ─────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="Project 2 — Inventory Forecasting & Lean Waste Engine"
    )
    parser.add_argument(
        "--charts",
        action  = "store_true",
        help    = "Show Plotly forecast charts per SKU (opens browser tabs)"
    )
    parser.add_argument(
        "--skip-forecast",
        action  = "store_true",
        help    = "Skip Prophet forecasting step (uses existing forecasts table)"
    )
    args = parser.parse_args()

    # ── Pipeline header ───────────────────────────────────────────────────
    pipeline_start = time.time()

    print("\n" + "═" * 55)
    print("  PROJECT 2 — INVENTORY FORECASTING PIPELINE")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 55)

    # ── Shared database connection ────────────────────────────────────────
    # Created once, passed to every module — efficient connection reuse
    print("\n🔌 Connecting to PostgreSQL...")
    engine = get_engine()
    print("   ✅ Connected\n")

    # ── Track timing for final summary ────────────────────────────────────
    timings = {}
    charts  = {}

    # ── Step 1 — Demand Forecaster ────────────────────────────────────────
    if args.skip_forecast:
        logger.info("⏭️  Skipping forecaster (--skip-forecast flag set)")
        logger.info("   Using existing rows in forecasts table")
        timings["Forecaster"] = 0
    else:
        try:
            charts, elapsed = run_step(
                "Demand Forecaster (Prophet)",
                run_forecaster,
                engine     = engine,
                show_charts = args.charts,
            )
            timings["Forecaster"] = elapsed
        except Exception:
            print("\n❌ Pipeline stopped: Forecaster failed.")
            print("   Fix the error above and re-run.")
            sys.exit(1)

    # ── Step 2 — Stockout Scorer ──────────────────────────────────────────
    try:
        scored_df, elapsed = run_step(
            "Stockout Scorer",
            run_stockout_scorer,
            engine = engine,
        )
        timings["Stockout Scorer"] = elapsed
    except Exception:
        print("\n❌ Pipeline stopped: Stockout Scorer failed.")
        sys.exit(1)

    # ── Step 3 — Reorder Calculator ───────────────────────────────────────
    try:
        reorder_df, elapsed = run_step(
            "Reorder Calculator (EOQ + ROP)",
            run_reorder_calculator,
            engine = engine,
        )
        timings["Reorder Calculator"] = elapsed
    except Exception:
        print("\n❌ Pipeline stopped: Reorder Calculator failed.")
        sys.exit(1)

    # ── Step 4 — Lean Waste Detector ──────────────────────────────────────
    try:
        waste_df, elapsed = run_step(
            "Lean Waste Detector",
            run_lean_detector,
            engine = engine,
        )
        timings["Lean Detector"] = elapsed
    except Exception:
        print("\n❌ Pipeline stopped: Lean Detector failed.")
        sys.exit(1)

    # ── Step 5 — ERP Exporter ─────────────────────────────────────────────
    try:
        sap_df, elapsed = run_step(
            "ERP Exporter (SAP MM Format)",
            run_erp_exporter,
            engine = engine,
        )
        timings["ERP Exporter"] = elapsed
    except Exception:
        # ERP export is non-critical — log and continue to Excel report
        logger.warning("⚠️  ERP Exporter failed — continuing to Excel report")
        timings["ERP Exporter"] = -1

    # ── Step 6 — Excel MRP Report ─────────────────────────────────────────
    try:
        report_path, elapsed = run_step(
            "Excel MRP Report Builder",
            run_excel_reporter,
            engine = engine,
        )
        timings["Excel Reporter"] = elapsed
    except Exception:
        logger.warning("⚠️  Excel Reporter failed")
        timings["Excel Reporter"] = -1

    # ── Final summary ─────────────────────────────────────────────────────
    total_elapsed = round(time.time() - pipeline_start, 1)

    print("\n" + "═" * 55)
    print("  ✅ PIPELINE COMPLETE")
    print(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 55)

    print("\n  📊 Step Timing Summary:")
    print(f"  {'Step':<35} {'Time':>8}")
    print("  " + "-" * 45)
    for step, secs in timings.items():
        if secs == 0:
            display = "skipped"
        elif secs == -1:
            display = "failed"
        else:
            display = f"{secs}s"
        print(f"  {step:<35} {display:>8}")
    print("  " + "-" * 45)
    print(f"  {'TOTAL':<35} {total_elapsed}s")

    print("\n  📁 Output Files:")
    from pathlib import Path
    reports_dir = Path("reports")
    if reports_dir.exists():
        for f in sorted(reports_dir.iterdir()):
            if f.suffix in [".xlsx", ".csv"]:
                size_kb = round(f.stat().st_size / 1024, 1)
                print(f"     {f.name:<45} {size_kb} KB")

    print("\n  📋 PostgreSQL Tables Updated:")
    tables = ["forecasts", "reorder_params", "lean_waste_flags",
              "erp_export_log"]
    for t in tables:
        print(f"     ✅ {t}")

    print("\n  🚀 To launch the Streamlit dashboard:")
    print("     streamlit run app.py")
    print("═" * 55 + "\n")


if __name__ == "__main__":
    main()