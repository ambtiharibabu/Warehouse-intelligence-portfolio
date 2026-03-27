# evaluation/ragas_eval.py
# ─────────────────────────────────────────────────────────────────────────────
# RAGAS evaluation — scores each prompting strategy across 4 metrics:
#   Faithfulness, Answer Relevancy, Context Precision, Context Recall
#
# Usage:
#   python evaluation/ragas_eval.py --strategy zero_shot
#   python evaluation/ragas_eval.py --strategy all
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
import argparse
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── Ground truth answers ──────────────────────────────────────────────────────
GROUND_TRUTH = {
    "Which SKUs are at Critical stockout risk this week?":
        "No SKUs are at Critical stockout risk. All 20 SKUs have a stockout risk "
        "rating of Low, with days of supply ranging from 36 to 427 days, well above "
        "their lead times of 3-14 days.",

    "What is the current order fulfillment rate?":
        "The overall order fulfillment rate is approximately 94% based on order history. "
        "Out of 18,214 total orders, approximately 94% were fulfilled, 4% were late, "
        "and 2% failed. This is below the 95% fulfillment threshold.",

    "Which shift has the lowest labor productivity?":
        "Labor productivity varies by department and shift. The threshold is 85 units "
        "per hour. Productivity data is available by department and shift combination "
        "across weekly windows. Specific shift comparison requires reviewing labor "
        "chunks by shift and department.",

    "What is the total estimated annual waste from excess inventory?":
        "The total estimated annual waste from excess inventory is $1,001,209 across "
        "20 SKUs all flagged as High severity excess inventory waste. Additionally "
        "15 SKUs have demand planning failure flags totaling $38,673, bringing total "
        "annual waste to $1,039,883.",

    "How many OSHA incidents occurred in the last 30 days?":
        "There are 4 total OSHA safety incidents on record: 2 injuries and 2 violations, "
        "all rated low severity. Incidents occurred across AM and PM shifts.",

    "What are the top 3 SKUs with worst inventory accuracy?":
        "Inventory accuracy data is available per SKU showing expected vs actual counts. "
        "The worst performing SKUs can be identified from the inventory table by "
        "comparing actual_count to expected_count across all count dates per SKU.",

    "What does the 30-day demand forecast show for SKU-0007?":
        "The 30-day demand forecast for SKU-0007 from 2026-03-26 to 2026-04-24 shows "
        "a total projected demand of 12.0 units with an average of 0.4 units per day. "
        "This is a low-demand SKU. The forecast was generated using Prophet time-series "
        "forecasting.",

    "Which carrier has the worst on-time shipping rate?":
        "OnTrac has the worst on-time shipping rate. In the period 2026-01-08 to "
        "2026-01-14, OnTrac achieved only 80.0% on-time delivery (12 of 15 shipments), "
        "which is below the 92% threshold. USPS performance varies from 82.6% to 95% "
        "across different periods.",

    "What lean waste flags exist for the electronics category?":
        "Electronics SKUs (SKU-0001 through SKU-0004 and others in the Electronics "
        "category) have excess inventory waste flags rated High severity. Each flag "
        "indicates stock levels far exceeding safety stock levels, with annual waste "
        "costs ranging from tens of thousands to hundreds of thousands of dollars.",

    "Compare night shift fulfillment rate vs day shift.":
        "Order fulfillment data is available broken down by shift (AM, PM, Night) "
        "across weekly windows per SKU. Both AM and PM shifts show fulfillment rates "
        "around 94-95%. Night shift data is also available in the same format for "
        "direct comparison.",
}

# ── Strategy registry ─────────────────────────────────────────────────────────

def _get_strategy_runner(strategy_name: str):
    if strategy_name == "zero_shot":
        from prompting.zero_shot import run
    elif strategy_name == "few_shot":
        from prompting.few_shot import run
    elif strategy_name == "hyde":
        from prompting.hyde import run
    elif strategy_name == "step_back":
        from prompting.step_back import run
    elif strategy_name == "subcontext":
        from prompting.subcontext import run
    elif strategy_name == "chain_of_thought":
        from prompting.chain_of_thought import run
    elif strategy_name == "self_rag":
        from prompting.self_rag import run
    else:
        raise ValueError(f"Unknown strategy: {strategy_name}")
    return run

# ── Run one strategy against all test questions ───────────────────────────────

def evaluate_strategy(strategy_name: str) -> pd.DataFrame:
    from ragas import evaluate
    from ragas.metrics._faithfulness import Faithfulness
    from ragas.metrics._answer_relevance import AnswerRelevancy
    from ragas.metrics._context_precision import ContextPrecision
    from ragas.metrics._context_recall import ContextRecall
    from datasets import Dataset

    print(f"\n{'=' * 60}")
    print(f"  Evaluating strategy: {strategy_name.upper()}")
    print(f"{'=' * 60}")

    run_fn    = _get_strategy_runner(strategy_name)
    questions = list(GROUND_TRUTH.keys())
    eval_rows = []

    for i, question in enumerate(questions, start=1):
        print(f"\n  [{i}/{len(questions)}] {question[:55]}...")
        try:
            result   = run_fn(question)
            contexts = [chunk.text for chunk in result.chunks]
            eval_rows.append({
                "question":     question,
                "answer":       result.answer,
                "contexts":     contexts,
                "ground_truth": GROUND_TRUTH[question],
            })
            print(f"    ✓ Answer generated ({result.total_tokens} tokens)")
        except Exception as e:
            print(f"    ✗ Error: {e}")
            eval_rows.append({
                "question":     question,
                "answer":       f"[Error: {str(e)}]",
                "contexts":     ["[Error retrieving context]"],
                "ground_truth": GROUND_TRUTH[question],
            })

    dataset = Dataset.from_list(eval_rows)

    print(f"\n  Running RAGAS scoring (this makes additional LLM calls)...")

    from openai import OpenAI as OpenAIClient
    from ragas.llms import llm_factory
    from ragas.embeddings import HuggingfaceEmbeddings

    _openai_client = OpenAIClient(
        api_key  = config.OPENROUTER_API_KEY,
        base_url = config.OPENROUTER_BASE_URL,
    )

    ragas_llm = llm_factory(
        model  = config.MODEL_NAME,
        client = _openai_client,
    )

    ragas_embeddings = HuggingfaceEmbeddings(
        model_name = config.EMBEDDING_MODEL
    )
    ragas_embeddings = RagasOpenAIEmbeddings(
        model  = "text-embedding-ada-002",
        client = _openai_client,
    )

    scores = evaluate(
        dataset    = dataset,
        metrics    = [
            Faithfulness(),
            AnswerRelevancy(),
            ContextPrecision(),
            ContextRecall(),
        ],
        llm        = ragas_llm,
        embeddings = ragas_embeddings,
    )

    scores_df            = scores.to_pandas()
    scores_df["strategy"] = strategy_name

    print(f"\n  Results for {strategy_name.upper()}:")
    print(f"  {'Metric':<25} {'Score':>8}")
    print(f"  {'-'*25} {'-'*8}")
    numeric_cols = scores_df.select_dtypes(include="number").columns
    for col in numeric_cols:
        avg = scores_df[col].mean()
        print(f"  {col:<25} {avg:>8.4f}")

    return scores_df

# ── Run all strategies ────────────────────────────────────────────────────────

def evaluate_all_strategies() -> pd.DataFrame:
    strategies = [
        "zero_shot", "few_shot", "hyde", "step_back",
        "subcontext", "chain_of_thought", "self_rag"
    ]
    all_results = []
    for strategy in strategies:
        try:
            df = evaluate_strategy(strategy)
            all_results.append(df)
        except Exception as e:
            print(f"\n  ✗ Strategy {strategy} failed: {e}")

    if not all_results:
        print("No results collected.")
        return pd.DataFrame()

    return pd.concat(all_results, ignore_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strategy",
        type    = str,
        default = "zero_shot",
        help    = "Strategy: zero_shot | few_shot | hyde | step_back | "
                  "subcontext | chain_of_thought | self_rag | all"
    )
    args = parser.parse_args()

    if args.strategy == "all":
        results_df = evaluate_all_strategies()
    else:
        results_df = evaluate_strategy(args.strategy)

    if not results_df.empty:
        os.makedirs("reports", exist_ok=True)
        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"reports/ragas_{args.strategy}_{timestamp}.csv"
        results_df.to_csv(output_path, index=False)
        print(f"\n  Results saved to: {output_path}")