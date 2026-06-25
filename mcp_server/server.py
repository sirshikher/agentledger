"""
AgentLedger MCP Server
=======================
A real MCP server (Day 2: MCP architecture) exposing billing tools over SQLite.
Demonstrates: server → transport → client architecture, tool discovery.

Exposes three tools:
  - get_invoices:  Retrieve invoices filtered by vendor and/or period
  - get_usage:     Retrieve API/LLM usage records
  - get_contract:  Retrieve vendor contract details for negotiation RAG

Run standalone:
    python -m mcp_server.server

Or connect from ADK agent via MCP client.
"""

import json
import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Resolve DB path relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "agentledger.db"

mcp_server = FastMCP(
    "AgentLedger Billing Server",
    instructions=(
        "MCP server for AgentLedger. Provides access to SaaS invoices, "
        "API/LLM usage records, and vendor contracts for cost analysis."
    ),
)


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@mcp_server.tool()
def get_invoices(vendor: str | None = None, period: str | None = None) -> str:
    """
    Retrieve SaaS invoices from the billing store.

    Args:
        vendor: Filter by vendor name (e.g., "Slack", "AWS"). None for all.
        period: Filter by billing period in YYYY-MM format. None for all.

    Returns:
        JSON array of invoice records with vendor, category, amount, period.
    """
    conn = _get_db()
    query = "SELECT vendor, category, amount, currency, period, invoice_date, description FROM invoices WHERE 1=1"
    params = []

    if vendor:
        query += " AND vendor = ?"
        params.append(vendor)
    if period:
        query += " AND period = ?"
        params.append(period)

    query += " ORDER BY period DESC, vendor ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = [dict(r) for r in rows]
    return json.dumps(results, indent=2)


@mcp_server.tool()
def get_usage(service: str | None = None, period: str | None = None) -> str:
    """
    Retrieve API and LLM usage records.

    Args:
        service: Filter by service name (e.g., "OpenAI API"). None for all.
        period: Filter by period in YYYY-MM format. None for all.

    Returns:
        JSON array of usage records with tokens, API calls, compute hours, cost.
    """
    conn = _get_db()
    query = "SELECT service, category, period, tokens_used, api_calls, compute_hours, estimated_cost FROM usage_records WHERE 1=1"
    params = []

    if service:
        query += " AND service = ?"
        params.append(service)
    if period:
        query += " AND period = ?"
        params.append(period)

    query += " ORDER BY period DESC, service ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = [dict(r) for r in rows]
    return json.dumps(results, indent=2)


@mcp_server.tool()
def get_contract(vendor: str) -> str:
    """
    Retrieve contract details for a specific vendor.
    Used by the Negotiation-Prep agent for RAG over contract terms.

    Args:
        vendor: Vendor name (e.g., "GitHub Enterprise").

    Returns:
        JSON object with tier, monthly cost, renewal date, terms, notice period.
    """
    conn = _get_db()
    row = conn.execute(
        "SELECT vendor, category, tier, monthly_cost, renewal_date, contract_terms, cancellation_notice_days FROM contracts WHERE vendor = ?",
        (vendor,),
    ).fetchone()
    conn.close()

    if row:
        return json.dumps(dict(row), indent=2)
    return json.dumps({"error": f"No contract found for vendor: {vendor}"})


if __name__ == "__main__":
    mcp_server.run(transport="stdio")
