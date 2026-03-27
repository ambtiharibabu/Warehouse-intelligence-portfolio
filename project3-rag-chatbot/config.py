# config.py
# ─────────────────────────────────────────────────────────────────────────────
# Central configuration for the entire P3 RAG pipeline.
# Every other module imports from here — nothing is hardcoded elsewhere.
# ─────────────────────────────────────────────────────────────────────────────

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env file into environment variables ─────────────────────────────────
# This makes DB_HOST, OPENROUTER_API_KEY, etc. available via os.getenv()
# load_dotenv() silently does nothing if .env doesn't exist (safe for cloud)
# Load .env for local development
load_dotenv()

# Override with Streamlit Cloud secrets if available
try:
    import streamlit as st
    if hasattr(st, "secrets"):
        if "database" in st.secrets:
            db = st.secrets["database"]
            os.environ["DB_HOST"]     = db["DB_HOST"]
            os.environ["DB_PORT"]     = str(db["DB_PORT"])
            os.environ["DB_NAME"]     = db["DB_NAME"]
            os.environ["DB_USER"]     = db["DB_USER"]
            os.environ["DB_PASSWORD"] = db["DB_PASSWORD"]
            os.environ["DB_SSLMODE"]  = db["DB_SSLMODE"]
        if "openrouter" in st.secrets:
            os.environ["OPENROUTER_API_KEY"] = st.secrets["openrouter"]["OPENROUTER_API_KEY"]
except Exception:
    pass

# ── Project root — the folder this file lives in ─────────────────────────────
# Path(__file__) is the path to config.py itself
# .parent gives us the folder it's in (project3-rag-chatbot/)
BASE_DIR = Path(__file__).parent

# ── PostgreSQL connection ─────────────────────────────────────────────────────
# Same pattern we inherited from P1 and P2
# All values read from .env — nothing hardcoded here
DB_CONFIG = {
    "drivername": "postgresql+psycopg2",
    "username":   os.getenv("DB_USER"),
    "password":   os.getenv("DB_PASSWORD"),
    "host":       os.getenv("DB_HOST"),
    "port":       int(os.getenv("DB_PORT", 5432)),
    "database":   os.getenv("DB_NAME"),
}
DB_SSLMODE = os.getenv("DB_SSLMODE", "disable")

# ── OpenRouter (LLM API) ──────────────────────────────────────────────────────
# OpenRouter lets us use Llama 3 via the same interface as OpenAI
# We just point the openai package at a different base_url
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL_NAME = "meta-llama/llama-3-8b-instruct"

# ── Embedding model ───────────────────────────────────────────────────────────
# Runs locally on your machine — no API key, no cost, no internet needed
# all-MiniLM-L6-v2: fast, small, strong for semantic similarity tasks
# First run will download ~90MB model weights and cache them locally
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ── ChromaDB ──────────────────────────────────────────────────────────────────
# Local persistent storage — ChromaDB writes index files to this folder
# Path is relative to project root: project3-rag-chatbot/chroma_db/
CHROMA_PATH = str(BASE_DIR / "chroma_db")
CHROMA_COLLECTION_NAME = "warehouse_chunks"

# ── Chunking settings ─────────────────────────────────────────────────────────
# chunk_size: max tokens per chunk (controls how much text each chunk holds)
# chunk_overlap: tokens shared between adjacent chunks
#   → overlap prevents important context from being cut off at a chunk boundary
#   → think of it like pages in a book that repeat the last paragraph
CHUNK_SIZE    = 512
CHUNK_OVERLAP = 50

# ── Retrieval settings ────────────────────────────────────────────────────────
# TOP_K: number of chunks returned per query
# 5 is the standard starting point — enough context, not too much noise
TOP_K = 5

# ── Tables to ingest from PostgreSQL ─────────────────────────────────────────
# Explicit list — ingest.py will loop through exactly these tables
# If P1/P2 add new tables later, just add them here
TABLES_TO_INGEST = [
    "orders",
    "inventory",
    "labor",
    "shipments",
    "safety_incidents",
    "forecasts",
    "reorder_params",
    "lean_waste_flags",
]

# ── RAGAS test questions ──────────────────────────────────────────────────────
# Ground-truth evaluation set — 10 questions used to benchmark all 7 strategies
# We define them here so every eval script uses exactly the same set
TEST_QUESTIONS = [
    "Which SKUs are at Critical stockout risk this week?",
    "What is the current order fulfillment rate?",
    "Which shift has the lowest labor productivity?",
    "What is the total estimated annual waste from excess inventory?",
    "How many OSHA incidents occurred in the last 30 days?",
    "What are the top 3 SKUs with worst inventory accuracy?",
    "What does the 30-day demand forecast show for SKU-007?",
    "Which carrier has the worst on-time shipping rate?",
    "What lean waste flags exist for the electronics category?",
    "Compare night shift fulfillment rate vs day shift.",
]