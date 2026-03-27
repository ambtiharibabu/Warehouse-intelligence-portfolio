markdown# 🏭 Warehouse Intelligence Portfolio

**Haribabu Ambati**  
MSBA Student |Supply Chain & Operations expert and enthusiast | Supply Chain  · Python · ML · Data Engineering . 
[LinkedIn](https://www.linkedin.com/in/haribabuambati) · [GitHub](https://github.com/ambtiharibabu)

![Python](https://img.shields.io/badge/Python-3.11-blue)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-DigitalOcean-336791)
![Streamlit](https://img.shields.io/badge/Streamlit-3_Live_Apps-FF4B4B)
![PowerBI](https://img.shields.io/badge/Power_BI-Executive_Layer-F2C811)
![ChromaDB](https://img.shields.io/badge/ChromaDB-RAG_Pipeline-green)
![OpenRouter](https://img.shields.io/badge/LLM-Llama_3_8B-orange)

---

A three-project portfolio demonstrating end-to-end data engineering,
machine learning, and AI applied to real warehouse operations problems —
built on a **single live PostgreSQL database** that every project reads from and writes to.

---

## Projects

### 📊 Project 1 — Warehouse KPI Dashboard
**Folder:** `project1-kpi-dashboard/`  
🌐 **[Live App](https://hari-warehouse-kpi-p1.streamlit.app)** · 📄 **[README](project1-kpi-dashboard/README.md)**

A full-stack warehouse operations dashboard with two audience layers —
a Power BI executive report and a Streamlit operational dashboard —
both powered by the same live PostgreSQL database.

**What it does:**
- Tracks 6 operational KPIs: Order Fulfillment, Inventory Accuracy,
  Labor Productivity, OSHA Incident Rate, Shipping On-Time %, Cycle Time
- Colour-coded alert thresholds (🔴 Red / 🟡 Yellow / 🟢 Green)
- 18 Plotly charts across 5 operational areas
- 4-sheet Excel export for offline reporting
- Power BI executive layer (CSV-based, SSL workaround documented)

**Tech:** `Python` `PostgreSQL` `Streamlit` `Plotly` `Power BI` `pandas` `openpyxl`

---

### 🏭 Project 2 — Inventory Forecasting & Lean Waste Detection Engine
**Folder:** `project2-forecasting/`  
🌐 **[Live App](https://hari-warehouse-p2.streamlit.app)** · 📄 **[README](project2-forecasting/README.md)**

A 6-module Python pipeline that reads live warehouse data,
runs ML-powered demand forecasting, optimises reorder parameters
using EOQ modelling, and surfaces $1M+ in annual Lean waste —
outputting results to PostgreSQL, Excel, and SAP-compatible ERP flat files.

**What it does:**
- Facebook Prophet demand forecasting (20 SKUs, 30-day horizon)
- EOQ + Safety Stock + Reorder Point optimisation ($441K savings identified)
- Lean waste detection: excess inventory, over-ordering, demand planning failure ($1.04M flagged)
- SAP MM MRP II flat file export (MM17 transaction ready)
- 5-sheet Excel MRP report for warehouse directors
- Streamlit dashboard with 6 pages, global filters, and download buttons

**Tech:** `Python` `PostgreSQL` `Prophet` `Streamlit` `Plotly` `SAP MM` `pandas` `openpyxl`

---

### 🤖 Project 3 — AI Warehouse Intelligence Chatbot (RAG Pipeline)
**Folder:** `project3-rag-chatbot/`  
🌐 **[Live App](https://hari-warehouse-p3-ai.streamlit.app)** · 📄 **[README](project3-rag-chatbot/README.md)**

A production-grade RAG (Retrieval-Augmented Generation) pipeline that ingests
22,406 rows of live warehouse data from PostgreSQL, converts them into 1,780
semantically searchable chunks, and lets operations teams ask questions in
plain English — with 7 prompting strategies benchmarked using RAGAS metrics.

**What it does:**
- Ingests 8 PostgreSQL tables → 4 chunk types → 1,780 embeddings in ChromaDB
- Implements and benchmarks 7 RAG prompting strategies:
  Zero-Shot · Few-Shot · HyDE · Step-Back · Sub-Context · Chain-of-Thought · Self-RAG
- Evaluates every strategy with RAGAS: Faithfulness, Context Precision, Context Recall
- Streamlit chat UI with strategy selector, source chunk viewer, and metric badges
- Full benchmark comparison table built from real evaluation runs

**RAGAS Results (10 test questions, Llama 3 8B judge):**

| Strategy | Faithfulness ↑ | Ctx Precision ↑ | Ctx Recall ↑ |
|---|---|---|---|
| **Few-Shot** | **0.8318** | 0.5250 | 0.8333 |
| HyDE | 0.7292 | 0.5000 | 0.7667 |
| Zero-Shot | 0.7271 | 0.5250 | 0.8333 |
| Chain-of-Thought | 0.6966 | 0.5450 | 0.8333 |
| Self-RAG | 0.5802 | **0.6250** | 0.8333 |
| Step-Back | 0.5692 | 0.5583 | 0.8333 |
| Sub-Context | 0.4483 | 0.5250 | 0.8333 |

**Tech:** `Python` `ChromaDB` `HuggingFace` `LangChain` `RAGAS` `OpenRouter` `Llama 3` `Streamlit`

---

## How the 3 Projects Connect
```
PostgreSQL (DigitalOcean)  ←  the shared data spine across all 3 projects
        │
        ├── Project 1 writes:   orders, inventory, labor,
        │                       shipments, safety_incidents
        │                       (8,032 rows, 90 days of warehouse ops)
        │
        ├── Project 2 adds:     forecasts, reorder_params,
        │                       lean_waste_flags, suppliers, sku_master
        │                       (+14,374 rows of ML outputs)
        │
        └── Project 3 reads:    ALL 8 tables → 1,780 ChromaDB chunks → RAG chatbot

Power BI   → connects to PostgreSQL (P1 executive layer)
DBeaver    → validates data at every pipeline stage
Streamlit  → 3 live dashboards, all reading from same DB
```

Data flows forward: P1 generates KPI data → P2 adds forecast and waste tables →
P3 RAG pipeline reads from everything and answers questions in plain English.

---

## Shared Infrastructure

All three projects share the same live PostgreSQL database on DigitalOcean:
```
Database: main_db
Host:     DigitalOcean Droplet (self-managed, sslmode=disable)

Tables from P1: orders · inventory · labor · shipments · safety_incidents
Tables from P2: forecasts · reorder_params · lean_waste_flags · erp_export_log · suppliers · sku_master
Tables from P3: reads all of the above → ChromaDB (local vector store)

Total rows: 22,406 across 8 ingested tables
```

---

## How to Navigate This Repo

Each project is self-contained with its own `README.md`, `requirements.txt`,
and virtual environment. Start with the project README for full setup instructions.
```
warehouse-intelligence-portfolio/
├── README.md                        ← You are here
│
├── project1-kpi-dashboard/
│   ├── README.md                    ← P1 setup + docs
│   ├── dashboard.py                 ← Streamlit app
│   ├── kpi_engine.py                ← 6 KPI functions
│   └── db/ charts/ powerbi/
│
├── project2-forecasting/
│   ├── README.md                    ← P2 setup + docs
│   ├── main.py                      ← Pipeline orchestrator
│   ├── app.py                       ← Streamlit dashboard
│   └── db/ modules/ reports/
│
└── project3-rag-chatbot/
    ├── README.md                    ← P3 setup + docs
    ├── app.py                       ← Streamlit chat UI
    ├── config.py                    ← Centralised settings
    └── pipeline/ prompting/ evaluation/
```

---

## Full Tech Stack

| Category | Technologies |
|---|---|
| Language | Python 3.11 |
| Database | PostgreSQL on DigitalOcean |
| Dashboarding | Streamlit (3 live apps) · Power BI Desktop |
| ML / Forecasting | Facebook Prophet · scikit-learn |
| RAG Pipeline | ChromaDB · LangChain · HuggingFace all-MiniLM-L6-v2 |
| LLM | Llama 3 8B via OpenRouter |
| RAG Evaluation | RAGAS 0.4.3 |
| Visualisation | Plotly |
| ERP Integration | SAP MM MRP II flat file (pipe-delimited) |
| Data Engineering | SQLAlchemy · pandas · psycopg2 |
| Deployment | Streamlit Cloud · GitHub |
| Validation | DBeaver |

---

## Live URLs

| Project | Live URL |
|---|---|
| P1 — KPI Dashboard | https://hari-warehouse-kpi-p1.streamlit.app |
| P2 — Forecasting Engine | https://hari-warehouse-p2.streamlit.app |
| P3 — RAG Chatbot | https://hari-warehouse-p3-ai.streamlit.app |
| Power BI Report | https://app.powerbi.com/view?r=eyJrIjoiNTVhMzEzOWEtZjM4NC00MWM4LTgwOTYtNGM1OTRhMWJkMjMxIiwidCI6ImUwNWI2YjNmLTE5ODAtNGIyNC04NjM3LTU4MDc3MWY0NGRlZSIsImMiOjN9 |
| GitHub | https://github.com/ambtiharibabu/Warehouse-intelligence-portfolio |

---

## Author

<<<<<<< Updated upstream
**Haribabu Ambati** — MSBA Student |Supply Chain & Operations expert and enthusiast | Supply Chain  · Python · ML · Data Engineering .

[LinkedIn](https://www.linkedin.com/in/haribabuambati) · [GitHub](https://github.com/ambtiharibabu)

=======
**Haribabu Ambati**  
MSBA Student |Supply Chain & Operations expert and enthusiast | Supply Chain  · Python · ML · Data Engineering . 
[LinkedIn](https://www.linkedin.com/in/haribabuambati) · [GitHub](https://github.com/ambtiharibabu)
>>>>>>> Stashed changes
