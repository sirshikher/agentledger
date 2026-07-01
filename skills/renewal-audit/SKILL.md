---
name: renewal-audit
description: >
  Run a fast, deterministic SaaS cost audit over the AgentLedger billing store —
  upcoming contract renewals, duplicate tools, and month-over-month spend spikes.
  Use this when an operator (or an agent) wants a quick terminal report before a
  billing cycle, without spinning up the full multi-agent pipeline or spending
  any LLM tokens.
metadata:
  type: skill
  surface: terminal-sandbox
  cost: $0 (no LLM calls — deterministic detection only)
---

# renewal-audit

A **playbook + script** that an operator or agent can run in a terminal sandbox.
It reuses AgentLedger's deterministic detection layer (the same tools the live
Anomaly Agent uses) to surface time-sensitive cost findings — fast, repeatable,
and free.

## When to use this skill

Reach for `renewal-audit` when you want:

- A **pre-billing-cycle check** — "what renews soon and what's overlapping?"
- A **zero-cost sanity pass** before committing to a full agent run.
- A scriptable hook for **CI / a cron job** that flags renewals weekly.

Do **not** use this for drafting recommendations or vendor emails — that's the
Negotiation Agent's job in the full pipeline. This skill only *detects*.

## What it checks

1. **Upcoming renewals** — contracts renewing inside the warning window, with
   days-until-renewal and monthly cost.
2. **Duplicate tools** — multiple vendors in the same category (e.g. three
   project-management tools) and the monthly dollars at stake.
3. **Spend spikes** — month-over-month invoice increases over the threshold.

## How to run it

From the project root, in a terminal:

```bash
# Full audit — renewals + duplicates + spikes
python skills/renewal-audit/audit.py

# Only the time-critical renewals
python skills/renewal-audit/audit.py --renewals-only

# Audit as if "today" were a specific date (useful for demos / tests)
python skills/renewal-audit/audit.py --as-of 2025-03-01
```

### Expected output

A plain-text, section-by-section report:

```
AgentLedger · renewal-audit skill

────────────────────────────────────────────────────────────
UPCOMING RENEWALS
────────────────────────────────────────────────────────────
  • GitHub Enterprise     renews 2025-03-12 (11 days) · $2,100/mo
  ...
────────────────────────────────────────────────────────────
SUMMARY
────────────────────────────────────────────────────────────
  N finding(s). Review the items above before the next billing cycle.
```

## Prerequisites

- The billing store exists (`python -m scripts.generate_data` if `data/agentledger.db`
  is missing).
- No API key required — this skill makes **no LLM calls**.

## How it stays consistent with the agents

The script imports the detection functions from `tools/agent_tools.py` directly —
it does not copy or fork the logic. So a finding from this skill is, by
construction, the same finding the Anomaly Agent would produce. The skill is a
lightweight terminal entry-point to a capability the system already has.
