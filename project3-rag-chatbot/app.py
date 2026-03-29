# app.py
# ─────────────────────────────────────────────────────────────────────────────
# Streamlit Chat UI — Warehouse Intelligence Chatbot
# ─────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

# ── Page config — MUST be first Streamlit call ────────────────────────────────
st.set_page_config(
    page_title="Warehouse Intelligence Chatbot",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Auto-ingest on cold start ─────────────────────────────────────────────────
# Streamlit Cloud wipes ephemeral storage on container recycle.
# This rebuilds ChromaDB automatically if the collection is missing.

def _ensure_chroma_ready():
    import chromadb
    try:
        client = chromadb.PersistentClient(path=config.CHROMA_PATH)
        client.get_collection(name=config.CHROMA_COLLECTION_NAME)
        # Collection exists — nothing to do
    except Exception:
        # Collection missing — rebuild from PostgreSQL
        with st.spinner(
            "⏳ Building knowledge base from PostgreSQL... "
            "This takes ~90 seconds on first load. Please wait."
        ):
            from pipeline.ingest import (
                get_engine, load_all_tables,
                build_all_chunks, embed_and_store
            )
            engine = get_engine()
            tables = load_all_tables(engine)
            chunks = build_all_chunks(tables)
            embed_and_store(chunks)
        st.success("✅ Knowledge base ready!")
        st.rerun()

_ensure_chroma_ready()

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Exo+2:wght@300;400;600;700&display=swap');

:root {
    --bg-deep:    #080e14;
    --bg-panel:   #0d1821;
    --bg-card:    #111f2e;
    --border:     #1e3a52;
    --amber:      #f59e0b;
    --amber-dim:  #92600a;
    --cyan:       #22d3ee;
    --green:      #10b981;
    --red:        #ef4444;
    --text-main:  #e2e8f0;
    --text-muted: #94a3b8;
    --text-dim:   #64748b;
}

.stApp {
    background-color: var(--bg-deep) !important;
    background-image:
        linear-gradient(rgba(245,158,11,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(245,158,11,0.03) 1px, transparent 1px),
        radial-gradient(ellipse 80% 60% at 50% 0%, rgba(34,211,238,0.07) 0%, transparent 60%),
        radial-gradient(ellipse 40% 40% at 90% 80%, rgba(245,158,11,0.05) 0%, transparent 50%);
    background-size: 40px 40px, 40px 40px, 100% 100%, 100% 100%;
    font-family: 'Exo 2', sans-serif !important;
    color: var(--text-main) !important;
}

p, span, div, label, h1, h2, h3, h4, h5, h6,
.stMarkdown, .stMarkdown p, .stMarkdown span,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span,
[data-testid="stMarkdownContainer"] li,
.element-container, .stText {
    color: var(--text-main) !important;
    font-family: 'Exo 2', sans-serif !important;
}

[data-testid="stSidebar"] {
    background-color: var(--bg-panel) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * { color: var(--text-main) !important; }

[data-testid="stSidebar"] .stButton button {
    background-color: var(--bg-card) !important;
    color: var(--text-main) !important;
    border: 1px solid var(--border) !important;
    font-size: 0.80em !important;
    text-align: left !important;
    border-radius: 6px !important;
    padding: 6px 10px !important;
    transition: all 0.2s ease;
}
[data-testid="stSidebar"] .stButton button:hover {
    border-color: var(--amber) !important;
    color: var(--amber) !important;
    background-color: rgba(245,158,11,0.08) !important;
}

[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
    background-color: #111f2e !important;
    color: #e2e8f0 !important;
    border: 1px solid #1e3a52 !important;
}
[data-testid="stSelectbox"] div[data-baseweb="select"] span {
    color: #e2e8f0 !important;
}
[data-testid="stSelectbox"] svg { fill: #e2e8f0 !important; }

[data-baseweb="popover"] {
    background-color: #0d1821 !important;
    border: 1px solid #1e3a52 !important;
    border-radius: 8px !important;
}
[data-baseweb="popover"] ul {
    background-color: #0d1821 !important;
    padding: 4px !important;
}
[data-baseweb="popover"] li {
    background-color: #0d1821 !important;
    color: #e2e8f0 !important;
    border-radius: 6px !important;
    margin: 2px 0 !important;
}
[data-baseweb="popover"] li:hover {
    background-color: rgba(245,158,11,0.12) !important;
    color: #f59e0b !important;
}
[data-baseweb="popover"] li[aria-selected="true"] {
    background-color: rgba(245,158,11,0.18) !important;
    color: #f59e0b !important;
}
[data-baseweb="popover"] span,
[data-baseweb="popover"] div,
[data-baseweb="popover"] p {
    color: #e2e8f0 !important;
    background-color: transparent !important;
}

[data-testid="stChatMessage"] {
    background-color: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    margin-bottom: 12px !important;
    overflow: visible !important;
}
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] span,
[data-testid="stChatMessage"] div,
[data-testid="stChatMessage"] li {
    color: var(--text-main) !important;
}

[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-user"],
[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-assistant"] {
    font-size: 1.4em !important;
    line-height: 1 !important;
    overflow: hidden !important;
}

[data-testid="stChatMessageContent"] {
    overflow: hidden !important;
    word-wrap: break-word !important;
    word-break: break-word !important;
}

[data-testid="stChatInput"] {
    background-color: var(--bg-panel) !important;
    border-top: 1px solid var(--border) !important;
}
[data-testid="stChatInput"] textarea {
    background-color: var(--bg-card) !important;
    color: var(--text-main) !important;
    border: 1px solid var(--border) !important;
    font-family: 'Exo 2', sans-serif !important;
}
[data-testid="stChatInput"] textarea::placeholder {
    color: var(--text-dim) !important;
}

[data-testid="stExpander"] {
    background-color: var(--bg-panel) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    overflow: hidden !important;
    margin-top: 8px !important;
}
[data-testid="stExpander"] summary {
    color: var(--text-muted) !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
    max-width: 100% !important;
    padding: 8px 12px !important;
}
[data-testid="stExpander"] summary:hover {
    color: var(--amber) !important;
}
[data-testid="stExpander"] summary span {
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
    color: var(--text-muted) !important;
}
[data-testid="stExpander"] p,
[data-testid="stExpander"] span,
[data-testid="stExpander"] div {
    color: var(--text-main) !important;
}
[data-testid="stExpander"] > div[data-testid="stExpanderDetails"] {
    padding: 12px 16px !important;
}

[data-testid="stAlert"] {
    background-color: rgba(34,211,238,0.08) !important;
    border: 1px solid rgba(34,211,238,0.25) !important;
    border-radius: 8px !important;
}
[data-testid="stAlert"] p,
[data-testid="stAlert"] span { color: var(--text-main) !important; }

[data-testid="stTabs"] [role="tab"] {
    color: var(--text-muted) !important;
    font-weight: 600;
    font-size: 0.95em;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: var(--amber) !important;
    border-bottom: 2px solid var(--amber) !important;
}

[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}
[data-testid="stDataFrame"] * {
    color: var(--text-main) !important;
    background-color: var(--bg-card) !important;
}

.stCaption,
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {
    color: var(--text-dim) !important;
}

hr { border-color: var(--border) !important; }
[data-testid="stSpinner"] p { color: var(--amber) !important; }

.metric-badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 20px;
    font-size: 0.76em;
    font-weight: 700;
    margin-right: 6px;
    margin-top: 6px;
    font-family: 'Share Tech Mono', monospace;
    letter-spacing: 0.03em;
}
.badge-green  { background: rgba(16,185,129,0.15);  color: #10b981 !important; border: 1px solid rgba(16,185,129,0.3); }
.badge-yellow { background: rgba(245,158,11,0.15);  color: #f59e0b !important; border: 1px solid rgba(245,158,11,0.3); }
.badge-red    { background: rgba(239,68,68,0.15);   color: #ef4444 !important; border: 1px solid rgba(239,68,68,0.3); }
.badge-grey   { background: rgba(100,116,139,0.15); color: #94a3b8 !important; border: 1px solid rgba(100,116,139,0.3); }

.main-header {
    background: linear-gradient(135deg, #0d1f35 0%, #0a1929 50%, #0d1f35 100%);
    border: 1px solid var(--border);
    border-top: 3px solid var(--amber);
    border-radius: 12px;
    padding: 22px 28px;
    margin-bottom: 20px;
    position: relative;
    overflow: hidden;
}
.main-header::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: repeating-linear-gradient(
        90deg, transparent, transparent 60px,
        rgba(245,158,11,0.03) 60px, rgba(245,158,11,0.03) 61px
    );
    pointer-events: none;
}
.main-header h2 {
    margin: 0;
    color: #f59e0b !important;
    font-family: 'Exo 2', sans-serif !important;
    font-weight: 700;
    font-size: 1.6em;
    letter-spacing: 0.02em;
}
.main-header p {
    margin: 6px 0 0 0;
    color: var(--text-muted) !important;
    font-size: 0.88em;
}
.robot-banner { display: flex; align-items: center; gap: 16px; }
.robot-icon {
    font-size: 3em;
    animation: pulse-glow 3s ease-in-out infinite;
}
@keyframes pulse-glow {
    0%, 100% { filter: drop-shadow(0 0 8px rgba(245,158,11,0.4)); }
    50%       { filter: drop-shadow(0 0 20px rgba(245,158,11,0.8)); }
}

.sidebar-header {
    text-align: center;
    padding: 12px 0 16px 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 16px;
}
.sidebar-header h3 {
    color: var(--amber) !important;
    font-family: 'Exo 2', sans-serif !important;
    font-weight: 700;
    font-size: 1.1em;
    margin: 6px 0 2px 0;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}
.sidebar-header p {
    color: var(--text-dim) !important;
    font-size: 0.78em;
    margin: 0;
}

.strategy-card {
    background: rgba(245,158,11,0.06);
    border: 1px solid rgba(245,158,11,0.2);
    border-left: 3px solid var(--amber);
    border-radius: 8px;
    padding: 10px 14px;
    margin: 8px 0;
}
.strategy-card p {
    color: #94a3b8 !important;
    font-size: 0.82em;
    margin: 0;
    line-height: 1.5;
}

.section-label {
    color: var(--amber) !important;
    font-size: 0.72em;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    font-family: 'Share Tech Mono', monospace;
    margin-bottom: 8px;
}

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--bg-deep); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--amber-dim); }
</style>
""", unsafe_allow_html=True)

# ── Strategy configuration ────────────────────────────────────────────────────
STRATEGIES = {
    "zero_shot": {
        "label":       "⚡ Zero-Shot",
        "description": "Retrieve → generate with no examples or structure. Fastest. Baseline for all comparisons.",
        "llm_calls":   1,
        "faith":       0.7271,
    },
    "few_shot": {
        "label":       "📋 Few-Shot",
        "description": "Injects 3 labeled warehouse Q&A examples before your question. Best faithfulness score (0.83).",
        "llm_calls":   1,
        "faith":       0.8318,
    },
    "hyde": {
        "label":       "🔮 HyDE",
        "description": "Generates a hypothetical answer first, then embeds THAT for retrieval. Better for specific SKU queries.",
        "llm_calls":   2,
        "faith":       0.7292,
    },
    "step_back": {
        "label":       "🔙 Step-Back",
        "description": "Abstracts your question to a general principle, retrieves for both levels. Best for 'why' questions.",
        "llm_calls":   2,
        "faith":       0.5692,
    },
    "subcontext": {
        "label":       "✂️ Sub-Context",
        "description": "Compresses retrieved chunks to only relevant sentences. Most token-efficient. Honest about gaps.",
        "llm_calls":   2,
        "faith":       0.4483,
    },
    "chain_of_thought": {
        "label":       "🧠 Chain-of-Thought",
        "description": "Forces 5-step reasoning: data → logic → result → recommendation → confidence.",
        "llm_calls":   1,
        "faith":       0.6966,
    },
    "self_rag": {
        "label":       "🔄 Self-RAG",
        "description": "Generates → self-critiques → re-retrieves if confidence < 4/5. Best context precision (0.625).",
        "llm_calls":   "2-3",
        "faith":       0.5802,
    },
}

# ── Cached resources ──────────────────────────────────────────────────────────
@st.cache_resource
def load_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(config.EMBEDDING_MODEL)

@st.cache_resource
def load_chroma_collection():
    import chromadb
    client = chromadb.PersistentClient(path=config.CHROMA_PATH)
    return client.get_collection(name=config.CHROMA_COLLECTION_NAME)

@st.cache_data
def load_benchmark_table():
    path = "reports/benchmark_table.csv"
    if os.path.exists(path):
        return pd.read_csv(path)
    return None

# ── Strategy runner ───────────────────────────────────────────────────────────
def run_strategy(strategy_key: str, question: str):
    if strategy_key == "zero_shot":
        from prompting.zero_shot import run
    elif strategy_key == "few_shot":
        from prompting.few_shot import run
    elif strategy_key == "hyde":
        from prompting.hyde import run
    elif strategy_key == "step_back":
        from prompting.step_back import run
    elif strategy_key == "subcontext":
        from prompting.subcontext import run
    elif strategy_key == "chain_of_thought":
        from prompting.chain_of_thought import run
    elif strategy_key == "self_rag":
        from prompting.self_rag import run
    else:
        raise ValueError(f"Unknown strategy: {strategy_key}")
    return run(question)

# ── Badge helper ──────────────────────────────────────────────────────────────
def metric_badge(label: str, value, thresholds: tuple = (0.7, 0.5)) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return f'<span class="metric-badge badge-grey">{label}: n/a</span>'
    high, mid = thresholds
    cls = "badge-green" if value >= high else "badge-yellow" if value >= mid else "badge-red"
    return f'<span class="metric-badge {cls}">{label}: {value:.3f}</span>'

# ── Session state ─────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "strategy" not in st.session_state:
    st.session_state.strategy = "zero_shot"
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="sidebar-header">
        <div style="font-size:2.4em;">🤖</div>
        <h3>Warehouse AI</h3>
        <p>Supply Chain Intelligence Platform</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-label">▸ Prompting Strategy</div>',
                unsafe_allow_html=True)

    strategy_labels = {k: v["label"] for k, v in STRATEGIES.items()}
    selected_label  = st.selectbox(
        label="Strategy",
        options=list(strategy_labels.values()),
        index=list(strategy_labels.keys()).index(st.session_state.strategy),
        label_visibility="collapsed",
    )
    selected_key = [k for k, v in STRATEGIES.items()
                    if v["label"] == selected_label][0]
    st.session_state.strategy = selected_key

    meta        = STRATEGIES[selected_key]
    faith_val   = meta["faith"]
    faith_color = "#10b981" if faith_val >= 0.7 else "#f59e0b" if faith_val >= 0.5 else "#ef4444"

    st.markdown(f"""
    <div class="strategy-card">
        <p>{meta['description']}</p>
        <p style="margin-top:8px;">
            <span style="color:{faith_color}; font-weight:700;">
                Faithfulness: {faith_val:.4f}
            </span>
            &nbsp;·&nbsp;
            <span style="color:#94a3b8;">{meta['llm_calls']} LLM call(s)</span>
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.divider()
    st.markdown('<div class="section-label">▸ Sample Questions</div>',
                unsafe_allow_html=True)

    sample_questions = [
        "Which SKUs are at stockout risk?",
        "What is the total annual waste?",
        "Which carrier has the worst on-time rate?",
        "Forecast for SKU-0007?",
        "Which shift has lowest productivity?",
        "How many OSHA incidents occurred?",
    ]
    for q in sample_questions:
        if st.button(q, use_container_width=True, key=f"sq_{q[:15]}"):
            st.session_state.pending_question = q
            st.rerun()

    st.divider()
    st.markdown('<div class="section-label">▸ Pipeline Stats</div>',
                unsafe_allow_html=True)
    st.markdown("""
    <div style="font-size:0.8em; color:#64748b; line-height:2.2;">
        📦 &nbsp;1,780 embedded chunks<br>
        🗄️ &nbsp;8 PostgreSQL tables<br>
        🧮 &nbsp;22,406 total rows<br>
        🤖 &nbsp;Llama 3 8B via OpenRouter<br>
        🔍 &nbsp;all-MiniLM-L6-v2 embeddings
    </div>
    """, unsafe_allow_html=True)

    st.divider()
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.pending_question = None
        st.rerun()

# ── Main panel ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <div class="robot-banner">
        <div class="robot-icon">🏭</div>
        <div>
            <h2>Warehouse Intelligence Chatbot</h2>
            <p>
                RAG pipeline &nbsp;·&nbsp; 7 prompting strategies &nbsp;·&nbsp;
                Live PostgreSQL data &nbsp;·&nbsp; 1,780 embedded chunks &nbsp;·&nbsp;
                Llama 3 via OpenRouter
            </p>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

chat_tab, benchmark_tab = st.tabs(["💬  Chat", "📊  Benchmark Table"])

# ── Chat tab ──────────────────────────────────────────────────────────────────
with chat_tab:

    for msg in st.session_state.messages:
        if msg["role"] == "user":
            with st.chat_message("user", avatar="👤"):
                st.markdown(msg["content"])
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(msg["content"])

                if "chunks" in msg:
                    ragas  = msg.get("ragas", {})
                    badges = ""
                    badges += metric_badge("Completeness", ragas.get("completeness"), (0.75, 0.5))
                    badges += metric_badge("Fairness",     ragas.get("fairness"),     (0.8,  0.6))
                    badges += '<span class="metric-badge badge-grey">Faithfulness: see Benchmark tab</span>'
                    st.markdown(badges, unsafe_allow_html=True)

                    strategy_used = msg.get("strategy", "zero_shot")
                    with st.expander(
                        f"📄 {len(msg['chunks'])} source chunks  ·  "
                        f"{STRATEGIES[strategy_used]['label']}"
                    ):
                        for i, chunk in enumerate(msg["chunks"], 1):
                            st.markdown(
                                f"**[{i}]** &nbsp;"
                                f"`{chunk['source_label']}` &nbsp;"
                                f"*similarity: {chunk['score']:.4f}*"
                            )
                            text = chunk["text"]
                            st.caption(text[:320] + "..." if len(text) > 320 else text)
                            if i < len(msg["chunks"]):
                                st.divider()

                    st.caption(
                        f"⚡ {msg.get('total_tokens', 0):,} tokens  ·  "
                        f"{STRATEGIES[strategy_used]['label']}"
                    )

    if st.session_state.pending_question:
        question = st.session_state.pending_question
        st.session_state.pending_question = None

        st.session_state.messages.append({"role": "user", "content": question})

        strategy_key = st.session_state.strategy
        with st.spinner(f"Thinking with {STRATEGIES[strategy_key]['label']}..."):
            try:
                result = run_strategy(strategy_key, question)

                from evaluation.custom_eval import score_completeness, score_fairness
                completeness = score_completeness(question, result.answer)
                fairness     = score_fairness(result.chunks)

                chunks_serialized = [
                    {
                        "text":         c.text,
                        "metadata":     c.metadata,
                        "score":        c.score,
                        "source_label": c.source_label(),
                    }
                    for c in result.chunks
                ]

                st.session_state.messages.append({
                    "role":         "assistant",
                    "content":      result.answer,
                    "chunks":       chunks_serialized,
                    "strategy":     strategy_key,
                    "total_tokens": result.total_tokens,
                    "ragas": {
                        "completeness":      completeness,
                        "fairness":          fairness,
                        "faithfulness":      None,
                        "context_precision": None,
                        "context_recall":    None,
                    },
                })

            except Exception as e:
                st.session_state.messages.append({
                    "role":    "assistant",
                    "content": f"Error: {str(e)}",
                })

        st.rerun()

    user_input = st.chat_input("Ask your warehouse data anything...")
    if user_input:
        st.session_state.pending_question = user_input
        st.rerun()

# ── Benchmark tab ─────────────────────────────────────────────────────────────
with benchmark_tab:
    st.markdown("### 📊 7-Strategy Benchmark — RAGAS Evaluation")
    st.markdown(
        "10 warehouse test questions evaluated across all 7 strategies. "
        "Judge model: **Llama 3 8B** via OpenRouter."
    )

    bench_df = load_benchmark_table()

    if bench_df is not None:
        display_cols = [c for c in [
            "Label", "faithfulness", "context_precision",
            "context_recall", "LLM Calls", "Best For"
        ] if c in bench_df.columns]

        st.dataframe(
            bench_df[display_cols].rename(columns={
                "Label":             "Strategy",
                "faithfulness":      "Faithfulness ↑",
                "context_precision": "Ctx Precision ↑",
                "context_recall":    "Ctx Recall ↑",
                "LLM Calls":         "Calls",
                "Best For":          "Best For",
            }),
            use_container_width=True,
            hide_index=True,
        )

        st.info(
            "**Note — Answer Relevancy:** OpenRouter does not expose an embeddings "
            "endpoint compatible with RAGAS answer_relevancy scoring. "
            "All other metrics are fully computed using Llama 3 8B as judge model."
        )

        if "faithfulness" in bench_df.columns and "Label" in bench_df.columns:
            st.markdown("#### Faithfulness by Strategy")
            chart_df = bench_df[["Label", "faithfulness"]].set_index("Label")
            st.bar_chart(chart_df, color="#f59e0b")

        if "context_precision" in bench_df.columns:
            st.markdown("#### Context Precision by Strategy")
            chart_df2 = bench_df[["Label", "context_precision"]].set_index("Label")
            st.bar_chart(chart_df2, color="#22d3ee")
    else:
        st.warning(
            "Benchmark table not found. "
            "Run: `python evaluation/comparison_report.py`"
        )