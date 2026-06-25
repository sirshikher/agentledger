"""
AgentLedger Agent Tools
========================
Custom Python tool functions for ADK agents (Day 2: custom tools).
Includes the anomaly detection skill (Day 1: agent skills).

These tools operate on in-memory data passed by the orchestrator,
keeping each agent's data scope constrained (Day 1: security).
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from config import DB_PATH, SPEND_SPIKE_THRESHOLD, RENEWAL_WARNING_DAYS


# ============================================================
# INGESTION TOOLS
# ============================================================

def fetch_all_invoices(period_start: str = "", period_end: str = "") -> str:
    """
    Fetch all invoices, optionally filtered by period range.
    Called by the Ingestion Agent.

    Args:
        period_start: Start period in YYYY-MM format (inclusive).
        period_end: End period in YYYY-MM format (inclusive).

    Returns:
        JSON string with list of invoice records.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    query = "SELECT vendor, category, amount, period, invoice_date FROM invoices WHERE 1=1"
    params = []

    if period_start:
        query += " AND period >= ?"
        params.append(period_start)
    if period_end:
        query += " AND period <= ?"
        params.append(period_end)

    query += " ORDER BY period DESC, vendor ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return json.dumps([dict(r) for r in rows], indent=2)


def fetch_all_usage(period_start: str = "", period_end: str = "") -> str:
    """
    Fetch all API/LLM usage records.
    Called by the Ingestion Agent.

    Args:
        period_start: Start period in YYYY-MM format.
        period_end: End period in YYYY-MM format.

    Returns:
        JSON string with list of usage records.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    query = "SELECT service, category, period, tokens_used, api_calls, compute_hours, estimated_cost FROM usage_records WHERE 1=1"
    params = []

    if period_start:
        query += " AND period >= ?"
        params.append(period_start)
    if period_end:
        query += " AND period <= ?"
        params.append(period_end)

    query += " ORDER BY period DESC, service ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return json.dumps([dict(r) for r in rows], indent=2)


def fetch_all_contracts() -> str:
    """
    Fetch all vendor contracts.
    Called by the Ingestion Agent.

    Returns:
        JSON string with list of contract records.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT vendor, category, tier, monthly_cost, renewal_date, contract_terms, cancellation_notice_days FROM contracts"
    ).fetchall()
    conn.close()
    return json.dumps([dict(r) for r in rows], indent=2)


# ============================================================
# ANOMALY DETECTION SKILL (Day 1: Agent Skills)
# ============================================================
# Packaged as a reusable skill: deterministic detection logic
# that can be loaded by any anomaly-detection agent.

def detect_spend_spikes(invoices_json: str) -> str:
    """
    Detect month-over-month spend spikes exceeding the threshold.
    This is the deterministic layer - LLM handles explanation.

    Args:
        invoices_json: JSON string of invoice records from ingestion.

    Returns:
        JSON string with detected spend spike anomalies.
    """
    invoices = json.loads(invoices_json)

    # Group by vendor and period
    vendor_periods: dict[str, dict[str, float]] = {}
    for inv in invoices:
        vendor = inv["vendor"]
        if vendor not in vendor_periods:
            vendor_periods[vendor] = {}
        period = inv["period"]
        vendor_periods[vendor][period] = vendor_periods[vendor].get(period, 0) + inv["amount"]

    spikes = []
    for vendor, periods in vendor_periods.items():
        sorted_periods = sorted(periods.items())
        for i in range(1, len(sorted_periods)):
            prev_period, prev_amount = sorted_periods[i - 1]
            curr_period, curr_amount = sorted_periods[i]

            if prev_amount > 0:
                change = (curr_amount - prev_amount) / prev_amount
                if change > SPEND_SPIKE_THRESHOLD:
                    spikes.append({
                        "type": "spend_spike",
                        "vendor": vendor,
                        "period": curr_period,
                        "previous_period": prev_period,
                        "previous_amount": round(prev_amount, 2),
                        "current_amount": round(curr_amount, 2),
                        "change_pct": round(change * 100, 1),
                        "severity": "high" if change > 1.0 else "medium",
                    })

    return json.dumps(spikes, indent=2)


def detect_duplicate_tools(contracts_json: str) -> str:
    """
    Detect overlapping tools in the same category.

    Args:
        contracts_json: JSON string of contract records.

    Returns:
        JSON string with detected duplicate tool anomalies.
    """
    contracts = json.loads(contracts_json)

    category_vendors: dict[str, list[dict]] = {}
    for c in contracts:
        cat = c["category"]
        if cat not in category_vendors:
            category_vendors[cat] = []
        category_vendors[cat].append(c)

    duplicates = []
    for category, vendors in category_vendors.items():
        if len(vendors) > 1 and category not in ("cloud_infra", "llm_api"):
            duplicates.append({
                "type": "duplicate_tools",
                "category": category,
                "vendors": [v["vendor"] for v in vendors],
                "total_monthly_cost": round(sum(v["monthly_cost"] for v in vendors), 2),
                "severity": "medium",
            })

    return json.dumps(duplicates, indent=2)


def detect_upcoming_renewals(contracts_json: str, reference_date: str = "") -> str:
    """
    Detect vendor renewals coming up within the warning window.

    Args:
        contracts_json: JSON string of contract records.
        reference_date: Reference date in YYYY-MM-DD format. Defaults to today.

    Returns:
        JSON string with detected upcoming renewal anomalies.
    """
    contracts = json.loads(contracts_json)

    if reference_date:
        ref = datetime.strptime(reference_date, "%Y-%m-%d")
    else:
        ref = datetime(2026, 6, 20)  # Fixed for reproducible demos

    renewals = []
    for c in contracts:
        if not c.get("renewal_date"):
            continue
        renewal = datetime.strptime(c["renewal_date"], "%Y-%m-%d")
        days_until = (renewal - ref).days

        if 0 < days_until <= RENEWAL_WARNING_DAYS:
            renewals.append({
                "type": "upcoming_renewal",
                "vendor": c["vendor"],
                "renewal_date": c["renewal_date"],
                "days_until_renewal": days_until,
                "monthly_cost": c["monthly_cost"],
                "cancellation_notice_days": c["cancellation_notice_days"],
                "severity": "high" if days_until <= 14 else "medium",
            })

    return json.dumps(renewals, indent=2)


# ============================================================
# NEGOTIATION TOOLS
# ============================================================

def get_vendor_contract(vendor: str) -> str:
    """
    Fetch contract details for a specific vendor.
    Constrained scope: Negotiation agent only sees relevant vendor data.
    (Day 1: security via constrained data scoping)

    Args:
        vendor: Vendor name.

    Returns:
        JSON string with contract details.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM contracts WHERE vendor = ?", (vendor,)
    ).fetchone()
    conn.close()

    if row:
        return json.dumps(dict(row), indent=2)
    return json.dumps({"error": f"No contract found for {vendor}"})


def get_vendor_spend_history(vendor: str) -> str:
    """
    Fetch historical spend for a vendor across all periods.
    Used for trend analysis in negotiation prep.

    Args:
        vendor: Vendor name.

    Returns:
        JSON string with spend history by period.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT period, SUM(amount) as total_amount FROM invoices WHERE vendor = ? GROUP BY period ORDER BY period",
        (vendor,),
    ).fetchall()
    conn.close()
    return json.dumps([dict(r) for r in rows], indent=2)


# ============================================================
# REPORTING TOOLS
# ============================================================

def save_recommendation(vendor: str, period: str, recommendation: str) -> str:
    """
    Save a recommendation to vendor history for long-term memory.
    (Day 3: persistent memory across sessions)

    Args:
        vendor: Vendor name.
        period: Current period.
        recommendation: Recommendation text.

    Returns:
        Confirmation string.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO vendor_history (vendor, period, amount, recommendation, recommendation_date) "
        "SELECT ?, ?, COALESCE((SELECT amount FROM invoices WHERE vendor = ? AND period = ? LIMIT 1), 0), ?, ?",
        (vendor, period, vendor, period, recommendation, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return json.dumps({"status": "saved", "vendor": vendor, "period": period})


def get_past_recommendations(vendor: str = "") -> str:
    """
    Retrieve past recommendations from long-term memory.
    (Day 3: cross-session persistent memory)

    Args:
        vendor: Filter by vendor. Empty for all.

    Returns:
        JSON string with past recommendations.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if vendor:
        rows = conn.execute(
            "SELECT * FROM vendor_history WHERE vendor = ? ORDER BY recommendation_date DESC",
            (vendor,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM vendor_history ORDER BY recommendation_date DESC"
        ).fetchall()
    conn.close()
    return json.dumps([dict(r) for r in rows], indent=2)
