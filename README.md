# 🏭 Warehouse Intelligence Portfolio

A 3-project portfolio demonstrating end-to-end data engineering,
machine learning, and operational analytics applied to warehouse
and supply chain operations.

Built on a live PostgreSQL database hosted on DigitalOcean,
with real data pipelines, interactive dashboards, and
enterprise-ready outputs.

---

## Projects

### 📊 Project 1 — Warehouse KPI Dashboard
**Folder:** `project1-kpi-dashboard/`

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

**Tech:** Python · PostgreSQL · Streamlit · Plotly · Power BI · pandas · openpyxl

🌐 **Live Dashboard →** [Streamlit App](https://hari-warehouse-kpi-p1.streamlit.app)

→ [View Project 1 README](project1-kpi-dashboard/README.md)

---

### 🏭 Project 2 — Inventory Forecasting & Lean Waste Detection Engine
**Folder:** `project2-forecasting/`

A 6-module Python pipeline that reads live warehouse data,
runs ML-powered demand forecasting, optimises reorder parameters
using EOQ modelling, and surfaces $1M+ in annual Lean waste —
outputting results to PostgreSQL, Excel, and SAP-compatible ERP flat files.

**What it does:**
- Facebook Prophet demand forecasting (20 SKUs, 30-day horizon)
- EOQ + Safety Stock + Reorder Point optimisation ($441K savings identified)
- Lean waste detection: excess inventory, over-ordering, demand planning failure
- SAP MM MRP II flat file export (MM17 transaction ready)
- 5-sheet Excel MRP report for warehouse directors
- Streamlit dashboard with 6 pages, global filters, and download buttons

**Tech:** Python · PostgreSQL · Prophet · Streamlit · Plotly · SAP MM · pandas · openpyxl

🌐 **Live Dashboard →** [Streamlit App](https://hari-warehouse-p2.streamlit.app)

→ [View Project 2 README](project2-forecasting/README.md)

---

### 🤖 Project 3 — RAG Pipeline *(Coming Soon)*
**Folder:** `project3-rag-pipeline/` *(in development)*

A Retrieval-Augmented Generation pipeline that lets operations teams
query warehouse documentation, SOPs, and historical incident data
using natural language — powered by the same PostgreSQL database.

---

## Shared Infrastructure

All three projects share the same live PostgreSQL database on a
DigitalOcean Droplet:
```
Database: main_db
Tables from P1: orders · inventory · labor · shipments · safety_incidents
Tables from P2: forecasts · reorder_params · lean_waste_flags · erp_export_log
Tables from P3: (coming soon)
```

Data flows forward: P1 generates KPI data → P2 adds forecast tables →
P3 RAG pipeline reads from everything.

---

## How to Navigate This Repo

Each project is self-contained in its own subfolder with its own
`README.md`, `requirements.txt`, and virtual environment setup.
Start with the project README for setup instructions.
```
warehouse-intelligence-portfolio/
├── README.md                        ← You are here
├── project1-kpi-dashboard/
│   ├── README.md                    ← P1 setup + docs
│   └── ...
├── project2-forecasting/
│   ├── README.md                    ← P2 setup + docs
│   └── ...
└── project3-rag-pipeline/           ← Coming soon
```

---

## Author

**Haribabu Ambati** — Supply Chain & Operations Professional
transitioning into data-driven operations roles.

[GitHub](https://github.com/ambtiharibabu) ·
[LinkedIn](www.linkedin.com/in/haribabuambati)
