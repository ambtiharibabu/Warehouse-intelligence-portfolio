# pipeline/retriever.py
# ─────────────────────────────────────────────────────────────────────────────
# Retriever: takes a plain English query → returns top-k relevant chunks
# Called by every prompting strategy in the prompting/ folder
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
from dataclasses import dataclass, field
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── Data structure for a retrieved chunk ─────────────────────────────────────
# Using @dataclass so every caller gets a consistent, typed object
# instead of unpacking raw dicts and lists

@dataclass
class RetrievedChunk:
    text:       str               # the raw chunk text
    metadata:   dict              # source, sku, date_range, kpi_type, etc.
    score:      float             # cosine similarity (higher = more relevant)
    chunk_id:   str = ""          # ChromaDB ID e.g. "chunk_0042"

    def source_label(self) -> str:
        """
        Returns a human-readable citation string for UI display.
        Example: "orders | SKU-0007 | 2026-01-01 to 2026-01-07"
        """
        parts = [self.metadata.get("source", "unknown")]
        if "sku" in self.metadata:
            parts.append(self.metadata["sku"])
        if "date_start" in self.metadata and "date_end" in self.metadata:
            parts.append(
                f"{self.metadata['date_start']} to {self.metadata['date_end']}"
            )
        elif "date" in self.metadata:
            parts.append(self.metadata["date"])
        return " | ".join(parts)


# ── Module-level singletons ───────────────────────────────────────────────────
# Loaded once when retriever.py is first imported — not on every query call
# This is the "singleton pattern": one shared instance reused everywhere

_embedding_model = None   # SentenceTransformer instance
_collection      = None   # ChromaDB collection instance


def _load_model():
    """Load embedding model once and cache it in module-level variable."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
    return _embedding_model


def _load_collection():
    """Connect to ChromaDB and return the warehouse_chunks collection."""
    global _collection
    if _collection is None:
        import chromadb
        client      = chromadb.PersistentClient(path=config.CHROMA_PATH)
        _collection = client.get_collection(
            name=config.CHROMA_COLLECTION_NAME
        )
    return _collection


# ── Core retrieval function ───────────────────────────────────────────────────

def retrieve(
    query:       str,
    top_k:       int           = config.TOP_K,
    source_filter: Optional[str] = None,
) -> List[RetrievedChunk]:
    """
    Embed the query and return the top-k most similar chunks from ChromaDB.

    Args:
        query:         Plain English question from the user
        top_k:         Number of chunks to return (default: 5 from config)
        source_filter: Optional — restrict results to one source table.
                       e.g. source_filter="forecasts" returns only forecast chunks.
                       Useful for HyDE and Step-Back strategies.

    Returns:
        List of RetrievedChunk objects, sorted by similarity (highest first)
    """
    model      = _load_model()
    collection = _load_collection()

    # Embed the query — same model, same 384-dim space as the stored chunks
    query_embedding = model.encode(query).tolist()

    # Build optional ChromaDB where-filter
    # ChromaDB filter syntax: {"source": {"$eq": "forecasts"}}
    where = {"source": {"$eq": source_filter}} if source_filter else None

    # Query ChromaDB — returns dicts with parallel lists
    results = collection.query(
        query_embeddings = [query_embedding],
        n_results        = top_k,
        where            = where,
        include          = ["documents", "metadatas", "distances"],
    )

    # ChromaDB returns distances (lower = more similar for cosine)
    # Convert distance → similarity score: similarity = 1 - distance
    chunks = []
    for doc, meta, dist, chunk_id in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
        results["ids"][0],
    ):
        chunks.append(RetrievedChunk(
            text      = doc,
            metadata  = meta,
            score     = round(1 - dist, 4),   # convert distance to similarity
            chunk_id  = chunk_id,
        ))

    return chunks


def retrieve_multi_query(
    queries: List[str],
    top_k:   int = config.TOP_K,
) -> List[RetrievedChunk]:
    """
    Retrieve chunks for multiple queries and deduplicate by chunk_id.
    Used by Step-Back strategy: retrieves for both the abstract
    and specific question, then merges results.

    Returns deduplicated list, ordered by best score per unique chunk.
    """
    seen_ids = {}

    for query in queries:
        chunks = retrieve(query, top_k=top_k)
        for chunk in chunks:
            # Keep the highest-scoring version if a chunk appears in both results
            if chunk.chunk_id not in seen_ids:
                seen_ids[chunk.chunk_id] = chunk
            elif chunk.score > seen_ids[chunk.chunk_id].score:
                seen_ids[chunk.chunk_id] = chunk

    # Sort by score descending, return top_k
    merged = sorted(seen_ids.values(), key=lambda c: c.score, reverse=True)
    return merged[:top_k]


def format_chunks_for_prompt(chunks: List[RetrievedChunk]) -> str:
    """
    Formats retrieved chunks into a single context string for LLM prompts.
    Each chunk is numbered and labeled with its source.

    Output example:
        [1] Source: reorder_params | SKU-0007
        Reorder parameters for SKU-0007: ...

        [2] Source: forecasts | SKU-0007 | 2026-03-26 to 2026-04-24
        30-day demand forecast for SKU-0007: ...
    """
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        parts.append(
            f"[{i}] Source: {chunk.source_label()}\n{chunk.text}"
        )
    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Test — run directly to verify retriever works across multiple query types
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  P3 — Retriever Test")
    print("=" * 60)

    # Test queries covering different chunk types
    test_queries = [
        ("Stockout risk",        "Which SKUs are at stockout risk this week?"),
        ("Labor productivity",   "Which shift has the lowest labor productivity?"),
        ("Lean waste",           "What is the biggest source of warehouse waste?"),
        ("Forecast",             "What is the demand forecast for SKU-0007?"),
        ("Carrier performance",  "Which carrier has the worst on-time rate?"),
    ]

    for label, query in test_queries:
        print(f"\n{'─' * 60}")
        print(f"  Query [{label}]: {query}")
        print(f"{'─' * 60}")

        chunks = retrieve(query, top_k=3)

        for i, chunk in enumerate(chunks, start=1):
            print(f"  [{i}] score={chunk.score:.4f} | {chunk.source_label()}")
            print(f"       {chunk.text[:120]}...")

    # Test format_chunks_for_prompt
    print(f"\n{'─' * 60}")
    print("  Formatted context block (as LLM will see it):")
    print(f"{'─' * 60}")
    sample_chunks = retrieve("Which SKUs need reordering?", top_k=2)
    print(format_chunks_for_prompt(sample_chunks))

    print("\n" + "=" * 60)
    print("  Retriever test complete")
    print("=" * 60)