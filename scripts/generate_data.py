"""
Synthetic Data Generator for AgentLedger
=========================================
Generates realistic SaaS invoices, API/LLM usage records, and vendor contracts.
Plants known anomalies for the eval harness (Day 4: evaluation methodology).

Usage:
    python -m scripts.generate_data
"""

import json
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from config import DATA_DIR, DB_PATH


# --- Vendor catalog ---
VENDORS = [
    {"name": "Slack", "category": "communication", "base_cost": 850, "renewal_date": "2026-07-15"},
    {"name": "Notion", "category": "project_management", "base_cost": 600, "renewal_date": "2026-08-20"},
    {"name": "Asana", "category": "project_management", "base_cost": 550, "renewal_date": "2026-09-10"},
    {"name": "GitHub Enterprise", "category": "dev_tools", "base_cost": 1900, "renewal_date": "2026-07-01"},
    {"name": "Datadog", "category": "observability", "base_cost": 2200, "renewal_date": "2026-10-15"},
    {"name": "AWS", "category": "cloud_infra", "base_cost": 8500, "renewal_date": "2027-01-01"},
    {"name": "GCP", "category": "cloud_infra", "base_cost": 3200, "renewal_date": "2026-12-01"},
    {"name": "Figma", "category": "design", "base_cost": 450, "renewal_date": "2026-11-01"},
    {"name": "Jira", "category": "project_management", "base_cost": 480, "renewal_date": "2026-08-01"},
    {"name": "OpenAI API", "category": "llm_api", "base_cost": 1200, "renewal_date": None},
    {"name": "Anthropic API", "category": "llm_api", "base_cost": 800, "renewal_date": None},
    {"name": "Zoom", "category": "communication", "base_cost": 400, "renewal_date": "2026-09-30"},
    {"name": "Salesforce", "category": "crm", "base_cost": 3600, "renewal_date": "2026-12-15"},
    {"name": "HubSpot", "category": "crm", "base_cost": 1800, "renewal_date": "2027-02-01"},
    {"name": "Vercel", "category": "dev_tools", "base_cost": 500, "renewal_date": "2026-08-15"},
]

# --- Anomalies to plant (ground truth for eval) ---
PLANTED_ANOMALIES = [
    {
        "id": "ANOM-001",
        "type": "spend_spike",
        "vendor": "OpenAI API",
        "description": "4x cost spike in March 2026 due to unmonitored batch job",
        "month": "2026-03",
        "multiplier": 4.0,
    },
    {
        "id": "ANOM-002",
        "type": "duplicate_tools",
        "vendors": ["Notion", "Asana", "Jira"],
        "description": "Three overlapping project management tools",
    },
    {
        "id": "ANOM-003",
        "type": "upcoming_renewal",
        "vendor": "GitHub Enterprise",
        "description": "Renewal in 11 days - needs review",
        "renewal_date": "2026-07-01",
    },
    {
        "id": "ANOM-004",
        "type": "spend_spike",
        "vendor": "AWS",
        "description": "Steady 15% month-over-month increase over 3 months",
        "months": ["2026-01", "2026-02", "2026-03"],
        "multipliers": [1.0, 1.15, 1.32],
    },
    {
        "id": "ANOM-005",
        "type": "duplicate_tools",
        "vendors": ["Salesforce", "HubSpot"],
        "description": "Two CRM tools with overlapping functionality",
    },
    {
        "id": "ANOM-006",
        "type": "upcoming_renewal",
        "vendor": "Slack",
        "description": "Renewal in 25 days",
        "renewal_date": "2026-07-15",
    },
    {
        "id": "ANOM-007",
        "type": "spend_spike",
        "vendor": "Anthropic API",
        "description": "2.5x spike in February 2026",
        "month": "2026-02",
        "multiplier": 2.5,
    },
]


def create_database():
    """Create SQLite database with schema for invoices, usage, and contracts."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("DROP TABLE IF EXISTS invoices")
    c.execute("DROP TABLE IF EXISTS usage_records")
    c.execute("DROP TABLE IF EXISTS contracts")
    c.execute("DROP TABLE IF EXISTS vendor_history")
    c.execute("DROP TABLE IF EXISTS anomaly_ground_truth")

    c.execute("""
        CREATE TABLE invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'USD',
            period TEXT NOT NULL,
            invoice_date TEXT NOT NULL,
            description TEXT
        )
    """)

    c.execute("""
        CREATE TABLE usage_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT NOT NULL,
            category TEXT NOT NULL,
            period TEXT NOT NULL,
            tokens_used INTEGER,
            api_calls INTEGER,
            compute_hours REAL,
            estimated_cost REAL
        )
    """)

    c.execute("""
        CREATE TABLE contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor TEXT NOT NULL,
            category TEXT NOT NULL,
            tier TEXT DEFAULT 'standard',
            monthly_cost REAL,
            renewal_date TEXT,
            contract_terms TEXT,
            cancellation_notice_days INTEGER DEFAULT 30
        )
    """)

    c.execute("""
        CREATE TABLE vendor_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor TEXT NOT NULL,
            period TEXT NOT NULL,
            amount REAL NOT NULL,
            recommendation TEXT,
            recommendation_date TEXT
        )
    """)

    c.execute("""
        CREATE TABLE anomaly_ground_truth (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            vendor TEXT,
            vendors TEXT,
            description TEXT NOT NULL,
            severity TEXT DEFAULT 'medium'
        )
    """)

    conn.commit()
    return conn


def generate_invoices(conn):
    """Generate 6 months of invoices with planted anomalies."""
    c = conn.cursor()
    months = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]

    spike_map = {}
    for anom in PLANTED_ANOMALIES:
        if anom["type"] == "spend_spike":
            if "month" in anom:
                spike_map[(anom["vendor"], anom["month"])] = anom["multiplier"]
            elif "months" in anom:
                for m, mult in zip(anom["months"], anom["multipliers"]):
                    spike_map[(anom["vendor"], m)] = mult

    for vendor in VENDORS:
        for month in months:
            base = vendor["base_cost"]
            noise = random.uniform(0.95, 1.05)
            amount = base * noise

            key = (vendor["name"], month)
            if key in spike_map:
                amount = base * spike_map[key]

            invoice_date = f"{month}-{random.randint(1, 28):02d}"
            c.execute(
                "INSERT INTO invoices (vendor, category, amount, period, invoice_date, description) VALUES (?, ?, ?, ?, ?, ?)",
                (vendor["name"], vendor["category"], round(amount, 2), month, invoice_date,
                 f"Monthly subscription - {vendor['name']}"),
            )

    conn.commit()


def generate_usage(conn):
    """Generate API/LLM usage records."""
    c = conn.cursor()
    months = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]

    llm_vendors = [v for v in VENDORS if v["category"] == "llm_api"]
    cloud_vendors = [v for v in VENDORS if v["category"] == "cloud_infra"]

    for vendor in llm_vendors:
        for month in months:
            base_tokens = random.randint(800_000, 1_200_000)
            base_calls = random.randint(5_000, 15_000)

            multiplier = 1.0
            for anom in PLANTED_ANOMALIES:
                if anom["type"] == "spend_spike" and anom.get("vendor") == vendor["name"]:
                    if anom.get("month") == month:
                        multiplier = anom["multiplier"]

            tokens = int(base_tokens * multiplier)
            calls = int(base_calls * multiplier)
            cost = round(tokens * 0.001 * random.uniform(0.8, 1.2), 2)

            c.execute(
                "INSERT INTO usage_records (service, category, period, tokens_used, api_calls, estimated_cost) VALUES (?, ?, ?, ?, ?, ?)",
                (vendor["name"], vendor["category"], month, tokens, calls, cost),
            )

    for vendor in cloud_vendors:
        for month in months:
            hours = round(random.uniform(500, 2000), 1)
            cost = round(hours * random.uniform(0.5, 2.0), 2)
            c.execute(
                "INSERT INTO usage_records (service, category, period, tokens_used, api_calls, compute_hours, estimated_cost) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (vendor["name"], vendor["category"], month, None, None, hours, cost),
            )

    conn.commit()


def generate_contracts(conn):
    """Generate contract records for each vendor."""
    c = conn.cursor()

    tiers = {
        "Slack": ("Business+", "Annual commitment, 30-day cancellation notice"),
        "Notion": ("Team", "Annual, auto-renews, 60-day cancellation notice"),
        "Asana": ("Business", "Annual, auto-renews, 30-day cancellation notice"),
        "GitHub Enterprise": ("Enterprise", "Annual, includes advanced security, 90-day notice"),
        "Datadog": ("Pro", "Annual commitment, usage-based overages, 30-day notice"),
        "AWS": ("Enterprise Support", "Month-to-month with reserved instances, no fixed term"),
        "GCP": ("Premium", "Committed use discount, 1-year term, 30-day notice"),
        "Figma": ("Professional", "Annual, per-editor pricing, 30-day notice"),
        "Jira": ("Premium", "Annual, includes advanced roadmaps, 30-day notice"),
        "OpenAI API": ("Tier 4", "Pay-as-you-go, no contract, rate limits apply"),
        "Anthropic API": ("Scale", "Pay-as-you-go, no contract, rate limits apply"),
        "Zoom": ("Business", "Annual, 30-day cancellation notice"),
        "Salesforce": ("Enterprise", "Annual, multi-year discount available, 60-day notice"),
        "HubSpot": ("Professional", "Annual, includes CRM + Marketing Hub, 30-day notice"),
        "Vercel": ("Pro", "Monthly, per-member pricing, cancel anytime"),
    }

    for vendor in VENDORS:
        tier, terms = tiers.get(vendor["name"], ("Standard", "Standard terms"))
        notice_days = 30
        if "60-day" in terms:
            notice_days = 60
        elif "90-day" in terms:
            notice_days = 90

        c.execute(
            "INSERT INTO contracts (vendor, category, tier, monthly_cost, renewal_date, contract_terms, cancellation_notice_days) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (vendor["name"], vendor["category"], tier, vendor["base_cost"],
             vendor.get("renewal_date"), terms, notice_days),
        )

    conn.commit()


def store_ground_truth(conn):
    """Store anomaly ground truth for eval harness (Day 4: evaluation)."""
    c = conn.cursor()

    for anom in PLANTED_ANOMALIES:
        vendors_str = json.dumps(anom.get("vendors")) if "vendors" in anom else None
        severity = "high" if anom["type"] == "spend_spike" and anom.get("multiplier", 1) > 3 else "medium"

        c.execute(
            "INSERT INTO anomaly_ground_truth (id, type, vendor, vendors, description, severity) VALUES (?, ?, ?, ?, ?, ?)",
            (anom["id"], anom["type"], anom.get("vendor"), vendors_str, anom["description"], severity),
        )

    conn.commit()


def main():
    """Generate all synthetic data."""
    print("Generating AgentLedger synthetic data...")
    conn = create_database()
    generate_invoices(conn)
    generate_usage(conn)
    generate_contracts(conn)
    store_ground_truth(conn)

    # Summary
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM invoices")
    print(f"  Invoices: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM usage_records")
    print(f"  Usage records: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM contracts")
    print(f"  Contracts: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM anomaly_ground_truth")
    print(f"  Planted anomalies: {c.fetchone()[0]}")

    conn.close()
    print(f"Database saved to: {DB_PATH}")
    print("Done!")


if __name__ == "__main__":
    main()
