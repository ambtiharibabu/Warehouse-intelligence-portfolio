# pipeline/ingest.py
# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — Read all PostgreSQL tables into DataFrames + inspect structure
# PART 2 — Convert rows into text chunks with metadata  ← THIS STEP
# PART 3 — Embed chunks and store in ChromaDB           ← NEXT STEP
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
import pandas as pd
from datetime import timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — Database connection + table loading (unchanged from Step 4)
# ─────────────────────────────────────────────────────────────────────────────

def get_engine():
    connection_url = URL.create(
        drivername = config.DB_CONFIG["drivername"],
        username   = config.DB_CONFIG["username"],
        password   = config.DB_CONFIG["password"],
        host       = config.DB_CONFIG["host"],
        port       = config.DB_CONFIG["port"],
        database   = config.DB_CONFIG["database"],
    )
    return create_engine(
        connection_url,
        connect_args={"sslmode": config.DB_SSLMODE}
    )

def load_all_tables(engine):
    print("\n[INGEST] Loading tables from PostgreSQL...")
    tables = {}
    for table_name in config.TABLES_TO_INGEST:
        try:
            df = pd.read_sql(f"SELECT * FROM {table_name}", engine)
            tables[table_name] = df
            print(f"  ✓ {table_name:<25} {len(df):>6,} rows")
        except Exception as e:
            print(f"  ✗ {table_name:<25} FAILED: {e}")
    return tables

def inspect_tables(tables):
    print("\n" + "=" * 60)
    print("  TABLE INSPECTION — columns + sample rows")
    print("=" * 60)
    for table_name, df in tables.items():
        print(f"\n{'─' * 60}")
        print(f"  TABLE: {table_name.upper()}  ({len(df):,} rows × {df.shape[1]} cols)")
        print(f"{'─' * 60}")
        print("  COLUMNS:")
        for col, dtype in df.dtypes.items():
            print(f"    {col:<30} {str(dtype):<15}")
        print("\n  SAMPLE (first 2 rows):")
        print(df.head(2).to_string(index=False))
        print()

# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — Chunking: convert DataFrames → list of (text, metadata) tuples
# ─────────────────────────────────────────────────────────────────────────────
# Each chunk = (text_string, metadata_dict)
# text_string  → what gets embedded and searched
# metadata_dict → what gets stored for filtering and citation

# ── Chunk Type 1a: Orders ─────────────────────────────────────────────────────
# Strategy: group by SKU + 7-day rolling window
# Why 7 days: long enough to show meaningful fulfillment patterns,
#             short enough that each chunk is about one SKU's one week

def chunk_orders(df):
    chunks = []
    df["order_date"] = pd.to_datetime(df["order_date"])

    # Get the full date range in the data
    min_date = df["order_date"].min()
    max_date = df["order_date"].max()

    # Build a list of 7-day window start dates covering the full history
    window_starts = []
    current = min_date
    while current <= max_date:
        window_starts.append(current)
        current += timedelta(days=7)

    skus = df["sku"].unique()

    for sku in skus:
        sku_df = df[df["sku"] == sku]

        for window_start in window_starts:
            window_end = window_start + timedelta(days=6)

            # Filter to just this SKU + this 7-day window
            window_df = sku_df[
                (sku_df["order_date"] >= window_start) &
                (sku_df["order_date"] <= window_end)
            ]

            # Skip empty windows — not every SKU has orders every week
            if len(window_df) == 0:
                continue

            # Calculate KPIs for this window
            total        = len(window_df)
            fulfilled    = (window_df["status"] == "fulfilled").sum()
            late         = (window_df["status"] == "late").sum()
            failed       = (window_df["status"] == "failed").sum()
            fulfill_rate = round((fulfilled / total) * 100, 1) if total > 0 else 0
            avg_time     = round(window_df["fulfillment_time_hrs"].mean(), 2)

            # Shift breakdown
            shift_counts = window_df["shift"].value_counts().to_dict()
            shift_str    = ", ".join(f"{s}={c}" for s, c in shift_counts.items())

            # Build the natural language text for this chunk
            date_range_str = f"{window_start.date()} to {window_end.date()}"
            text = (
                f"Order performance for {sku} during {date_range_str}: "
                f"{total} total orders. "
                f"{fulfilled} fulfilled ({fulfill_rate}%), "
                f"{late} late, {failed} failed. "
                f"Average fulfillment time: {avg_time} hours. "
                f"Orders by shift: {shift_str}."
            )

            metadata = {
                "source":      "orders",
                "sku":         sku,
                "date_start":  str(window_start.date()),
                "date_end":    str(window_end.date()),
                "kpi_type":    "fulfillment",
                "total_orders": int(total),
                "fulfill_rate": float(fulfill_rate),
            }

            chunks.append((text, metadata))

    return chunks

# ── Chunk Type 1b: Inventory ──────────────────────────────────────────────────
# Strategy: one chunk per SKU — summarise all count records for that SKU
# Why not per-row: each row is a weekly count check. The story is the
# accuracy trend across all checks, not any single count event.

def chunk_inventory(df):
    chunks = []
    df["count_date"] = pd.to_datetime(df["count_date"])

    for sku, sku_df in df.groupby("sku"):
        sku_df = sku_df.sort_values("count_date")

        # Most recent count
        latest       = sku_df.iloc[-1]
        accuracy_pct = round((latest["actual_count"] / latest["expected_count"]) * 100, 1)

        # Average accuracy across all counts for this SKU
        sku_df["accuracy"] = sku_df["actual_count"] / sku_df["expected_count"] * 100
        avg_accuracy = round(sku_df["accuracy"].mean(), 1)

        category = latest["category"]
        location = latest["location"]
        date_range_str = (
            f"{sku_df['count_date'].min().date()} to "
            f"{sku_df['count_date'].max().date()}"
        )

        text = (
            f"Inventory accuracy for {sku} ({category}) "
            f"from {date_range_str}: "
            f"{len(sku_df)} count checks performed. "
            f"Most recent count: {int(latest['actual_count'])} actual vs "
            f"{int(latest['expected_count'])} expected "
            f"({accuracy_pct}% accuracy). "
            f"Average accuracy across all checks: {avg_accuracy}%. "
            f"Current location: {location}."
        )

        metadata = {
            "source":       "inventory",
            "sku":          sku,
            "category":     category,
            "kpi_type":     "inventory_accuracy",
            "latest_accuracy_pct": float(accuracy_pct),
            "avg_accuracy_pct":    float(avg_accuracy),
            "date_start":   str(sku_df["count_date"].min().date()),
            "date_end":     str(sku_df["count_date"].max().date()),
        }

        chunks.append((text, metadata))

    return chunks

# ── Chunk Type 1c: Labor ──────────────────────────────────────────────────────
# Strategy: group by shift + department + 7-day window
# Why: labor has no SKU — the natural grouping is who worked when and where

def chunk_labor(df):
    chunks = []
    df["work_date"] = pd.to_datetime(df["work_date"])

    min_date = df["work_date"].min()
    max_date = df["work_date"].max()

    window_starts = []
    current = min_date
    while current <= max_date:
        window_starts.append(current)
        current += timedelta(days=7)

    for dept, dept_df in df.groupby("department"):
        for shift, shift_df in dept_df.groupby("shift"):
            for window_start in window_starts:
                window_end = window_start + timedelta(days=6)

                window_df = shift_df[
                    (shift_df["work_date"] >= window_start) &
                    (shift_df["work_date"] <= window_end)
                ]

                if len(window_df) == 0:
                    continue

                total_units = window_df["units_processed"].sum()
                total_hours = window_df["hours_worked"].sum()
                productivity = round(total_units / total_hours, 1) if total_hours > 0 else 0
                associates   = window_df["associate_id"].nunique()
                date_range_str = f"{window_start.date()} to {window_end.date()}"

                text = (
                    f"Labor productivity for {dept} department, {shift} shift "
                    f"during {date_range_str}: "
                    f"{associates} associates worked, "
                    f"processing {int(total_units):,} units over "
                    f"{round(total_hours, 1)} hours. "
                    f"Productivity: {productivity} units/hour. "
                    f"Threshold: 85 units/hour (below = underperforming)."
                )

                metadata = {
                    "source":       "labor",
                    "department":   dept,
                    "shift":        shift,
                    "kpi_type":     "labor_productivity",
                    "productivity": float(productivity),
                    "date_start":   str(window_start.date()),
                    "date_end":     str(window_end.date()),
                }

                chunks.append((text, metadata))

    return chunks

# ── Chunk Type 1d: Shipments ──────────────────────────────────────────────────
# Strategy: group by carrier + 7-day window
# Why: carrier performance is the key question for shipping data

def chunk_shipments(df):
    chunks = []
    df["ship_date"] = pd.to_datetime(df["ship_date"])

    min_date = df["ship_date"].min()
    max_date = df["ship_date"].max()

    window_starts = []
    current = min_date
    while current <= max_date:
        window_starts.append(current)
        current += timedelta(days=7)

    for carrier, carrier_df in df.groupby("carrier"):
        for window_start in window_starts:
            window_end = window_start + timedelta(days=6)

            window_df = carrier_df[
                (carrier_df["ship_date"] >= window_start) &
                (carrier_df["ship_date"] <= window_end)
            ]

            if len(window_df) == 0:
                continue

            total    = len(window_df)
            on_time  = (window_df["status"] == "on-time").sum()
            late     = (window_df["status"] == "late").sum()
            ontime_rate = round((on_time / total) * 100, 1) if total > 0 else 0
            date_range_str = f"{window_start.date()} to {window_end.date()}"

            text = (
                f"Shipping performance for {carrier} "
                f"during {date_range_str}: "
                f"{total} shipments total. "
                f"{on_time} on-time ({ontime_rate}%), "
                f"{late} late. "
                f"On-time threshold: 92%."
            )

            metadata = {
                "source":      "shipments",
                "carrier":     carrier,
                "kpi_type":    "shipping_performance",
                "ontime_rate": float(ontime_rate),
                "date_start":  str(window_start.date()),
                "date_end":    str(window_end.date()),
            }

            chunks.append((text, metadata))

    return chunks

# ── Chunk Type 1e: Safety Incidents ──────────────────────────────────────────
# Strategy: one chunk for the entire table (only 4 rows — no need to split)

def chunk_safety(df):
    chunks = []
    df["incident_date"] = pd.to_datetime(df["incident_date"])

    total      = len(df)
    by_type    = df["incident_type"].value_counts().to_dict()
    by_severity = df["severity"].value_counts().to_dict()
    by_shift   = df["shift"].value_counts().to_dict()

    type_str     = ", ".join(f"{k}: {v}" for k, v in by_type.items())
    severity_str = ", ".join(f"{k}: {v}" for k, v in by_severity.items())
    shift_str    = ", ".join(f"{k}: {v}" for k, v in by_shift.items())

    date_range_str = (
        f"{df['incident_date'].min().date()} to "
        f"{df['incident_date'].max().date()}"
    )

    text = (
        f"OSHA safety incidents from {date_range_str}: "
        f"{total} total incidents recorded. "
        f"By type: {type_str}. "
        f"By severity: {severity_str}. "
        f"By shift: {shift_str}. "
        f"OSHA incident rate threshold: 1.5 per 10,000 hours worked."
    )

    metadata = {
        "source":        "safety_incidents",
        "kpi_type":      "osha_safety",
        "total_incidents": int(total),
        "date_start":    str(df["incident_date"].min().date()),
        "date_end":      str(df["incident_date"].max().date()),
    }

    chunks.append((text, metadata))
    return chunks

# ── Chunk Type 2: Forecasts ───────────────────────────────────────────────────
# Strategy: one chunk per SKU covering its full 30-day forecast window
# Why: a supervisor asking "what's the forecast for SKU-X" wants the
#      full picture, not day-by-day fragments

def chunk_forecasts(df):
    chunks = []
    df["forecast_date"] = pd.to_datetime(df["forecast_date"])

    for sku, sku_df in df.groupby("sku"):
        sku_df = sku_df.sort_values("forecast_date")

        avg_forecast  = round(sku_df["yhat"].mean(), 2)
        peak_forecast = round(sku_df["yhat"].max(), 2)
        low_forecast  = round(sku_df["yhat"].min(), 2)
        total_demand  = round(sku_df["yhat"].sum(), 1)
        date_start    = sku_df["forecast_date"].min().date()
        date_end      = sku_df["forecast_date"].max().date()
        days          = len(sku_df)

        text = (
            f"30-day demand forecast for {sku} "
            f"({date_start} to {date_end}): "
            f"{days} days forecasted. "
            f"Total projected demand: {total_demand} units. "
            f"Average daily demand: {avg_forecast} units/day. "
            f"Peak day: {peak_forecast} units. "
            f"Lowest day: {low_forecast} units. "
            f"Model: Prophet time-series forecasting."
        )

        metadata = {
            "source":        "forecasts",
            "sku":           sku,
            "kpi_type":      "demand_forecast",
            "avg_daily":     float(avg_forecast),
            "total_demand":  float(total_demand),
            "date_start":    str(date_start),
            "date_end":      str(date_end),
        }

        chunks.append((text, metadata))

    return chunks

# ── Chunk Type 3a: Reorder Parameters ────────────────────────────────────────
# Strategy: one chunk per SKU — each row already contains a full SKU summary
# reorder_params is the densest table: 14 columns of operational intelligence

def chunk_reorder_params(df):
    chunks = []

    for _, row in df.iterrows():
        sku       = row["sku"]
        risk      = row["stockout_risk"]
        savings   = round(row["potential_savings_usd"], 0)
        gap       = round(row["gap"], 1)

        text = (
            f"Reorder parameters for {sku}: "
            f"Current stock: {int(row['current_stock'])} units "
            f"({round(row['days_of_stock'], 0):.0f} days of supply). "
            f"Stockout risk: {risk}. "
            f"Lead time: {int(row['lead_time_days'])} days. "
            f"Optimal reorder point (ROP): {round(row['optimal_rop'], 1)} units. "
            f"Current ROP: {round(row['current_rop'], 1)} units "
            f"(gap: {gap} units — "
            f"{'reordering too early, excess inventory building' if gap < 0 else 'reordering too late, stockout risk'}). "
            f"Economic Order Quantity (EOQ): {round(row['eoq'], 1)} units. "
            f"Safety stock: {round(row['safety_stock'], 1)} units. "
            f"Potential annual savings from ROP optimisation: "
            f"${int(savings):,}."
        )

        metadata = {
            "source":         "reorder_params",
            "sku":            sku,
            "kpi_type":       "reorder_optimisation",
            "stockout_risk":  risk,
            "days_of_stock":  float(row["days_of_stock"]),
            "potential_savings_usd": float(savings),
        }

        chunks.append((text, metadata))

    return chunks

# ── Chunk Type 3b: Lean Waste Flags ──────────────────────────────────────────
# Strategy: one chunk per flag row — each flag already has a rich detail field
# The detail column is essentially pre-written natural language

def chunk_lean_waste(df):
    chunks = []

    for _, row in df.iterrows():
        sku        = row["sku"]
        waste_type = row["waste_type"]
        severity   = row["severity"]
        waste_usd  = round(row["annual_waste_usd"], 0)
        detail     = row["detail"]

        # Map waste_type to a plain English label
        waste_labels = {
            "excess_inventory":       "Excess Inventory",
            "over_ordering":          "Over-Ordering",
            "demand_planning_failure": "Demand Planning Failure",
        }
        waste_label = waste_labels.get(waste_type, waste_type)

        text = (
            f"Lean waste flag for {sku}: "
            f"Waste type: {waste_label}. "
            f"Severity: {severity}. "
            f"Estimated annual waste cost: ${int(waste_usd):,}. "
            f"Detail: {detail}."
        )

        metadata = {
            "source":           "lean_waste_flags",
            "sku":              sku,
            "waste_type":       waste_type,
            "severity":         severity,
            "annual_waste_usd": float(waste_usd),
            "kpi_type":         "lean_waste",
        }

        chunks.append((text, metadata))

    return chunks

# ── Chunk Type 4: Daily Summary ───────────────────────────────────────────────
# Strategy: one summary chunk per day — a high-level warehouse health snapshot
# Best for broad queries like "how was the warehouse doing last Tuesday?"

def chunk_daily_summary(tables):
    chunks = []

    orders_df    = tables["orders"].copy()
    labor_df     = tables["labor"].copy()
    shipments_df = tables["shipments"].copy()

    orders_df["order_date"]    = pd.to_datetime(orders_df["order_date"])
    labor_df["work_date"]      = pd.to_datetime(labor_df["work_date"])
    shipments_df["ship_date"]  = pd.to_datetime(shipments_df["ship_date"])

    # Get all unique dates that appear across any of the three tables
    all_dates = sorted(set(
        orders_df["order_date"].dt.date.tolist() +
        labor_df["work_date"].dt.date.tolist() +
        shipments_df["ship_date"].dt.date.tolist()
    ))

    for date in all_dates:
        # Orders on this date
        day_orders = orders_df[orders_df["order_date"].dt.date == date]
        total_ord  = len(day_orders)
        if total_ord > 0:
            fulfill_rate = round(
                (day_orders["status"] == "fulfilled").sum() / total_ord * 100, 1
            )
        else:
            fulfill_rate = None

        # Labor on this date
        day_labor    = labor_df[labor_df["work_date"].dt.date == date]
        total_units  = day_labor["units_processed"].sum()
        total_hours  = day_labor["hours_worked"].sum()
        productivity = round(total_units / total_hours, 1) if total_hours > 0 else None

        # Shipments on this date
        day_ships  = shipments_df[shipments_df["ship_date"].dt.date == date]
        total_ships = len(day_ships)
        if total_ships > 0:
            ontime_rate = round(
                (day_ships["status"] == "on-time").sum() / total_ships * 100, 1
            )
        else:
            ontime_rate = None

        # Only write a chunk if there's at least some data for this day
        if total_ord == 0 and productivity is None and total_ships == 0:
            continue

        parts = [f"Warehouse daily summary for {date}:"]
        if total_ord > 0:
            parts.append(
                f"Orders: {total_ord} processed, "
                f"{fulfill_rate}% fulfillment rate."
            )
        if productivity is not None:
            parts.append(
                f"Labor: {int(total_units):,} units processed, "
                f"{productivity} units/hour productivity."
            )
        if total_ships > 0:
            parts.append(
                f"Shipping: {total_ships} shipments, "
                f"{ontime_rate}% on-time."
            )

        text = " ".join(parts)

        metadata = {
            "source":       "daily_summary",
            "date":         str(date),
            "kpi_type":     "daily_summary",
            "fulfill_rate": float(fulfill_rate) if fulfill_rate is not None else 0.0,
            "productivity": float(productivity) if productivity is not None else 0.0,
            "ontime_rate":  float(ontime_rate) if ontime_rate is not None else 0.0,
        }

        chunks.append((text, metadata))

    return chunks

# ── Master chunking function ──────────────────────────────────────────────────
# Calls all chunk builders and returns one combined list

def build_all_chunks(tables):
    print("\n[INGEST] Building chunks from all tables...")

    all_chunks = []

    # Type 1 — KPI chunks (operational tables)
    orders_chunks   = chunk_orders(tables["orders"])
    inventory_chunks = chunk_inventory(tables["inventory"])
    labor_chunks    = chunk_labor(tables["labor"])
    shipment_chunks = chunk_shipments(tables["shipments"])
    safety_chunks   = chunk_safety(tables["safety_incidents"])

    # Type 2 — Forecast chunks
    forecast_chunks = chunk_forecasts(tables["forecasts"])

    # Type 3 — Reorder + Lean waste chunks
    reorder_chunks  = chunk_reorder_params(tables["reorder_params"])
    lean_chunks     = chunk_lean_waste(tables["lean_waste_flags"])

    # Type 4 — Daily summary chunks
    summary_chunks  = chunk_daily_summary(tables)

    # Print counts per type
    print(f"  ✓ orders          → {len(orders_chunks):>5} chunks")
    print(f"  ✓ inventory       → {len(inventory_chunks):>5} chunks")
    print(f"  ✓ labor           → {len(labor_chunks):>5} chunks")
    print(f"  ✓ shipments       → {len(shipment_chunks):>5} chunks")
    print(f"  ✓ safety          → {len(safety_chunks):>5} chunks")
    print(f"  ✓ forecasts       → {len(forecast_chunks):>5} chunks")
    print(f"  ✓ reorder_params  → {len(reorder_chunks):>5} chunks")
    print(f"  ✓ lean_waste_flags→ {len(lean_chunks):>5} chunks")
    print(f"  ✓ daily_summary   → {len(summary_chunks):>5} chunks")

    all_chunks = (
        orders_chunks + inventory_chunks + labor_chunks +
        shipment_chunks + safety_chunks + forecast_chunks +
        reorder_chunks + lean_chunks + summary_chunks
    )

    print(f"\n  TOTAL chunks built: {len(all_chunks):,}")
    return all_chunks

# ─────────────────────────────────────────────────────────────────────────────
# PART 3 — Embed + store in ChromaDB (next step — placeholder for now)
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# PART 3 — Embed chunks + store in ChromaDB
# ─────────────────────────────────────────────────────────────────────────────

def embed_and_store(chunks):
    """
    Takes the full list of (text, metadata) tuples.
    Embeds each text with all-MiniLM-L6-v2.
    Stores text + embedding + metadata in ChromaDB.
    Uses upsert so this is safely re-runnable.
    """
    from sentence_transformers import SentenceTransformer
    import chromadb

    # ── Load embedding model ──────────────────────────────────────────────────
    # First run: downloads ~90MB model weights to local cache (~30 seconds)
    # All subsequent runs: loads from cache instantly
    print("\n[INGEST] Loading embedding model...")
    model = SentenceTransformer(config.EMBEDDING_MODEL)
    print(f"  ✓ Model loaded: {config.EMBEDDING_MODEL}")

    # ── Connect to ChromaDB (local persistent) ────────────────────────────────
    # PersistentClient writes index files to disk at CHROMA_PATH
    # Creates the folder automatically if it doesn't exist
    print(f"\n[INGEST] Connecting to ChromaDB at: {config.CHROMA_PATH}")
    client = chromadb.PersistentClient(path=config.CHROMA_PATH)

    # Get or create the collection
    # If collection already exists, upsert below will update matching IDs
    collection = client.get_or_create_collection(
        name     = config.CHROMA_COLLECTION_NAME,
        metadata = {"hnsw:space": "cosine"},
        # cosine similarity: measures angle between vectors
        # better than euclidean distance for text embeddings
    )
    print(f"  ✓ Collection ready: {config.CHROMA_COLLECTION_NAME}")

    # ── Prepare data for ChromaDB ─────────────────────────────────────────────
    # ChromaDB expects four parallel lists:
    #   ids        → unique string ID per chunk
    #   documents  → the raw text strings
    #   embeddings → the numerical vectors
    #   metadatas  → the metadata dicts

    texts     = [chunk[0] for chunk in chunks]
    metadatas = [chunk[1] for chunk in chunks]

    # Build unique IDs: "chunk_0000", "chunk_0001", ...
    # Zero-padded to 4 digits so they sort cleanly
    ids = [f"chunk_{str(i).zfill(4)}" for i in range(len(chunks))]

    # ── Embed in batches ──────────────────────────────────────────────────────
    # Batch size 100: fast enough, low memory, good for 1,780 chunks
    # show_progress_bar=True prints a live progress bar in the terminal
    print(f"\n[INGEST] Embedding {len(texts):,} chunks...")
    print(f"  Model: {config.EMBEDDING_MODEL}  |  Batch size: 100")

    embeddings = model.encode(
        texts,
        batch_size        = 100,
        show_progress_bar = True,
        convert_to_numpy  = True,   # ChromaDB expects numpy arrays or plain lists
    ).tolist()                      # convert to plain Python lists for ChromaDB

    print(f"  ✓ Embeddings generated: {len(embeddings):,} vectors")
    print(f"  ✓ Vector dimensions: {len(embeddings[0])}")  # should be 384

    # ── Upsert into ChromaDB in batches ──────────────────────────────────────
    # Upsert = insert new + update existing (matched by id)
    # Safe to re-run — won't create duplicates
    print(f"\n[INGEST] Storing chunks in ChromaDB...")

    BATCH_SIZE = 100
    total_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(total_batches):
        start = batch_num * BATCH_SIZE
        end   = min(start + BATCH_SIZE, len(chunks))

        collection.upsert(
            ids        = ids[start:end],
            documents  = texts[start:end],
            embeddings = embeddings[start:end],
            metadatas  = metadatas[start:end],
        )

        print(f"  Batch {batch_num + 1}/{total_batches} stored "
              f"(chunks {start}–{end - 1})")

    # ── Verify storage ────────────────────────────────────────────────────────
    final_count = collection.count()
    print(f"\n  ✓ ChromaDB collection now contains: {final_count:,} chunks")

    return collection


# ─────────────────────────────────────────────────────────────────────────────
# Main — full pipeline: load → chunk → embed → store
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  P3 RAG Pipeline — Ingest (Part 3: Embed + Store)")
    print("=" * 60)

    engine     = get_engine()
    tables     = load_all_tables(engine)
    chunks     = build_all_chunks(tables)
    collection = embed_and_store(chunks)

    # ── Quick sanity query ────────────────────────────────────────────────────
    # Test that ChromaDB can actually retrieve something meaningful
    # We embed one test question and check what comes back
    print("\n[INGEST] Running sanity query on ChromaDB...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(config.EMBEDDING_MODEL)

    test_query     = "Which SKUs are at stockout risk?"
    query_embedding = model.encode(test_query).tolist()

    results = collection.query(
        query_embeddings = [query_embedding],
        n_results        = 3,
    )

    print(f"\n  Query: '{test_query}'")
    print(f"  Top 3 retrieved chunks:\n")
    for i, (doc, meta) in enumerate(
        zip(results["documents"][0], results["metadatas"][0])
    ):
        print(f"  [{i+1}] source={meta['source']} | sku={meta.get('sku','N/A')}")
        print(f"       {doc[:120]}...")
        print()

    print("=" * 60)
    print("  Ingest complete — ChromaDB is loaded and queryable")
    print("=" * 60)
 