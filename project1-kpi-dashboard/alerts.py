# ============================================================
# alerts.py
# Applies threshold rules to KPI values and returns
# color-coded status flags: green / yellow / red
# Imported by dashboard.py to drive KPI card colors
# ============================================================

# ============================================================
# THRESHOLD CONFIGURATION TABLE
# Edit numbers here to change alert behavior globally.
# direction: "lower_is_worse" → alert when value drops below threshold
#            "higher_is_worse" → alert when value rises above threshold
# ============================================================
THRESHOLDS = {
    "fulfillment": {
        "label":     "Order Fulfillment Rate",
        "direction": "lower_is_worse",
        "warning":   98.0,   # yellow below this
        "alert":     95.0    # red below this
    },
    "inventory": {
        "label":     "Inventory Accuracy",
        "direction": "lower_is_worse",
        "warning":   99.0,
        "alert":     97.0
    },
    "productivity": {
        "label":     "Labor Productivity",
        "direction": "lower_is_worse",
        "warning":   95.0,
        "alert":     85.0
    },
    "osha": {
        "label":     "OSHA Incident Rate",
        "direction": "higher_is_worse",
        "warning":   1.0,    # yellow above this
        "alert":     1.5     # red above this
    },
    "shipping": {
        "label":     "Shipping On-Time %",
        "direction": "lower_is_worse",
        "warning":   96.0,
        "alert":     92.0
    },
    "cycle_time": {
        "label":     "Receiving Cycle Time",
        "direction": "higher_is_worse",
        "warning":   3.0,
        "alert":     4.0
    }
}

# ============================================================
# CORE FUNCTION: get_status()
# Takes a KPI key and its numeric value.
# Returns: "green", "yellow", or "red"
# ============================================================
def get_status(kpi_key, value):
    """
    Looks up the threshold config for a KPI and returns
    a color string based on where the value falls.
    """
    config    = THRESHOLDS[kpi_key]
    direction = config["direction"]
    warning   = config["warning"]
    alert     = config["alert"]

    if direction == "lower_is_worse":
        # Good → Warning → Alert as value decreases
        if value >= warning:
            return "green"
        elif value >= alert:
            return "yellow"
        else:
            return "red"

    elif direction == "higher_is_worse":
        # Good → Warning → Alert as value increases
        if value <= warning:
            return "green"
        elif value <= alert:
            return "yellow"
        else:
            return "red"


# ============================================================
# HELPER: get_color_hex()
# Converts status string to a hex color code.
# Used by Streamlit to style KPI cards directly.
# ============================================================
def get_color_hex(status):
    return {
        "green":  "#28a745",
        "yellow": "#ffc107",
        "red":    "#dc3545"
    }.get(status, "#6c757d")   # grey as fallback


# ============================================================
# MASTER FUNCTION: evaluate_all_kpis()
# Takes the full dict returned by kpi_engine.get_all_kpis()
# Returns each KPI enriched with status + color fields
# ============================================================
def evaluate_all_kpis(kpis):
    """
    Input:  dict from kpi_engine.get_all_kpis()
    Output: same dict with two new fields added per KPI:
            - "status" → "green" / "yellow" / "red"
            - "color"  → hex color string for the UI
    """
    results = {}

    for kpi_key, kpi_data in kpis.items():
        value  = kpi_data["value"]
        status = get_status(kpi_key, value)
        color  = get_color_hex(status)

        # Copy the original KPI data and add the new fields
        results[kpi_key] = {
            **kpi_data,       # unpacks all existing fields (value, label, unit...)
            "status": status,
            "color":  color
        }

    return results


# ============================================================
# QUICK TEST — run directly to verify alert logic
# ============================================================
if __name__ == "__main__":
    from kpi_engine import get_all_kpis

    print("Running Alerts Engine test...\n")
    raw_kpis      = get_all_kpis()
    evaluated     = evaluate_all_kpis(raw_kpis)

    for key, data in evaluated.items():
        status_icon = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(data["status"], "⚪")
        print(f"{status_icon}  {data['label']}: {data['value']} {data['unit']}  → {data['status'].upper()}")