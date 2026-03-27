markdown
# 🏭 Project 3 — AI Warehouse Intelligence Chatbot

> *"A warehouse supervisor shouldn't need SQL to ask: 'Which SKUs will stock out 
> this week?' or 'Why did fulfillment drop on Tuesday night shift?'"*

A production-grade RAG (Retrieval-Augmented Generation) pipeline that ingests 
live warehouse operational data from PostgreSQL, implements and benchmarks 
**7 prompting strategies**, and delivers plain-English answers with full 
auditability of every source used — evaluated with RAGAS metrics.

**🔴 Live App:** [Streamlit App]https://hari-warehouse-p3-ai.streamlit.app/  
**📁 Portfolio:** [Link]https://github.com/ambtiharibabu/Warehouse-intelligence-portfolio

---

## What Was Built

A complete RAG pipeline reading from the same PostgreSQL database populated 
by Projects 1 and 2 — 22,406 rows across 8 tables converted into 1,780 
semantically searchable chunks. Seven distinct prompting strategies are 
implemented and benchmarked against each other using RAGAS evaluation metrics, 
giving both plain-English answers and full quantitative auditability of how 
each answer was derived.

---

## Live Numbers

| Metric | Value |
|---|---|
| PostgreSQL tables ingested | 8 |
| Total rows across all tables | 22,406 |
| Text chunks embedded | 1,780 |
| Embedding model | all-MiniLM-L6-v2 (local, free) |
| Vector dimensions | 384 |
| LLM | Llama 3 8B via OpenRouter |
| Prompting strategies implemented | 7 |
| RAGAS test questions | 10 |
| Evaluation metrics | 4 (Faithfulness, Ctx Precision, Ctx Recall, Completeness) |

---

## ArchitecturePostgreSQL (DigitalOcean)     ← P1 + P2 tables: 22,406 rows
↓
pipeline/ingest.py
→ reads all 8 tables
→ converts to 4 chunk types with metadata
→ embeds with all-MiniLM-L6-v2 (local)
→ stores in ChromaDB (local persistent, 1,780 chunks)
↓
pipeline/retriever.py
→ embeds user query
→ cosine similarity search
→ returns top-5 most relevant chunks
↓
prompting/ layer
→ applies selected strategy to query + chunks
↓
OpenRouter API (Llama 3 8B)
→ generates cited answer
↓
evaluation/
→ RAGAS: Faithfulness, Context Precision, Context Recall
→ Custom: Completeness, Fairness
↓
Streamlit Chat UI (app.py)
→ strategy selector sidebar
→ answer + source chunks + metric badges
→ benchmark comparison table

---

## The 7 Prompting Strategies

| Strategy | LLM Calls | Core Idea | Best For |
|---|---|---|---|
| **Zero-Shot** | 1 | Retrieve → generate, no extras | Baseline, simple queries |
| **Few-Shot** | 1 | Inject 3 labeled Q&A examples first | Consistent format, best faithfulness |
| **HyDE** | 2 | Generate hypothetical answer, embed *that* for retrieval | Specific entity queries |
| **Step-Back** | 2 | Abstract to general principle, retrieve for both levels | "Why" and root-cause questions |
| **Sub-Context** | 2 | Compress chunks to relevant sentences only | Token efficiency, honest gaps |
| **Chain-of-Thought** | 1 | 5-step: data → logic → result → recommendation → confidence | Complex comparisons |
| **Self-RAG** | 2–3 | Generate → self-critique → re-retrieve if confidence < 4/5 | Highest precision |

---

## RAGAS Benchmark Table

Same 10 warehouse questions evaluated across all 7 strategies.  
Judge model: **Llama 3 8B** · Scale: 0.0 → 1.0 (higher is better)

| Strategy | Faithfulness ↑ | Ctx Precision ↑ | Ctx Recall ↑ |
|---|---|---|---|
| **Few-Shot** | **0.8318** | 0.5250 | 0.8333 |
| HyDE | 0.7292 | 0.5000 | 0.7667 |
| Zero-Shot | 0.7271 | 0.5250 | 0.8333 |
| Chain-of-Thought | 0.6966 | 0.5450 | 0.8333 |
| Self-RAG | 0.5802 | **0.6250** | 0.8333 |
| Step-Back | 0.5692 | 0.5583 | 0.8333 |
| Sub-Context | 0.4483 | 0.5250 | 0.8333 |

**Key findings:**
- **Few-Shot wins faithfulness** — labeled examples anchor the LLM to context better than any multi-step strategy
- **Self-RAG wins context precision** — self-critique step filters noise before committing to an answer
- **HyDE has lowest context recall** — hypothesis-based retrieval fails when the hypothesis is confidently wrong
- **Sub-Context has lowest faithfulness** — aggressive compression loses grounding
- The "total annual waste" question failed across 5 of 7 strategies — a documented retrieval vocabulary mismatch, not a code bug

> **Note on Answer Relevancy:** OpenRouter does not expose an embeddings endpoint 
> compatible with RAGAS answer_relevancy scoring. All other metrics are fully 
> computed using Llama 3 8B as the judge model.

---

## Chunking Strategy

Four chunk types designed for different retrieval patterns:

| Type | Source | Grouping | Best For |
|---|---|---|---|
| KPI chunks | orders, inventory, labor, shipments, safety | SKU + 7-day window | Weekly performance queries |
| Forecast chunks | forecasts | SKU + 30-day window | "What's the forecast for X?" |
| Lean waste chunks | lean_waste_flags | One per flag | "What waste exists?" |
| Daily summary chunks | orders + labor + shipments | One per calendar day | Broad "how was Tuesday?" queries |

---

## File Structureproject3-rag-chatbot/
├── pipeline/
│   ├── ingest.py          ← PostgreSQL → chunks → ChromaDB
│   ├── retriever.py       ← query → top-k chunks + format_chunks_for_prompt()
│   └── generator.py       ← chunks + prompt → OpenRouter → answer
├── prompting/
│   ├── result_types.py    ← StrategyResult dataclass (shared interface)
│   ├── zero_shot.py       ← Strategy 1
│   ├── few_shot.py        ← Strategy 2
│   ├── hyde.py            ← Strategy 3
│   ├── step_back.py       ← Strategy 4
│   ├── subcontext.py      ← Strategy 5
│   ├── chain_of_thought.py← Strategy 6
│   └── self_rag.py        ← Strategy 7
├── evaluation/
│   ├── ragas_eval.py      ← RAGAS metrics runner (--strategy zero_shot|all)
│   ├── custom_eval.py     ← Completeness + Fairness scorers
│   └── comparison_report.py ← benchmark table builder
├── app.py                 ← Streamlit chat UI
├── config.py              ← Centralised settings (API keys, model, ChromaDB path)
└── requirements.txt

---

## PostgreSQL Tables Read by P3

| Table | Rows | Source | Used For |
|---|---|---|---|
| orders | 18,214 | P1 + P2 | Fulfillment rate chunks |
| inventory | 240 | P1 | Inventory accuracy chunks |
| labor | 1,943 | P1 | Labor productivity chunks |
| shipments | 1,350 | P1 | Carrier performance chunks |
| safety_incidents | 4 | P1 | OSHA safety chunk |
| forecasts | 600 | P2 | 30-day demand forecast chunks |
| reorder_params | 20 | P2 | EOQ/ROP/stockout risk chunks |
| lean_waste_flags | 35 | P2 | Lean waste flag chunks |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Vector database | ChromaDB (local persistent) |
| Embedding model | HuggingFace all-MiniLM-L6-v2 (384-dim, local, free) |
| LLM | Llama 3 8B Instruct via OpenRouter |
| RAG evaluation | RAGAS 0.4.3 |
| Database | PostgreSQL on DigitalOcean |
| ORM | SQLAlchemy + psycopg2-binary |
| UI | Streamlit |
| Language | Python 3.11 |

---

## How to Run Locally
```powershell1. Clone
git clone https://github.com/ambtiharibabu/Warehouse-intelligence-portfolio.git
cd Warehouse-intelligence-portfolio/project3-rag-chatbot2. Virtual environment
python -m venv venv
.\venv\Scripts\activate      # Windows PowerShell3. Install dependencies
pip install -r requirements.txt4. Create .env with credentials
DB_HOST=your_host
DB_PORT=5432
DB_NAME=your_db
DB_USER=your_user
DB_PASSWORD=your_password
DB_SSLMODE=disable
OPENROUTER_API_KEY=sk-or-...5. Build ChromaDB (one-time, ~90 seconds)
python pipeline/ingest.py6. Launch app
streamlit run app.py7. Run RAGAS evaluation (optional, ~20 min for all strategies)
python evaluation/ragas_eval.py --strategy zero_shot
python evaluation/ragas_eval.py --strategy all

---

## Honest Notes on Limitations

**Retrieval vocabulary mismatch:** The "total annual waste" question fails across most strategies because the query language ("annual waste", "total cost") doesn't semantically match the chunk language ("annual_waste_usd", "excess inventory"). This is a documented chunking design limitation, not a pipeline bug — and is clearly visible in the benchmark scores.

**Answer Relevancy metric:** OpenRouter does not expose an embeddings API endpoint, so RAGAS `answer_relevancy` returns `nan` across all strategies. All other metrics are fully computed. This is noted transparently rather than hidden.

**Self-RAG re-retrieval:** The self-critique step correctly identifies low-confidence answers but cannot always find better chunks on re-retrieval if the root cause is vocabulary mismatch rather than a bad query formulation.

---

## Related Projects

- **[Project 1 — Warehouse KPI Dashboard](https://hari-warehouse-kpi-p1.streamlit.app/)** — 6 KPIs, 16 Plotly charts, Power BI executive layer
- **[Project 2 — Forecasting & Lean Waste Engine](https://hari-warehouse-p2.streamlit.app/)** — Prophet forecasting, EOQ/ROP optimisation, SAP export

---

## Author

**Haribabu Ambati**  
MSBA Student |Supply Chain & Operations expert and enthusiast | Supply Chain  · Python · ML · Data Engineering . 
[LinkedIn](https://www.linkedin.com/in/haribabuambati) · [GitHub](https://github.com/ambtiharibabu)
