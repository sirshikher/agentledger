# AgentLedger

**Autonomous SaaS Cost & Vendor Renewal Manager**

> Kaggle 5-Day AI Agents Intensive Vibecoding Course — Capstone Project
> Category: **Agents for Business**

AgentLedger is a multi-agent system built with Google ADK and Gemini that ingests SaaS invoices and API/LLM usage data, flags spend anomalies and forgotten renewals, drafts negotiation-ready recommendations, and produces executive summaries — all fully instrumented with production-grade observability.

## Quick Start

```bash
# 1. Clone and enter the project
git clone https://github.com/YOUR_USERNAME/agentledger.git
cd agentledger

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API key
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY from AI Studio

# 5. Generate synthetic data
python -m scripts.generate_data

# 6. Run the demo
python main.py

# 7. Run evaluation harness
python main.py --eval
```

## Architecture

```
                 ┌─────────────────────┐
                 │  Orchestrator Agent  │  ADK root agent
                 │  (routes + sequences)│  Day 1: hierarchical pattern
                 └──────────┬──────────┘
        ┌─────────────┬─────┴────────┬──────────────┐
        ▼             ▼              ▼              ▼
 ┌────────────┐ ┌───────────┐ ┌────────────┐ ┌────────────┐
 │ Ingestion  │ │ Anomaly   │ │Negotiation │ │ Reporting  │
 │  Agent     │ │  Agent    │ │ -Prep Agent│ │  Agent     │
 │            │ │           │ │            │ │            │
 │ Day 2:     │ │ Day 1:    │ │ Day 1:     │ │ Day 3:     │
 │ custom     │ │ agent     │ │ constrained│ │ persistent │
 │ tools      │ │ skills    │ │ data scope │ │ memory     │
 └─────┬──────┘ └─────┬─────┘ └─────┬──────┘ └─────┬──────┘
       │              │             │              │
       ▼              ▼             ▼              ▼
   MCP Server     Deterministic  Contract RAG   Exec Summary
   (Day 2)        + LLM Judge    + HITL Gate    + Savings
                  (Day 4)        (Day 2)        Report
```

## Project Structure

```
agentledger/
├── main.py                    # Demo runner + HITL gate
├── config.py                  # Central configuration
├── requirements.txt           # Dependencies
├── .env.example               # API key template
│
├── agents/                    # ADK agent definitions
│   ├── agent_definitions.py   # Agent classes with tools
│   └── prompts.py             # System instructions
│
├── tools/                     # Agent tools (Day 2)
│   └── agent_tools.py         # Custom tool functions + anomaly skill
│
├── mcp_server/                # MCP server (Day 2)
│   └── server.py              # FastMCP server over SQLite
│
├── observability/             # Day 4 differentiator
│   └── tracer.py              # Logs, Traces, Metrics
│
├── eval/                      # Day 4 evaluation
│   └── eval_harness.py        # Precision/recall + LLM-as-Judge
│
├── scripts/                   # Utilities
│   └── generate_data.py       # Synthetic data generator
│
└── data/                      # Generated data (gitignored)
    └── agentledger.db         # SQLite database
```

## Course Concepts Demonstrated

| # | Concept | Day | Implementation |
|---|---------|-----|---------------|
| 1 | Multi-agent system (ADK) | 1 | 4 specialist agents + Orchestrator |
| 2 | Agent architectural patterns | 1 | Sequential hierarchical pipeline |
| 3 | AgentOps / security scoping | 1 | Constrained data per agent identity |
| 4 | Agent skills | 1 | Reusable anomaly detection skill |
| 5 | Custom tool functions | 2 | 5+ native Python tools |
| 6 | MCP server | 2 | FastMCP server over SQLite billing store |
| 7 | HITL long-running operation | 2 | Email approval gate with pause/resume |
| 8 | ADK session state | 3 | Intra-run state management |
| 9 | Long-term memory | 3 | Cross-session SQLite vendor history |
| 10 | Context engineering | 3 | Curated context slices per agent |
| 11 | Logs | 4 | Per-step structured agent diary |
| 12 | Traces | 4 | Full causal run trace with latency |
| 13 | Metrics | 4 | Cost/latency/detection dashboard |
| 14 | LLM-as-a-Judge | 4 | Recommendation quality scorer |
| 15 | Eval harness | 4 | Precision/recall on 7 planted anomalies |
| 16 | Production governance | 5 | Audit trail + HITL + data scoping |

## Demo Walkthrough

1. **User asks:** "Review our SaaS spend for the last quarter"
2. **Ingestion Agent** pulls 90 invoices + usage records via tools
3. **Anomaly Agent** flags:
   - 4× OpenAI API spend spike ($1,200 → $4,800)
   - 3 overlapping project management tools (Notion + Asana + Jira)
   - GitHub Enterprise renewal in 11 days
   - AWS 3-month upward spend trend
4. **Negotiation-Prep Agent** drafts:
   - Cancel Jira ($480/mo saved), consolidate to Notion
   - Downgrade OpenAI tier, add usage alerts
   - Renegotiate GitHub Enterprise before renewal
5. **HITL Gate:** User approves/rejects each recommendation
6. **Reporting Agent** outputs executive summary: "$X/yr in identified savings"
7. **Observability Dashboard** shows full trace, logs, and metrics

## Running the MCP Server (Optional)

```bash
# In a separate terminal
python -m mcp_server.server

# The MCP server exposes:
#   - get_invoices(vendor?, period?)
#   - get_usage(service?, period?)
#   - get_contract(vendor)
```

## Evaluation

```bash
# Run the eval harness
python main.py --eval

# This tests:
# - Detection precision/recall against 7 planted anomalies
# - LLM-as-Judge scoring on recommendation quality
# - Cost-per-run metrics
```

## Tech Stack

- **Agent Framework:** Google ADK (Agent Development Kit)
- **LLM:** Gemini 2.0 Flash
- **MCP:** FastMCP Python server
- **Data:** SQLite with synthetic billing data
- **Observability:** Custom tracer inspired by OpenTelemetry
- **Display:** Rich terminal formatting
- **Eval:** Custom harness with LLM-as-Judge

## License

CC-BY 4.0 (per competition requirements)
