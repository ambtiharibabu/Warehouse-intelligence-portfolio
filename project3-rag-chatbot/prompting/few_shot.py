# prompting/few_shot.py
# ─────────────────────────────────────────────────────────────────────────────
# Strategy 2 — Few-Shot
# Injects 3 labeled warehouse Q&A examples before the real question.
# Same retrieval as zero-shot — difference is purely in prompting.
# Hypothesis: more consistent format, better use of numbers, clearer citations.
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.retriever import retrieve, format_chunks_for_prompt
from pipeline.generator import generate
from prompting.result_types import StrategyResult
import config

# ── Few-shot examples ─────────────────────────────────────────────────────────
# Three representative warehouse Q&A pairs.
# Written to demonstrate: specific numbers, source citations, clear conclusions.
# Cover different KPI types so examples generalise across query domains.

FEW_SHOT_EXAMPLES = [
    {
        "question": "What is the fulfillment rate for SKU-0001 last week?",
        "answer": (
            "Based on orders data (Jan 1–7 2026), SKU-0001 had 18 total orders: "
            "17 fulfilled (94.4%), 1 late, 0 failed. Average fulfillment time was "
            "5.2 hours. This is below the 95% fulfillment threshold, indicating a "
            "minor performance gap for this SKU. "
            "[Source: orders | SKU-0001 | 2026-01-01 to 2026-01-07]"
        ),
    },
    {
        "question": "Which SKUs are at Critical stockout risk?",
        "answer": (
            "According to reorder_params data, no SKUs are currently at Critical "
            "stockout risk. All 20 SKUs are rated Low risk, with days of supply "
            "ranging from 36 to 427 days against lead times of 3–14 days. "
            "The warehouse is carrying significant excess inventory across all SKUs. "
            "[Source: reorder_params | all SKUs]"
        ),
    },
    {
        "question": "What was labor productivity on night shift this week?",
        "answer": (
            "Labor data shows night shift in the Receiving department processed "
            "8,432 units over 94.3 hours during the week of Mar 19–25 2026, "
            "achieving 89.4 units/hour — above the 85 unit/hour threshold. "
            "The Shipping department night shift averaged 91.2 units/hour over "
            "the same period. Both shifts are performing within acceptable range. "
            "[Source: labor | Night shift | 2026-03-19 to 2026-03-25]"
        ),
    },
]

# ── System prompt with few-shot examples embedded ────────────────────────────

def _build_system_prompt() -> str:
    """
    Builds the full system prompt with examples injected.
    Examples are formatted as numbered Q&A pairs so the LLM
    clearly sees the expected structure.
    """
    examples_text = ""
    for i, ex in enumerate(FEW_SHOT_EXAMPLES, start=1):
        examples_text += f"\nExample {i}:\n"
        examples_text += f"Q: {ex['question']}\n"
        examples_text += f"A: {ex['answer']}\n"

    return f"""You are a warehouse operations analyst with access to live operational data.

Here are examples of high-quality answers to warehouse operations questions:
{examples_text}
Now answer the following question using the same style:
- Lead with the direct answer (numbers first)
- Cite your data source using [Source: table | SKU | date range] notation
- End with a clear operational conclusion or recommendation
- Use ONLY the provided context — do not use outside knowledge
- If context is insufficient, say so clearly"""


def run(question: str) -> StrategyResult:
    """
    Few-shot RAG pipeline:
    1. Retrieve top-k chunks (identical to zero-shot)
    2. Build system prompt with 3 embedded Q&A examples
    3. Generate — LLM learns format from examples before answering

    Args:
        question: Plain English question from user

    Returns:
        StrategyResult with answer, chunks, token counts
    """
    # Step 1 — Retrieve (same as zero-shot)
    chunks  = retrieve(question, top_k=config.TOP_K)
    context = format_chunks_for_prompt(chunks)

    # Step 2 — Generate with example-enriched prompt
    response = generate(
        system_prompt = _build_system_prompt(),
        context       = context,
        question      = question,
        strategy_name = "few_shot",
    )

    return StrategyResult(
        answer            = response.answer,
        chunks            = chunks,
        strategy          = "few_shot",
        prompt_tokens     = response.prompt_tokens,
        completion_tokens = response.completion_tokens,
        total_tokens      = response.total_tokens,
        extra_info        = {"num_examples": len(FEW_SHOT_EXAMPLES)},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Strategy 2 — Few-Shot Test")
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

        print(f"  ANSWER:\n  {result.answer}")
        print(f"\n  Sources used:")
        for chunk in result.chunks:
            print(f"    - {chunk.source_label()} (score: {chunk.score:.4f})")
        print(f"\n  Tokens: {result.total_tokens} total "
              f"(+examples overhead vs zero-shot)")

    print("\n" + "=" * 60)
    print("  Few-shot test complete")
    print("=" * 60)