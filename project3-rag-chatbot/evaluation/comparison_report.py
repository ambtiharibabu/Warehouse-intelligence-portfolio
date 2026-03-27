# evaluation/comparison_report.py
# ─────────────────────────────────────────────────────────────────────────────
# Reads RAGAS evaluation CSV(s) and produces:
#   1. Console benchmark table (for README)
#   2. reports/benchmark_table.csv (for Streamlit UI)
#   3. Interpretation notes per strategy
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
import glob
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Strategy metadata ─────────────────────────────────────────────────────────
# Human-readable labels, LLM call counts, and interpretation notes
# Used to enrich the benchmark table beyond raw numbers

STRATEGY_META = {
    "zero_shot": {
        "label":       "Zero-Shot",
        "llm_calls":   1,
        "description": "Baseline — retrieve + generate with no examples or reasoning structure.",
        "best_for":    "Simple factual queries. Fast and cheap.",
    },
    "few_shot": {
        "label":       "Few-Shot",
        "llm_calls":   1,
        "description": "Injects 3 labeled Q&A examples before the real question.",
        "best_for":    "Consistent answer formatting. Best faithfulness score.",
    },
    "hyde": {
        "label":       "HyDE",
        "llm_calls":   2,
        "description": "Generates hypothetical answer first, embeds that for retrieval.",
        "best_for":    "Specific entity queries (e.g. SKU-0007 forecast). Worst on vague queries.",
    },
    "step_back": {
        "label":       "Step-Back",
        "llm_calls":   2,
        "description": "Abstracts question to general principle, retrieves for both levels.",
        "best_for":    "Why/root-cause questions. Adds operational framework.",
    },
    "subcontext": {
        "label":       "Sub-Context",
        "llm_calls":   2,
        "description": "Compresses retrieved chunks to only relevant sentences before generating.",
        "best_for":    "Token efficiency. Honest refusals when data is missing.",
    },
    "chain_of_thought": {
        "label":       "Chain-of-Thought",
        "llm_calls":   1,
        "description": "Forces 5-step explicit reasoning: inventory → logic → result → recommendation → confidence.",
        "best_for":    "Complex multi-step questions. Best self-reported confidence gaps.",
    },
    "self_rag": {
        "label":       "Self-RAG",
        "llm_calls":   "2-3",
        "description": "Generates → self-critiques → re-retrieves if confidence < 4/5.",
        "best_for":    "Highest context precision. Best when answer accuracy is critical.",
    },
}


def find_latest_csv(strategy: str = "all") -> str:
    """Find the most recent RAGAS output CSV for the given strategy."""
    pattern = f"reports/ragas_{strategy}_*.csv"
    files   = glob.glob(pattern)
    if not files:
        # Fall back to any ragas CSV
        files = glob.glob("reports/ragas_*.csv")
    if not files:
        raise FileNotFoundError(
            "No RAGAS results CSV found in reports/. "
            "Run: python evaluation/ragas_eval.py --strategy all"
        )
    return sorted(files)[-1]   # most recent by filename timestamp


def build_benchmark_table(csv_path: str) -> pd.DataFrame:
    """
    Reads raw RAGAS CSV and produces a clean summary table
    with one row per strategy showing average metric scores.
    """
    df = pd.read_csv(csv_path)

    # Identify available metric columns
    metric_cols = [c for c in df.columns if c in [
        "faithfulness", "answer_relevancy",
        "context_precision", "context_recall"
    ]]

    # Aggregate: mean score per strategy per metric
    summary = df.groupby("strategy")[metric_cols].mean().round(4)

    # Add metadata columns
    summary["Label"]       = summary.index.map(
        lambda s: STRATEGY_META.get(s, {}).get("label", s)
    )
    summary["LLM Calls"]   = summary.index.map(
        lambda s: STRATEGY_META.get(s, {}).get("llm_calls", "?")
    )
    summary["Best For"]    = summary.index.map(
        lambda s: STRATEGY_META.get(s, {}).get("best_for", "")
    )

    # Sort by faithfulness descending (most important metric for RAG)
    summary = summary.sort_values("faithfulness", ascending=False)

    return summary


def print_benchmark_table(summary: pd.DataFrame):
    """Prints a formatted benchmark table to console."""

    print("\n" + "=" * 70)
    print("  P3 RAG PIPELINE — 7-STRATEGY BENCHMARK TABLE")
    print("  Evaluation: RAGAS metrics across 10 warehouse test questions")
    print("=" * 70)

    # Header
    print(f"\n  {'Strategy':<20} {'Faithful':>9} {'Precision':>10} "
          f"{'Recall':>8} {'Calls':>6}")
    print(f"  {'-'*20} {'-'*9} {'-'*10} {'-'*8} {'-'*6}")

    for strategy, row in summary.iterrows():
        faith  = f"{row['faithfulness']:.4f}" if pd.notna(row.get('faithfulness')) else "n/a"
        prec   = f"{row['context_precision']:.4f}" if pd.notna(row.get('context_precision')) else "n/a"
        rec    = f"{row['context_recall']:.4f}" if pd.notna(row.get('context_recall')) else "n/a"
        calls  = str(row['LLM Calls'])
        label  = row['Label']

        print(f"  {label:<20} {faith:>9} {prec:>10} {rec:>8} {calls:>6}")

    print(f"\n  Note: answer_relevancy = n/a across all strategies.")
    print(f"  Root cause: OpenRouter does not expose an embeddings endpoint")
    print(f"  compatible with RAGAS answer_relevancy scoring. All other")
    print(f"  metrics are fully computed using the Llama 3 8B judge model.")

    print("\n" + "─" * 70)
    print("  METRIC DEFINITIONS")
    print("─" * 70)
    print("  Faithfulness    → Every answer claim is supported by retrieved context")
    print("  Context Precision → Retrieved chunks were actually useful for the answer")
    print("  Context Recall  → Retrieved chunks contained all needed information")
    print("  (higher = better for all metrics, scale 0.0 → 1.0)")

    print("\n" + "─" * 70)
    print("  KEY FINDINGS")
    print("─" * 70)

    # Auto-generate findings from actual scores
    best_faith  = summary["faithfulness"].idxmax()
    best_prec   = summary["context_precision"].idxmax()
    best_recall = summary["context_recall"].idxmax()
    worst_faith = summary["faithfulness"].idxmin()

    print(f"  ✓ Best Faithfulness:      "
          f"{STRATEGY_META[best_faith]['label']} "
          f"({summary.loc[best_faith, 'faithfulness']:.4f})")
    print(f"  ✓ Best Context Precision: "
          f"{STRATEGY_META[best_prec]['label']} "
          f"({summary.loc[best_prec, 'context_precision']:.4f})")
    print(f"  ✓ Best Context Recall:    "
          f"{STRATEGY_META[best_recall]['label']} "
          f"({summary.loc[best_recall, 'context_recall']:.4f})")
    print(f"  ⚠ Lowest Faithfulness:   "
          f"{STRATEGY_META[worst_faith]['label']} "
          f"({summary.loc[worst_faith, 'faithfulness']:.4f})")

    print("\n" + "─" * 70)
    print("  STRATEGY DESCRIPTIONS")
    print("─" * 70)
    for strategy, row in summary.iterrows():
        meta = STRATEGY_META.get(strategy, {})
        print(f"\n  {row['Label']} ({row['LLM Calls']} LLM call(s))")
        print(f"  {meta.get('description', '')}")
        print(f"  → Best for: {meta.get('best_for', '')}")

    print("\n" + "=" * 70)


def save_benchmark_csv(summary: pd.DataFrame):
    """Saves clean benchmark table to reports/ for Streamlit UI to load."""
    os.makedirs("reports", exist_ok=True)
    out_path = "reports/benchmark_table.csv"
    summary.reset_index().to_csv(out_path, index=False)
    print(f"\n  Benchmark table saved to: {out_path}")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        type    = str,
        default = None,
        help    = "Path to RAGAS CSV. If not provided, uses most recent in reports/"
    )
    args = parser.parse_args()

    csv_path = args.csv if args.csv else find_latest_csv("all")
    print(f"\n  Reading: {csv_path}")

    summary  = build_benchmark_table(csv_path)
    print_benchmark_table(summary)
    save_benchmark_csv(summary)