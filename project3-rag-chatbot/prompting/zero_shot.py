# prompting/zero_shot.py
# ─────────────────────────────────────────────────────────────────────────────
# Strategy 1 — Zero-Shot
# Retrieve → apply baseline system prompt → generate
# No examples. No multi-step reasoning.
# Serves as the benchmark baseline all other strategies are measured against.
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.retriever import retrieve, format_chunks_for_prompt
from pipeline.generator import generate
from prompting.result_types import StrategyResult
import config

# ── System prompt ─────────────────────────────────────────────────────────────
# This is the only instruction the LLM receives about how to behave.
# No examples, no chain of thought, no self-critique.
# Deliberately minimal so we have a clean baseline to compare against.

SYSTEM_PROMPT = """You are a warehouse operations analyst with access to live operational data.

Answer the question using ONLY the provided context. Do not use outside knowledge.

Rules:
1. Always cite your sources using [Source: table | SKU | date range] notation
2. Give specific numbers where the data supports it
3. If the context doesn't contain enough information to answer, say so clearly
4. Keep your answer focused and actionable for a warehouse supervisor"""


def run(question: str) -> StrategyResult:
    """
    Zero-shot RAG pipeline:
    1. Retrieve top-k chunks from ChromaDB
    2. Format chunks as numbered context block
    3. Generate answer with baseline system prompt

    Args:
        question: Plain English question from user

    Returns:
        StrategyResult with answer, chunks used, and token counts
    """
    # Step 1 — Retrieve
    chunks  = retrieve(question, top_k=config.TOP_K)
    context = format_chunks_for_prompt(chunks)

    # Step 2 — Generate
    response = generate(
        system_prompt = SYSTEM_PROMPT,
        context       = context,
        question      = question,
        strategy_name = "zero_shot",
    )

    return StrategyResult(
        answer            = response.answer,
        chunks            = chunks,
        strategy          = "zero_shot",
        prompt_tokens     = response.prompt_tokens,
        completion_tokens = response.completion_tokens,
        total_tokens      = response.total_tokens,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Strategy 1 — Zero-Shot Test")
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
        print(f"\n  Tokens: {result.total_tokens} total")

    print("\n" + "=" * 60)
    print("  Zero-shot test complete")
    print("=" * 60)