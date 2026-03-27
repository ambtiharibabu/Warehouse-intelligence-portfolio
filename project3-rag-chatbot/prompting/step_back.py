# prompting/step_back.py
# ─────────────────────────────────────────────────────────────────────────────
# Strategy 4 — Step-Back Prompting
# Step 1: Abstract the specific question to a general principle
# Step 2: Retrieve chunks for BOTH the abstract + specific question
# Step 3: Generate final answer using the combined context
#
# Best for: "why" questions, root cause analysis, trend questions
# Example: "Why did fulfillment drop Tuesday?" →
#          Abstract: "What causes fulfillment rate drops in warehouses?"
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.retriever import retrieve, retrieve_multi_query, format_chunks_for_prompt
from pipeline.generator import generate, generate_raw
from prompting.result_types import StrategyResult
import config

# ── Prompts ───────────────────────────────────────────────────────────────────

STEPBACK_ABSTRACTION_PROMPT = """You are a warehouse operations expert.
Given a specific operational question, identify the more general warehouse 
management principle or concept that would help answer it.

Return ONLY the abstracted question — one sentence, no explanation.

Examples:
Specific: "Why did SKU-0012 stock out on Tuesday?"
Abstract: "What are the common causes of SKU-level stockouts in warehouse operations?"

Specific: "What is the fulfillment rate for the AM shift last week?"
Abstract: "What factors drive order fulfillment rate differences across warehouse shifts?"

Specific: "Which carrier has the worst on-time rate?"
Abstract: "What metrics indicate poor carrier performance in warehouse shipping operations?"
"""

FINAL_SYSTEM_PROMPT = """You are a warehouse operations analyst with access to live operational data.
You have been provided with two types of context:
1. Specific operational data relevant to the exact question
2. General warehouse performance data that provides broader context

Use BOTH to give a complete, insightful answer.
Always cite your sources using [Source: table | SKU | date range] notation.
Give specific numbers where the data supports it.
End with a clear operational recommendation."""


def _abstract_question(question: str) -> str:
    """
    Step 1: Ask the LLM to abstract the specific question
    to a general warehouse operations principle.
    Returns just the abstracted question string.
    """
    messages = [
        {"role": "system", "content": STEPBACK_ABSTRACTION_PROMPT},
        {"role": "user",   "content": f"Specific question: {question}"},
    ]
    response = generate_raw(
        messages      = messages,
        strategy_name = "step_back_abstraction",
        temperature   = 0.1,
        max_tokens    = 100,   # just one sentence needed
    )
    return response.answer.strip()


def run(question: str) -> StrategyResult:
    """
    Step-Back pipeline:
    1. Abstract question to general principle (LLM call 1)
    2. Retrieve for BOTH abstract + specific question (deduplicated)
    3. Generate final answer from combined context (LLM call 2)

    Args:
        question: Plain English question from user

    Returns:
        StrategyResult — extra_info contains the abstracted question
    """
    # ── Step 1: Abstract the question ─────────────────────────────────────────
    abstract_question = _abstract_question(question)

    # ── Step 2: Retrieve for both queries, deduplicate ────────────────────────
    # retrieve_multi_query handles deduplication by chunk_id
    # keeping highest score per unique chunk across both result sets
    chunks = retrieve_multi_query(
        queries = [question, abstract_question],
        top_k   = config.TOP_K,
    )
    context = format_chunks_for_prompt(chunks)

    # ── Step 3: Generate using combined context ───────────────────────────────
    # Tell the LLM both the original and abstract question
    # so it understands the two-level context it's receiving
    enriched_question = (
        f"Specific question: {question}\n"
        f"General context question: {abstract_question}"
    )

    response = generate(
        system_prompt = FINAL_SYSTEM_PROMPT,
        context       = context,
        question      = enriched_question,
        strategy_name = "step_back",
    )

    return StrategyResult(
        answer            = response.answer,
        chunks            = chunks,
        strategy          = "step_back",
        prompt_tokens     = response.prompt_tokens,
        completion_tokens = response.completion_tokens,
        total_tokens      = response.total_tokens,
        extra_info        = {
            "abstract_question": abstract_question,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Strategy 4 — Step-Back Test")
    print("=" * 60)

    test_questions = [
        "Which SKUs are at stockout risk this week?",
        "What is the total estimated annual waste from excess inventory?",
        "Which carrier has the worst on-time shipping rate?",
    ]

    for question in test_questions:
        print(f"\n{'─' * 60}")
        print(f"  Q: {question}")
        print(f"{'─' * 60}")

        result = run(question)

        print(f"  ABSTRACTED TO: {result.extra_info['abstract_question']}")
        print(f"\n  FINAL ANSWER:\n  {result.answer}")
        print(f"\n  Sources (merged from both queries):")
        for chunk in result.chunks:
            print(f"    - {chunk.source_label()} (score: {chunk.score:.4f})")
        print(f"\n  Tokens: {result.total_tokens} total")

    print("\n" + "=" * 60)
    print("  Step-Back test complete")
    print("=" * 60)