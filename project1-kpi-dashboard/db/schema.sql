-- ============================================================
-- Warehouse KPI Dashboard — Database Schema
-- Run once to create all 5 tables in PostgreSQL
-- Safe to re-run: IF NOT EXISTS prevents duplicate errors
-- ============================================================

-- Table 1: Every customer order and its fulfillment outcome
CREATE TABLE IF NOT EXISTS orders (
    order_id             VARCHAR PRIMARY KEY,
    sku                  VARCHAR,
    order_date           DATE,
    shift                VARCHAR,        -- AM / PM / Night
    status               VARCHAR,        -- fulfilled / late / failed
    fulfillment_time_hrs FLOAT
);

-- Table 2: Cycle count records — expected vs actual inventory
CREATE TABLE IF NOT EXISTS inventory (
    record_id      SERIAL PRIMARY KEY,  -- auto-numbered, no input needed
    sku            VARCHAR,
    count_date     DATE,
    expected_count INT,
    actual_count   INT,
    location       VARCHAR,
    category       VARCHAR
);

-- Table 3: Associate-level labor records per shift
CREATE TABLE IF NOT EXISTS labor (
    record_id       SERIAL PRIMARY KEY,
    associate_id    VARCHAR,
    shift           VARCHAR,
    work_date       DATE,
    units_processed INT,
    hours_worked    FLOAT,
    department      VARCHAR
);

-- Table 4: Safety incident log
CREATE TABLE IF NOT EXISTS safety_incidents (
    incident_id   VARCHAR PRIMARY KEY,
    incident_date DATE,
    shift         VARCHAR,
    incident_type VARCHAR,    -- near-miss / injury / violation
    severity      VARCHAR     -- low / medium / high
);

-- Table 5: Outbound shipment records
CREATE TABLE IF NOT EXISTS shipments (
    shipment_id    VARCHAR PRIMARY KEY,
    ship_date      DATE,
    scheduled_time TIMESTAMP,
    actual_time    TIMESTAMP,
    status         VARCHAR,   -- on-time / late
    carrier        VARCHAR
);