# prompting/subcontext.py
# ─────────────────────────────────────────────────────────────────────────────
# Strategy 5 — Sub-Context (Contextual Compression)
# Step 1: Retrieve top-k chunks (standard retrieval)
# Step 2: Compress — extract only sentences relevant to the question
# Step 3: Generate final answer from compressed context
#
# Benefit: removes noise from retrieved chunks, improves Precision@k
# Best for: questions where chunks contain relevant + irrelevant content mixed
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.retriever import retrieve, format_chunks_for_prompt
from pipeline.generator import generate, generate_raw
from prompting.result_types import StrategyResult
import config

# ── Prompts ───────────────────────────────────────────────────────────────────

COMPRESSION_PROMPT = """You are a precise information extractor.
Given a question and a block of context, extract ONLY the sentences and 
data points that are directly relevant to answering the question.

Rules:
- Remove all irrelevant content
- Keep all numbers, SKU names, dates, and percentages that relate to the question
- Preserve source labels like [1], [2] etc.
- If an entire chunk is irrelevant, write "IRRELEVANT" for that chunk
- Output only the compressed content — no explanation, no preamble"""

FINAL_SYSTEM_PROMPT = """You are a warehouse operations analyst with access to live operational data.
Answer the question using ONLY the provided context.
The context has been pre-filtered to contain only relevant information.
Always cite your sources using [Source: table | SKU | date range] notation.
Give specific numbers where the data supports it.
Be concise — the context is already focused, so your answer should be too."""


def _compress_context(question: str, context: str) -> str:
    """
    Step 2: Ask the LLM to extract only the relevant sentences
    from the full retrieved context.
    Returns compressed context string.
    """
    messages = [
        {"role": "system", "content": COMPRESSION_PROMPT},
        {
            "role": "user",
            "content": (
                f"Question: {question}\n\n"
                f"Context to compress:\n{context}"
            ),
        },
    ]
    response = generate_raw(
        messages      = messages,
        strategy_name = "subcontext_compression",
        temperature   = 0.0,   # fully deterministic — extraction not creativity
        max_tokens    = 600,   # compressed context should be much shorter
    )
    return response.answer.strip()


def run(question: str) -> StrategyResult:
    """
    Sub-Context pipeline:
    1. Retrieve top-k chunks (standard)
    2. Compress — LLM extracts only relevant sentences (LLM call 1)
    3. Generate final answer from compressed context (LLM call 2)

    Args:
        question: Plain English question from user

    Returns:
        StrategyResult — extra_info contains original and compressed context
    """
    # ── Step 1: Standard retrieval ────────────────────────────────────────────
    chunks          = retrieve(question, top_k=config.TOP_K)
    full_context    = format_chunks_for_prompt(chunks)

    # ── Step 2: Compress context ──────────────────────────────────────────────
    compressed_context = _compress_context(question, full_context)

    # Fallback: if compression produced nothing useful, use full context
    if not compressed_context or len(compressed_context) < 50:
        compressed_context = full_context

    # ── Step 3: Generate from compressed context ──────────────────────────────
    response = generate(
        system_prompt = FINAL_SYSTEM_PROMPT,
        context       = compressed_context,
        question      = question,
        strategy_name = "subcontext",
    )

    return StrategyResult(
        answer            = response.answer,
        chunks            = chunks,
        strategy          = "subcontext",
        prompt_tokens     = response.prompt_tokens,
        completion_tokens = response.completion_tokens,
        total_tokens      = response.total_tokens,
        extra_info        = {
            "full_context_length":       len(full_context),
            "compressed_context_length": len(compressed_context),
            "compression_ratio":         round(
                len(compressed_context) / len(full_context), 2
            ),
            "compressed_context":        compressed_context,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Strategy 5 — Sub-Context (Contextual Compression) Test")
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

        ratio = result.extra_info["compression_ratio"]
        full_len = result.extra_info["full_context_length"]
        comp_len = result.extra_info["compressed_context_length"]

        print(f"  COMPRESSION: {full_len} chars → {comp_len} chars "
              f"({ratio:.0%} of original)")
        print(f"\n  COMPRESSED CONTEXT:")
        print(f"  {result.extra_info['compressed_context'][:300]}...")
        print(f"\n  FINAL ANSWER:\n  {result.answer}")
        print(f"\n  Sources retrieved:")
        for chunk in result.chunks:
            print(f"    - {chunk.source_label()} (score: {chunk.score:.4f})")
        print(f"\n  Tokens: {result.total_tokens} total")

    print("\n" + "=" * 60)
    print("  Sub-Context test complete")
    print("=" * 60)