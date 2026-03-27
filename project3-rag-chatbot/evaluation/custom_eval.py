# evaluation/custom_eval.py
# ─────────────────────────────────────────────────────────────────────────────
# Custom metrics not covered by RAGAS:
#   Completeness → did the answer address all parts of the question?
#   Fairness     → did retrieval give balanced coverage across entities?
#
# Both are rule-based — no additional LLM calls needed.
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
import re
import pandas as pd
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── Completeness scoring ──────────────────────────────────────────────────────
# Each test question has required answer elements.
# We check how many appear in the generated answer.
# Score = elements_found / elements_required (0.0 → 1.0)

COMPLETENESS_RUBRIC = {
    "Which SKUs are at Critical stockout risk this week?": [
        "low", "no", "none", "risk"
    ],
    "What is the current order fulfillment rate?": [
        "94", "fulfil", "threshold", "95"
    ],
    "Which shift has the lowest labor productivity?": [
        "shift", "units", "hour", "department"
    ],
    "What is the total estimated annual waste from excess inventory?": [
        "excess", "inventory", "waste", "$"
    ],
    "How many OSHA incidents occurred in the last 30 days?": [
        "4", "incident", "injury", "violation"
    ],
    "What are the top 3 SKUs with worst inventory accuracy?": [
        "sku", "accuracy", "count", "expected"
    ],
    "What does the 30-day demand forecast show for SKU-0007?": [
        "sku-0007", "forecast", "12", "0.4"
    ],
    "Which carrier has the worst on-time shipping rate?": [
        "ontrac", "80", "threshold", "92"
    ],
    "What lean waste flags exist for the electronics category?": [
        "excess", "inventory", "high", "severity"
    ],
    "Compare night shift fulfillment rate vs day shift.": [
        "night", "am", "shift", "fulfil"
    ],
}


def score_completeness(question: str, answer: str) -> float:
    """
    Checks how many required elements appear in the answer.
    Elements are lowercase keywords — partial string match.
    Returns score 0.0 → 1.0.
    """
    rubric = COMPLETENESS_RUBRIC.get(question)
    if not rubric:
        return 0.5   # unknown question — neutral score

    answer_lower = answer.lower()
    found = sum(1 for elem in rubric if elem in answer_lower)
    return round(found / len(rubric), 4)


# ── Fairness scoring ──────────────────────────────────────────────────────────
# Measures source diversity in retrieved chunks.
# A fair retrieval covers multiple SKUs/shifts/carriers
# rather than always returning the same 1-2 entities.
# Score = unique_entities / total_chunks (0.0 → 1.0)

def score_fairness(chunks: list) -> float:
    """
    Measures diversity of retrieved chunks by counting unique
    entity values (SKU, department, carrier, date) across chunks.

    Args:
        chunks: List of RetrievedChunk objects

    Returns:
        Fairness score 0.0 → 1.0
        1.0 = all chunks from different entities (maximum diversity)
        0.2 = all 5 chunks from same entity (minimum diversity)
    """
    if not chunks:
        return 0.0

    entity_values = set()
    for chunk in chunks:
        meta = chunk.metadata
        # Extract the most specific entity identifier from metadata
        if "sku" in meta:
            entity_values.add(f"sku:{meta['sku']}")
        elif "carrier" in meta:
            entity_values.add(f"carrier:{meta['carrier']}")
        elif "department" in meta and "shift" in meta:
            entity_values.add(f"dept:{meta['department']}+shift:{meta['shift']}")
        elif "date" in meta:
            entity_values.add(f"date:{meta['date']}")
        else:
            entity_values.add(f"source:{meta.get('source', 'unknown')}")

    diversity = len(entity_values) / len(chunks)
    return round(diversity, 4)


# ── Run custom evaluation for one strategy ───────────────────────────────────

def evaluate_custom(strategy_name: str) -> pd.DataFrame:
    """
    Runs all 10 test questions through the strategy and
    scores completeness + fairness for each.
    """
    from evaluation.comparison_report import STRATEGY_META

    def _get_runner(name):
        if name == "zero_shot":
            from prompting.zero_shot import run
        elif name == "few_shot":
            from prompting.few_shot import run
        elif name == "hyde":
            from prompting.hyde import run
        elif name == "step_back":
            from prompting.step_back import run
        elif name == "subcontext":
            from prompting.subcontext import run
        elif name == "chain_of_thought":
            from prompting.chain_of_thought import run
        elif name == "self_rag":
            from prompting.self_rag import run
        else:
            raise ValueError(f"Unknown: {name}")
        return run

    print(f"\n{'=' * 55}")
    print(f"  Custom Eval: {strategy_name.upper()}")
    print(f"{'=' * 55}")

    run_fn    = _get_runner(strategy_name)
    questions = list(COMPLETENESS_RUBRIC.keys())
    rows      = []

    for i, question in enumerate(questions, start=1):
        print(f"  [{i}/{len(questions)}] {question[:50]}...")
        try:
            result       = run_fn(question)
            completeness = score_completeness(question, result.answer)
            fairness     = score_fairness(result.chunks)

            rows.append({
                "strategy":     strategy_name,
                "question":     question,
                "completeness": completeness,
                "fairness":     fairness,
                "answer_len":   len(result.answer),
            })
            print(f"    completeness={completeness:.2f}  "
                  f"fairness={fairness:.2f}")

        except Exception as e:
            print(f"    ✗ Error: {e}")
            rows.append({
                "strategy":     strategy_name,
                "question":     question,
                "completeness": 0.0,
                "fairness":     0.0,
                "answer_len":   0,
            })

    df = pd.DataFrame(rows)

    avg_c = df["completeness"].mean()
    avg_f = df["fairness"].mean()
    print(f"\n  Summary — {strategy_name}:")
    print(f"    Avg Completeness: {avg_c:.4f}")
    print(f"    Avg Fairness:     {avg_f:.4f}")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Main — run zero_shot only as a quick validation
# Full run across all strategies is triggered from comparison_report.py
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Custom Evaluation — Completeness + Fairness")
    print("=" * 55)

    # Test with zero_shot only — quick validation
    df = evaluate_custom("zero_shot")

    print("\n  Per-question breakdown:")
    print(f"  {'Question':<45} {'Comp':>6} {'Fair':>6}")
    print(f"  {'-'*45} {'-'*6} {'-'*6}")
    for _, row in df.iterrows():
        print(f"  {row['question'][:44]:<45} "
              f"{row['completeness']:>6.2f} "
              f"{row['fairness']:>6.2f}")

    os.makedirs("reports", exist_ok=True)
    df.to_csv("reports/custom_eval_zero_shot.csv", index=False)
    print("\n  Saved to: reports/custom_eval_zero_shot.csv")

    print("\n" + "=" * 55)
    print("  Custom eval complete")
    print("=" * 55)