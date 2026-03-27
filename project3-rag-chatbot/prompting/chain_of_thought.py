# prompting/chain_of_thought.py
# ─────────────────────────────────────────────────────────────────────────────
# Strategy 6 — Chain-of-Thought (CoT)
# Forces the LLM to reason through 5 explicit steps before answering.
# Standard retrieval — difference is entirely in how the LLM is instructed
# to process the context before generating an answer.
#
# Best for: questions requiring calculation, comparison, or multi-step logic
# Example: "Which shift has lowest productivity?" requires comparing
#          multiple labor chunks before concluding
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.retriever import retrieve, format_chunks_for_prompt
from pipeline.generator import generate
from prompting.result_types import StrategyResult
import config

# ── System prompt ─────────────────────────────────────────────────────────────
# The 5-step structure is the core of this strategy.
# Each step constrains what can logically appear in the next step.
# Step 5 (confidence) is particularly valuable for RAGAS faithfulness scoring
# — the model self-reports what data is missing.

SYSTEM_PROMPT = """You are a warehouse operations analyst with access to live operational data.

When answering questions, you MUST follow this exact 5-step reasoning structure:

STEP 1 — DATA INVENTORY
List every piece of data available in the context. 
What tables, SKUs, date ranges, and KPI values are present?

STEP 2 — REASONING
What calculation, comparison, or logic is needed to answer the question?
Show your work explicitly — don't skip steps.

STEP 3 — INTERMEDIATE RESULT  
What does the data tell us after applying the reasoning from Step 2?
State numbers, rankings, or findings clearly.

STEP 4 — RECOMMENDATION
What specific action should the warehouse supervisor take based on Step 3?
Be concrete — name SKUs, shifts, carriers, or departments specifically.

STEP 5 — CONFIDENCE & GAPS
Rate your confidence 1-5 (5 = fully supported by data).
What data is missing that would improve this answer?

Always cite sources using [Source: table | SKU | date range] after each finding.
Use ONLY the provided context — do not use outside knowledge."""


def run(question: str) -> StrategyResult:
    """
    Chain-of-Thought pipeline:
    1. Retrieve top-k chunks (standard)
    2. Generate with 5-step reasoning structure enforced in system prompt

    Single LLM call — the reasoning structure is purely a prompting technique.
    No additional API calls needed vs zero-shot.

    Args:
        question: Plain English question from user

    Returns:
        StrategyResult with full step-by-step reasoning in answer
    """
    # ── Step 1: Standard retrieval ────────────────────────────────────────────
    chunks  = retrieve(question, top_k=config.TOP_K)
    context = format_chunks_for_prompt(chunks)

    # ── Step 2: Generate with CoT structure ───────────────────────────────────
    # Higher max_tokens than other strategies — 5 steps produces longer output
    response = generate(
        system_prompt = SYSTEM_PROMPT,
        context       = context,
        question      = question,
        strategy_name = "chain_of_thought",
        max_tokens    = 1200,   # CoT answers are structurally longer
    )

    return StrategyResult(
        answer            = response.answer,
        chunks            = chunks,
        strategy          = "chain_of_thought",
        prompt_tokens     = response.prompt_tokens,
        completion_tokens = response.completion_tokens,
        total_tokens      = response.total_tokens,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Strategy 6 — Chain-of-Thought Test")
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

        # CoT answers are long — show the full answer, it's the point
        print(f"  ANSWER (full reasoning chain):\n")
        # Indent each line for readability
        for line in result.answer.split("\n"):
            print(f"  {line}")

        print(f"\n  Sources retrieved:")
        for chunk in result.chunks:
            print(f"    - {chunk.source_label()} (score: {chunk.score:.4f})")
        print(f"\n  Tokens: {result.total_tokens} total")

    print("\n" + "=" * 60)
    print("  Chain-of-Thought test complete")
    print("=" * 60)