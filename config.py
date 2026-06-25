"""
AgentLedger Configuration
========================
Central config for all agents, tools, and observability settings.
Maps to: Day 1 (AgentOps discipline), Day 5 (production governance)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Paths ---
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "agentledger.db")))

# --- Gemini ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_MODEL_JUDGE = os.getenv("GEMINI_MODEL_JUDGE", "gemini-2.0-flash")

# --- Agent Names (Day 1: Agent taxonomy) ---
ORCHESTRATOR_NAME = "orchestrator"
INGESTION_AGENT_NAME = "ingestion_agent"
ANOMALY_AGENT_NAME = "anomaly_agent"
NEGOTIATION_AGENT_NAME = "negotiation_agent"
REPORTING_AGENT_NAME = "reporting_agent"

# --- Anomaly Detection Thresholds (Day 4: deterministic + LLM) ---
SPEND_SPIKE_THRESHOLD = 0.30  # 30% increase month-over-month
RENEWAL_WARNING_DAYS = 30     # flag renewals within 30 days
OVERLAP_SIMILARITY = 0.8      # category overlap threshold

# --- Observability (Day 4: Logs, Traces, Metrics) ---
TRACE_ENABLED = True
LOG_LEVEL = "INFO"

# --- MCP Server (Day 2: MCP architecture) ---
MCP_SERVER_HOST = "localhost"
MCP_SERVER_PORT = 8765
