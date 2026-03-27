# pipeline/generator.py
# ─────────────────────────────────────────────────────────────────────────────
# Generator: sends prompt + context + question to OpenRouter → returns answer
# Called by every prompting strategy in prompting/
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
from typing import Optional
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── Response data structure ───────────────────────────────────────────────────
# Everything the caller needs: the answer text, token usage, and model info
# Prompting strategies return this object to the Streamlit UI

@dataclass
class GeneratorResponse:
    answer:           str    # the LLM's generated answer
    model:            str    # model name used
    prompt_tokens:    int    # tokens used by the prompt
    completion_tokens: int   # tokens used by the answer
    total_tokens:     int    # sum — used for cost tracking
    strategy:         str    # which prompting strategy produced this


# ── OpenRouter client — loaded once ──────────────────────────────────────────
# Same singleton pattern as retriever.py — don't recreate the client per call

_client = None

def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(
            api_key  = config.OPENROUTER_API_KEY,
            base_url = config.OPENROUTER_BASE_URL,
        )
    return _client


# ── Core generation function ──────────────────────────────────────────────────

def generate(
    system_prompt:  str,
    context:        str,
    question:       str,
    strategy_name:  str  = "zero_shot",
    temperature:    float = 0.1,
    max_tokens:     int   = 1000,
) -> GeneratorResponse:
    """
    Calls OpenRouter (Llama 3) with the given system prompt, context, question.

    Args:
        system_prompt: The instruction block — defines how the LLM should behave.
                       Each of the 7 strategies provides its own system prompt.
        context:       The retrieved chunks formatted as a numbered list.
                       Produced by retriever.format_chunks_for_prompt().
        question:      The user's original plain-English question.
        strategy_name: Label for tracking which strategy produced this answer.
        temperature:   0.1 = near-deterministic (good for factual data queries)
        max_tokens:    Max length of the generated answer.

    Returns:
        GeneratorResponse with answer text + token usage stats.
    """
    client = _get_client()

    # ── Build the user message ────────────────────────────────────────────────
    # We combine context + question into one user turn.
    # The LLM sees: system instructions → context block → question
    user_message = f"""CONTEXT (retrieved warehouse data):
{context}

QUESTION:
{question}

Answer based strictly on the context above. Cite which source(s) 
support your answer using [Source: ...] notation."""

    # ── Make the API call ─────────────────────────────────────────────────────
    try:
        response = client.chat.completions.create(
            model       = config.MODEL_NAME,
            messages    = [
                {"role": "system",  "content": system_prompt},
                {"role": "user",    "content": user_message},
            ],
            temperature = temperature,
            max_tokens  = max_tokens,
        )

        answer = response.choices[0].message.content.strip()

        return GeneratorResponse(
            answer            = answer,
            model             = response.model,
            prompt_tokens     = response.usage.prompt_tokens,
            completion_tokens = response.usage.completion_tokens,
            total_tokens      = response.usage.total_tokens,
            strategy          = strategy_name,
        )

    except Exception as e:
        # Return a structured error so the UI can display it cleanly
        # rather than crashing the whole Streamlit app
        return GeneratorResponse(
            answer            = f"[Generator error] {str(e)}",
            model             = config.MODEL_NAME,
            prompt_tokens     = 0,
            completion_tokens = 0,
            total_tokens      = 0,
            strategy          = strategy_name,
        )


def generate_raw(
    messages:    list,
    strategy_name: str   = "custom",
    temperature: float   = 0.1,
    max_tokens:  int     = 1000,
) -> GeneratorResponse:
    """
    Lower-level call — accepts a raw messages list directly.
    Used by HyDE (which needs two separate LLM calls with different structures)
    and Self-RAG (which builds its own message sequence for self-critique).

    Args:
        messages: List of {"role": "...", "content": "..."} dicts
    """
    client = _get_client()

    try:
        response = client.chat.completions.create(
            model       = config.MODEL_NAME,
            messages    = messages,
            temperature = temperature,
            max_tokens  = max_tokens,
        )

        return GeneratorResponse(
            answer            = response.choices[0].message.content.strip(),
            model             = response.model,
            prompt_tokens     = response.usage.prompt_tokens,
            completion_tokens = response.usage.completion_tokens,
            total_tokens      = response.usage.total_tokens,
            strategy          = strategy_name,
        )

    except Exception as e:
        return GeneratorResponse(
            answer            = f"[Generator error] {str(e)}",
            model             = config.MODEL_NAME,
            prompt_tokens     = 0,
            completion_tokens = 0,
            total_tokens      = 0,
            strategy          = strategy_name,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test — run directly to verify OpenRouter connection + Llama 3 response
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from pipeline.retriever import retrieve, format_chunks_for_prompt

    print("=" * 60)
    print("  P3 — Generator Test (OpenRouter + Llama 3)")
    print("=" * 60)

    # ── Step 1: Retrieve relevant chunks ─────────────────────────────────────
    question = "Which SKUs are at stockout risk and what are their days of supply?"
    print(f"\n  Question: {question}")
    print(f"\n[1/3] Retrieving top-{config.TOP_K} chunks...")

    chunks  = retrieve(question)
    context = format_chunks_for_prompt(chunks)

    print(f"  ✓ {len(chunks)} chunks retrieved")
    for c in chunks:
        print(f"    - {c.source_label()} (score: {c.score:.4f})")

    # ── Step 2: Define a simple system prompt (zero-shot baseline) ────────────
    system_prompt = """You are a warehouse operations analyst.
Answer the question using ONLY the provided context.
Always cite which data source supports your answer using [Source: ...] notation.
If the context doesn't contain enough information, say so clearly.
Be concise and specific — give numbers where the data supports it."""

    # ── Step 3: Generate answer ───────────────────────────────────────────────
    print(f"\n[2/3] Calling OpenRouter ({config.MODEL_NAME})...")
    response = generate(
        system_prompt = system_prompt,
        context       = context,
        question      = question,
        strategy_name = "zero_shot_test",
    )

    # ── Step 4: Display result ────────────────────────────────────────────────
    print(f"\n[3/3] Response received:")
    print(f"\n{'─' * 60}")
    print(f"  ANSWER:\n")
    print(f"  {response.answer}")
    print(f"\n{'─' * 60}")
    print(f"  Model:  {response.model}")
    print(f"  Tokens: {response.prompt_tokens} prompt + "
          f"{response.completion_tokens} completion = "
          f"{response.total_tokens} total")
    print(f"  Strategy: {response.strategy}")

    print("\n" + "=" * 60)
    print("  Generator test complete — pipeline end-to-end working")
    print("=" * 60)