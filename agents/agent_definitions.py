"""
AgentLedger Agent Definitions
===============================
Multi-agent system built with Google ADK (Day 1: multi-agent architecture).
Sequential pipeline: Orchestrator → Ingestion → Anomaly → Negotiation → Reporting

Concepts demonstrated:
  - Day 1: Multi-agent ADK, agent taxonomy, architectural patterns
  - Day 2: Custom tools, MCP integration (ingestion_agent uses McpToolset)
  - Day 3: Session state, context engineering
  - Day 5: A2A-style structured delegation
"""

import sys
from pathlib import Path

from mcp import StdioServerParameters
from google.adk.agents import Agent, SequentialAgent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams

from config import GEMINI_MODEL
from agents.prompts import (
    ORCHESTRATOR_INSTRUCTION,
    INGESTION_AGENT_INSTRUCTION,
    ANOMALY_AGENT_INSTRUCTION,
    NEGOTIATION_AGENT_INSTRUCTION,
    REPORTING_AGENT_INSTRUCTION,
)
from tools.agent_tools import (
    # Ingestion — fetch_all_contracts has no MCP bulk equivalent; kept direct
    fetch_all_contracts,
    # Anomaly detection skill (Day 1: agent skills)
    detect_spend_spikes,
    detect_duplicate_tools,
    detect_upcoming_renewals,
    # Negotiation tools (Day 1: constrained data scoping)
    get_vendor_contract,
    get_vendor_spend_history,
    save_recommendation,
    # Memory tools (Day 3: persistent memory)
    get_past_recommendations,
)

# MCP toolset for ingestion: get_invoices + get_usage served by the AgentLedger
# billing MCP server over stdio (Day 2: MCP server → transport → client pattern).
_PROJECT_ROOT = Path(__file__).parent.parent
ingestion_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server.server"],
            cwd=str(_PROJECT_ROOT),
        ),
        timeout=10.0,
    ),
    tool_filter=["get_invoices", "get_usage"],
)


# ============================================================
# SUB-AGENTS (Day 1: specialized agent roles)
# ============================================================

ingestion_agent = Agent(
    name="ingestion_agent",
    model=GEMINI_MODEL,
    instruction=INGESTION_AGENT_INSTRUCTION,
    description="Gathers and normalizes billing data from invoices, usage records, and contracts.",
    tools=[
        ingestion_mcp_toolset,  # get_invoices + get_usage via MCP (Day 2)
        fetch_all_contracts,    # bulk contracts — no MCP equivalent; kept direct
    ],
)

anomaly_agent = Agent(
    name="anomaly_agent",
    model=GEMINI_MODEL,
    instruction=ANOMALY_AGENT_INSTRUCTION,
    description="Analyzes billing data to detect spend spikes, duplicate tools, and upcoming renewals.",
    tools=[
        detect_spend_spikes,
        detect_duplicate_tools,
        detect_upcoming_renewals,
    ],
)

negotiation_agent = Agent(
    name="negotiation_agent",
    model=GEMINI_MODEL,
    instruction=NEGOTIATION_AGENT_INSTRUCTION,
    description="Drafts actionable recommendations for each flagged anomaly with vendor-specific context.",
    tools=[
        get_vendor_contract,
        get_vendor_spend_history,
        save_recommendation,
    ],
)

reporting_agent = Agent(
    name="reporting_agent",
    model=GEMINI_MODEL,
    instruction=REPORTING_AGENT_INSTRUCTION,
    description="Compiles all findings into an executive summary with prioritized actions and savings.",
    tools=[
        get_past_recommendations,
    ],
)


# ============================================================
# ORCHESTRATOR (Day 1: hierarchical orchestration pattern)
# ============================================================
# Uses sub_agents for LLM-routed delegation.
# The orchestrator decides which agent to call and in what order.

root_agent = Agent(
    name="orchestrator",
    model=GEMINI_MODEL,
    instruction=ORCHESTRATOR_INSTRUCTION,
    description="Coordinates the AgentLedger pipeline: ingestion → anomaly detection → negotiation prep → reporting.",
    sub_agents=[
        ingestion_agent,
        anomaly_agent,
        negotiation_agent,
        reporting_agent,
    ],
)


# ============================================================
# ALTERNATIVE: Sequential Pipeline (Day 5: deterministic flow)
# ============================================================
# Uncomment to use a deterministic sequential flow instead
# of LLM-routed orchestration. Better for demos and eval.

# sequential_pipeline = SequentialAgent(
#     name="agentledger_pipeline",
#     description="Sequential AgentLedger pipeline for deterministic execution.",
#     sub_agents=[
#         ingestion_agent,
#         anomaly_agent,
#         negotiation_agent,
#         reporting_agent,
#     ],
# )
