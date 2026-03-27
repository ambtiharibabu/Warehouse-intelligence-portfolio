# prompting/hyde.py
# ─────────────────────────────────────────────────────────────────────────────
# Strategy 3 — HyDE (Hypothetical Document Embeddings)
# Step 1: Ask LLM to write a hypothetical answer (no retrieval yet)
# Step 2: Embed the hypothetical answer (not the original question)
# Step 3: Use that embedding to retrieve real chunks from ChromaDB
# Step 4: Generate final answer from real retrieved chunks
#
# Why it works: the hypothetical answer uses the same vocabulary and
# structure as real data chunks — it retrieves more relevant content
# than embedding the raw question directly.
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.retriever import retrieve, format_chunks_for_prompt, _load_model
from pipeline.generator import generate, generate_raw
from prompting.result_types import StrategyResult
import config

# ── Prompts ───────────────────────────────────────────────────────────────────

HYPOTHESIS_PROMPT = """You are a warehouse analyst writing a detailed operational report.
Write a specific, data-rich answer to the following question as if you had 
full access to warehouse data. Use realistic warehouse terminology, include 
plausible numbers, and write in the style of an operational data summary.
This will be used to improve search — not shown to the user directly.
Keep it to 3-5 sentences."""

FINAL_SYSTEM_PROMPT = """You are a warehouse operations analyst with access to live operational data.
Answer the question using ONLY the provided context — not the search query used internally.
Always cite your sources using [Source: table | SKU | date range] notation.
Give specific numbers where the data supports it.
If the context doesn't contain enough information, say so clearly."""


def _generate_hypothesis(question: str) -> str:
    """
    Step 1: Ask the LLM to write a hypothetical answer.
    This is NOT shown to the user — it's only used to improve retrieval.
    """
    messages = [
        {"role": "system", "content": HYPOTHESIS_PROMPT},
        {"role": "user",   "content": question},
    ]
    response = generate_raw(
        messages      = messages,
        strategy_name = "hyde_hypothesis",
        temperature   = 0.3,   # slightly more creative than final answer
        max_tokens    = 200,   # keep hypothesis concise
    )
    return response.answer


def _embed_and_retrieve_by_text(hypothesis_text: str, top_k: int):
    """
    Step 2+3: Embed the hypothesis text and retrieve similar chunks.
    Uses the same embedding model and ChromaDB collection as normal retrieval,
    but the search vector comes from the hypothesis — not the original question.
    """
    import chromadb
    model      = _load_model()
    hypothesis_embedding = model.encode(hypothesis_text).tolist()

    client     = chromadb.PersistentClient(path=config.CHROMA_PATH)
    collection = client.get_collection(name=config.CHROMA_COLLECTION_NAME)

    results = collection.query(
        query_embeddings = [hypothesis_embedding],
        n_results        = top_k,
        include          = ["documents", "metadatas", "distances"],
    )

    # Import here to avoid circular import
    from pipeline.retriever import RetrievedChunk
    chunks = []
    for doc, meta, dist, chunk_id in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
        results["ids"][0],
    ):
        chunks.append(RetrievedChunk(
            text     = doc,
            metadata = meta,
            score    = round(1 - dist, 4),
            chunk_id = chunk_id,
        ))
    return chunks


def run(question: str) -> StrategyResult:
    """
    HyDE pipeline:
    1. Generate hypothetical answer from question (LLM call 1)
    2. Embed hypothesis → retrieve real chunks from ChromaDB
    3. Generate final answer from real chunks (LLM call 2)

    Args:
        question: Plain English question from user

    Returns:
        StrategyResult — extra_info contains the hypothesis text
    """
    # ── Step 1: Generate hypothesis ───────────────────────────────────────────
    hypothesis = _generate_hypothesis(question)

    # ── Step 2+3: Embed hypothesis → retrieve real chunks ────────────────────
    chunks  = _embed_and_retrieve_by_text(hypothesis, top_k=config.TOP_K)
    context = format_chunks_for_prompt(chunks)

    # ── Step 4: Generate final answer from real chunks ────────────────────────
    response = generate(
        system_prompt = FINAL_SYSTEM_PROMPT,
        context       = context,
        question      = question,
        strategy_name = "hyde",
    )

    return StrategyResult(
        answer            = response.answer,
        chunks            = chunks,
        strategy          = "hyde",
        prompt_tokens     = response.prompt_tokens,
        completion_tokens = response.completion_tokens,
        total_tokens      = response.total_tokens,
        extra_info        = {
            "hypothesis": hypothesis,
            # The UI will show this so users can see what HyDE searched for
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Strategy 3 — HyDE Test")
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

        # Show the hypothesis — this is what makes HyDE transparent
        print(f"  HYPOTHESIS (used for retrieval, not shown as answer):")
        print(f"  {result.extra_info['hypothesis']}")
        print(f"\n  FINAL ANSWER (from real retrieved chunks):")
        print(f"  {result.answer}")
        print(f"\n  Sources retrieved via hypothesis embedding:")
        for chunk in result.chunks:
            print(f"    - {chunk.source_label()} (score: {chunk.score:.4f})")
        print(f"\n  Tokens: {result.total_tokens} total (2 LLM calls)")

    print("\n" + "=" * 60)
    print("  HyDE test complete")
    print("=" * 60)