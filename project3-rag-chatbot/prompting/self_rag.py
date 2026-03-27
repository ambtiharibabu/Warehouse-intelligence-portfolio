# prompting/self_rag.py
# ─────────────────────────────────────────────────────────────────────────────
# Strategy 7 — Self-RAG
# Step 1: Generate initial answer with standard retrieval
# Step 2: Self-critique — is the answer fully supported by context?
#         Score confidence 1-5. Identify what's missing.
# Step 3: If confidence < 4 → reformulate query → re-retrieve → regenerate
# Step 4: Return final answer with confidence score
#
# Goal: highest faithfulness — only commits to answers the data supports
# Cost: up to 3 LLM calls per question (most expensive strategy)
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.retriever import retrieve, format_chunks_for_prompt
from pipeline.generator import generate, generate_raw
from prompting.result_types import StrategyResult
import config

# ── Prompts ───────────────────────────────────────────────────────────────────

INITIAL_SYSTEM_PROMPT = """You are a warehouse operations analyst with access to live operational data.
Answer the question using ONLY the provided context.
Cite your sources using [Source: table | SKU | date range] notation.
Give specific numbers where the data supports it.
If the context is insufficient, say so clearly."""

CRITIQUE_PROMPT = """You are a rigorous fact-checker for warehouse operations reports.

You will be given:
1. A question
2. The context (retrieved data) used to answer it
3. An answer that was generated

Your job: evaluate whether the answer is FULLY supported by the context.

Respond in this exact format (no other text):
CONFIDENCE: [1-5]
SUPPORTED: [YES/PARTIAL/NO]
GAP: [What specific information is missing or what claim is not supported by context?]
REFORMULATED_QUERY: [A better search query that would retrieve the missing information]

Scoring guide:
5 = Every claim in the answer is directly supported by the context
4 = Answer is mostly supported, minor gaps that don't affect the conclusion
3 = Answer is partially supported, significant gaps exist
2 = Answer makes claims not in the context
1 = Answer is largely unsupported or contradicts the context"""

REGENERATION_SYSTEM_PROMPT = """You are a warehouse operations analyst with access to live operational data.
You are regenerating an answer with additional context retrieved to fill identified gaps.
Use BOTH the original context and the new context provided.
Be precise — only claim what the combined context directly supports.
Cite all sources using [Source: table | SKU | date range] notation."""


def _critique_answer(
    question: str,
    context: str,
    answer: str,
) -> dict:
    """
    Step 2: Ask the LLM to critique its own answer.
    Returns a dict with confidence score, supported status, gap, and
    a reformulated query for re-retrieval if needed.
    """
    messages = [
        {"role": "system", "content": CRITIQUE_PROMPT},
        {
            "role": "user",
            "content": (
                f"QUESTION: {question}\n\n"
                f"CONTEXT USED:\n{context}\n\n"
                f"ANSWER TO EVALUATE:\n{answer}"
            ),
        },
    ]
    response = generate_raw(
        messages      = messages,
        strategy_name = "self_rag_critique",
        temperature   = 0.0,   # fully deterministic critique
        max_tokens    = 200,
    )

    # Parse the structured critique response
    critique = {
        "confidence":         3,     # defaults if parsing fails
        "supported":          "PARTIAL",
        "gap":                "Unknown gap",
        "reformulated_query": question,  # fallback to original query
    }

    for line in response.answer.strip().split("\n"):
        line = line.strip()
        if line.startswith("CONFIDENCE:"):
            try:
                critique["confidence"] = int(line.split(":")[1].strip())
            except ValueError:
                pass
        elif line.startswith("SUPPORTED:"):
            critique["supported"] = line.split(":")[1].strip()
        elif line.startswith("GAP:"):
            critique["gap"] = line.split(":", 1)[1].strip()
        elif line.startswith("REFORMULATED_QUERY:"):
            critique["reformulated_query"] = line.split(":", 1)[1].strip()

    return critique


def run(question: str) -> StrategyResult:
    """
    Self-RAG pipeline:
    1. Retrieve top-k chunks + generate initial answer (LLM call 1)
    2. Critique initial answer — score confidence 1-5 (LLM call 2)
    3a. If confidence >= 4: return initial answer
    3b. If confidence < 4: reformulate query → re-retrieve → regenerate (LLM call 3)

    Args:
        question: Plain English question from user

    Returns:
        StrategyResult — extra_info contains critique details and iteration count
    """
    # ── Step 1: Initial retrieval + generation ────────────────────────────────
    chunks          = retrieve(question, top_k=config.TOP_K)
    context         = format_chunks_for_prompt(chunks)

    initial_response = generate(
        system_prompt = INITIAL_SYSTEM_PROMPT,
        context       = context,
        question      = question,
        strategy_name = "self_rag_initial",
    )
    initial_answer = initial_response.answer

    # ── Step 2: Self-critique ─────────────────────────────────────────────────
    critique = _critique_answer(question, context, initial_answer)
    confidence = critique["confidence"]

    # ── Step 3a: High confidence — return initial answer ──────────────────────
    if confidence >= 4:
        return StrategyResult(
            answer            = initial_answer,
            chunks            = chunks,
            strategy          = "self_rag",
            prompt_tokens     = initial_response.prompt_tokens,
            completion_tokens = initial_response.completion_tokens,
            total_tokens      = initial_response.total_tokens,
            extra_info        = {
                "confidence":   confidence,
                "supported":    critique["supported"],
                "gap":          critique["gap"],
                "iterations":   1,
                "retriggered":  False,
            },
        )

    # ── Step 3b: Low confidence — re-retrieve and regenerate ──────────────────
    reformulated_query = critique["reformulated_query"]

    # Retrieve using the reformulated query
    new_chunks   = retrieve(reformulated_query, top_k=config.TOP_K)
    new_context  = format_chunks_for_prompt(new_chunks)

    # Combine original and new context for regeneration
    combined_context = (
        f"=== ORIGINAL CONTEXT ===\n{context}\n\n"
        f"=== ADDITIONAL CONTEXT (retrieved to fill gap) ===\n{new_context}"
    )

    # Regenerate with combined context
    final_response = generate(
        system_prompt = REGENERATION_SYSTEM_PROMPT,
        context       = combined_context,
        question      = question,
        strategy_name = "self_rag",
        max_tokens    = 1200,
    )

    # Merge chunk lists — original + new, deduplicated by chunk_id
    seen_ids   = {c.chunk_id: c for c in chunks}
    for c in new_chunks:
        if c.chunk_id not in seen_ids:
            seen_ids[c.chunk_id] = c
    all_chunks = sorted(seen_ids.values(), key=lambda c: c.score, reverse=True)

    return StrategyResult(
        answer            = final_response.answer,
        chunks            = all_chunks,
        strategy          = "self_rag",
        prompt_tokens     = final_response.prompt_tokens,
        completion_tokens = final_response.completion_tokens,
        total_tokens      = (
            initial_response.total_tokens + final_response.total_tokens
        ),
        extra_info        = {
            "confidence":          confidence,
            "supported":           critique["supported"],
            "gap":                 critique["gap"],
            "reformulated_query":  reformulated_query,
            "iterations":          2,
            "retriggered":         True,
            "initial_answer":      initial_answer,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Strategy 7 — Self-RAG Test")
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
        info   = result.extra_info

        print(f"  CONFIDENCE:  {info['confidence']}/5")
        print(f"  SUPPORTED:   {info['supported']}")
        print(f"  ITERATIONS:  {info['iterations']}")
        print(f"  RETRIGGERED: {info['retriggered']}")

        if info["retriggered"]:
            print(f"\n  GAP IDENTIFIED: {info['gap']}")
            print(f"  REFORMULATED:   {info['reformulated_query']}")
            print(f"\n  INITIAL ANSWER: {info['initial_answer'][:150]}...")

        print(f"\n  FINAL ANSWER:\n")
        for line in result.answer.split("\n"):
            print(f"  {line}")

        print(f"\n  Chunks used ({len(result.chunks)} total):")
        for chunk in result.chunks[:5]:
            print(f"    - {chunk.source_label()} (score: {chunk.score:.4f})")

        print(f"\n  Total tokens: {result.total_tokens} "
              f"({'3 LLM calls' if info['retriggered'] else '2 LLM calls'})")

    print("\n" + "=" * 60)
    print("  Self-RAG test complete — all 7 strategies built")
    print("=" * 60)