# Phase 1 — Run-Record Export

> Foundation for the AgentLedger demo UI. This phase makes every pipeline run
> emit a single self-contained JSON file that the Streamlit dashboard (Phase 2)
> renders. No agent architecture changes — this is a pure instrumentation +
> serialization layer wrapped around the existing, working pipeline.

---

## 1. Purpose & context

The current pipeline prints to a Rich terminal and discards everything when the
process exits. To build a visual demo that is **fast, reliable, and free to run
publicly**, we decouple the (slow, token-costing, occasionally-flaky) live agent
run from the presentation layer:

```
  live agent run  ──►  run-record.json  ──►  Streamlit dashboard
   (once, captured)     (committed)          (renders instantly, $0)
```

A "golden run" JSON committed to the repo guarantees the hosted demo always has
something polished to show, even with no API key present.

---

## 2. Goals / non-goals

### Goals
1. Define a stable, versioned **run-record JSON schema** capturing everything the
   UI needs: query, per-agent narrative, anomalies, recommendations, HITL outcome,
   trace tree, logs, metrics, and evaluation scores.
2. Add a **run-record builder** that assembles this from reliable structured
   sources (detection tools + DB + tracer), not by parsing LLM prose.
3. Replace the **estimated token count** (`len(text.split()) * 2`) with **real
   token usage** from `event.usage_metadata`.
4. Capture **1–2 golden runs** and commit them.
5. Keep all changes **additive and non-invasive** — default `python main.py`
   behavior is unchanged; export is opt-in via a flag.

### Non-goals (deferred to later phases)
- The Streamlit app, layout, animations (Phase 2).
- CSV upload + column mapping + session isolation (Phase 2.5).
- Deployment to Streamlit Community Cloud (Phase 3).
- Live in-browser streaming of agent events (Phase 2 / live toggle).

---

## 3. Run-record JSON schema (v1.0)

```jsonc
{
  "schema_version": "1.0",
  "run_id": "run_2e7a7bf3",
  "captured_at": "2026-06-25T01:30:00",
  "mode": "live",                       // "live" | "replay"
  "query": "Review our SaaS spend for the last quarter...",

  "dataset": {
    "source": "synthetic",             // "synthetic" | "upload"
    "invoices": 60,
    "usage_records": 24,
    "contracts": 15
  },

  "pipeline": {
    "agents": [
      {
        "name": "ingestion_agent",
        "order": 1,
        "status": "ok",
        "tool_calls": ["fetch_all_invoices", "fetch_all_usage", "fetch_all_contracts"],
        "output_text": "**Ingestion Summary** ...",   // full agent narrative
        "tokens_in": 650,
        "tokens_out": 120,
        "duration_ms": 4200
      }
      // ... one entry per agent that produced output, in execution order
    ]
  },

  "anomalies": [
    {
      "type": "spend_spike",
      "vendor": "OpenAI API",
      "severity": "high",
      "previous_amount": 1200.0,
      "current_amount": 4800.0,
      "change_pct": 300.0,
      "period": "2026-02",
      "previous_period": "2026-01"
    },
    {
      "type": "duplicate_tools",
      "category": "project_mgmt",
      "vendors": ["Notion", "Asana", "Jira"],
      "total_monthly_cost": 1340.0,
      "severity": "medium"
    },
    {
      "type": "upcoming_renewal",
      "vendor": "GitHub Enterprise",
      "renewal_date": "2026-07-01",
      "days_until_renewal": 11,
      "monthly_cost": 1900.0,
      "cancellation_notice_days": 30,
      "severity": "high"
    }
    // anomalies are emitted verbatim from the detect_* tools (structured already)
  ],

  "recommendations": [
    {
      "vendor": "Jira",
      "period": "2026-Q1",
      "action": "CONSOLIDATE",          // best-effort parse from text (see 5.3)
      "annual_savings_usd": 5760.0,      // best-effort parse from text
      "recommendation_text": "Action: CONSOLIDATE\nVendor: Jira...",  // always raw
      "draft_email": "Subject: ...",     // best-effort extract; "" if none
      "saved_at": "2026-06-25T01:29:55"
    }
    // captured for THIS run only (see 5.2)
  ],

  "hitl": {
    "requested": true,
    "granted": null                      // null when --no-hitl; true/false interactive
  },

  "trace": {
    "root": {
      "span_id": "orchestrator_full_pipeline_0",
      "agent_name": "orchestrator",
      "operation": "full_pipeline",
      "duration_ms": 11033,
      "tokens_in": 0,
      "tokens_out": 0,
      "status": "ok",
      "children": [ /* recursive TraceSpan */ ]
    }
  },

  "logs": [
    {
      "t_offset_s": 0.0,
      "agent": "ingestion_agent",
      "action": "tool_call:fetch_all_invoices",
      "tools": ["fetch_all_invoices"],
      "tokens": 0,
      "output": "Called fetch_all_invoices"
    }
    // flattened from tracer.logs
  ],

  "metrics": {
    "total_duration_ms": 11033,
    "total_tokens": 4210,
    "total_cost_usd": 0.0123,
    "agents_invoked": 5,
    "tool_calls_made": 9,
    "anomalies_flagged": 7,
    "recommendations_made": 6,
    "approvals_requested": 1,
    "approvals_granted": 1,
    "approvals_rejected": 0
  },

  "evaluation": {
    "detection": {
      "precision": 0.818,
      "recall": 0.90,
      "f1": 0.857,
      "true_positives": ["spend_spike:OpenAI API", "..."],
      "false_positives": ["..."],
      "false_negatives": ["..."]
    },
    "judge": {
      "average_score": 4.88,
      "scores": { "Jira": 4.8, "Salesforce": 5.0, "GitHub Enterprise": 4.8 }
    }
  },

  "totals": {
    "identified_annual_savings_usd": 67200.0   // sum of parsed annual_savings
  }
}
```

---

## 4. Data-source mapping

Every field traces to a reliable source — this is what avoids brittle LLM parsing.

| Section | Source | Notes |
|---|---|---|
| `query`, `mode`, `captured_at` | passed into builder | — |
| `dataset.*` | `COUNT(*)` on `invoices` / `usage_records` / `contracts` | direct SQL |
| `pipeline.agents[]` | `results["all_agent_outputs"]` + per-agent token tally | already collected in `run_agent_pipeline` |
| `anomalies[]` | `detect_spend_spikes` / `detect_duplicate_tools` / `detect_upcoming_renewals` | **structured JSON already** — same calls as `run_eval_mode` |
| `recommendations[]` | `vendor_history` rows created during this run | id-snapshot diff (see 5.2) |
| `recommendations[].action / annual_savings / draft_email` | best-effort parse of `recommendation_text` | format is prompt-enforced; raw text always kept |
| `hitl` | `tracer.metrics.approvals_*` | — |
| `trace.root` | `tracer.root_span` (recursive) | new `serialize_span()` |
| `logs[]` | `tracer.logs` | new serializer |
| `metrics.*` | `tracer.metrics` | extends existing `to_dict()` |
| `evaluation.detection` | `evaluate_detection(...)` vs `load_ground_truth()` | reuses eval harness |
| `evaluation.judge` | `llm_judge_recommendation(...)` over this run's recs | adds ~N LLM calls during capture only |
| `totals.identified_annual_savings_usd` | sum of parsed `annual_savings_usd` | — |

---

## 5. Implementation design

### 5.1 New module: `observability/run_record.py`
A single function:

```python
def build_run_record(
    *, query, mode, results, tracer, db_path,
    recommendations, run_evaluation=True,
) -> dict: ...
```

- Pulls dataset counts via SQL.
- Reads `results["all_agent_outputs"]` for per-agent narrative + token tallies.
- Re-runs the deterministic `detect_*` tools to populate `anomalies` (identical
  to `run_eval_mode`, fully reproducible).
- Accepts the already-captured `recommendations` list (see 5.2).
- Calls `evaluate_detection` + (optionally) the LLM judge for `evaluation`.
- Serializes the tracer's span tree, logs, and metrics.
- Returns the dict; caller writes JSON.

Tracer gains additive helpers: `serialize_span(span) -> dict` and
`serialize_logs() -> list[dict]`. Existing `to_dict()` stays for backward compat.

### 5.2 Capturing "this run's" recommendations only
`vendor_history` accumulates across all runs. To isolate the current run:

1. Before the pipeline runs: `before_id = SELECT MAX(id) FROM vendor_history` (or 0).
2. After it completes: `SELECT * FROM vendor_history WHERE id > before_id ORDER BY id`.

Robust against concurrent rows and avoids fragile timestamp matching.

### 5.3 Best-effort structured fields from recommendation text
The negotiation prompt enforces lines like `Action: CONSOLIDATE`,
`Estimated Annual Savings: $5,760`, and a `Draft Email:` block. The builder does a
light, line-based parse to populate `action`, `annual_savings_usd`, and
`draft_email`. **The raw `recommendation_text` is always preserved**, so if a parse
misses, the UI can still render the full text. No hard dependency on parse success.

### 5.4 Real token usage (replaces the estimate)
In `run_agent_pipeline`'s event loop, when `event.usage_metadata` is present,
read `prompt_token_count`, `candidates_token_count`, `total_token_count` and
accumulate them per-agent and into the tracer. This replaces
`tokens_used=len(text.split()) * 2` at `main.py:145` with real counts, and
populates `tokens_in` / `tokens_out` on spans and pipeline-agent entries.

> Note: `usage_metadata` is only populated on model-response events (not on every
> partial/tool event). The builder accumulates whenever present and treats absent
> values as 0 — totals reflect the sum of all reported model turns.

### 5.5 main.py hook (opt-in, non-invasive)
Add a CLI flag `--export PATH`. When set, after `tracer.finalize()`:

```python
record = build_run_record(query=..., mode="live", results=results,
                          tracer=tracer, db_path=DB_PATH,
                          recommendations=captured_recs)
Path(args.export).write_text(json.dumps(record, indent=2, default=str))
```

When `--export` is absent, behavior is byte-for-byte unchanged.

---

## 6. Golden run capture

```bash
# Reproducible non-interactive capture of the headline scenario
python main.py --no-hitl --export runs/golden_q1_review.json
```

- Commit `runs/golden_q1_review.json` (and optionally a second scenario).
- `.gitignore`: add `runs/*.json` then force-add the golden file(s), so ad-hoc
  local captures aren't accidentally committed but goldens are tracked.

---

## 7. File / directory changes

| Path | Change | Invasive? |
|---|---|---|
| `observability/run_record.py` | **new** — `build_run_record()` | no (new file) |
| `observability/tracer.py` | **additive** — `serialize_span()`, `serialize_logs()` | no (existing API kept) |
| `main.py` | **additive** — real token capture, `--export` flag + write | no (default path unchanged) |
| `runs/golden_q1_review.json` | **new** — committed golden run | no |
| `.gitignore` | add `runs/*.json` + golden exception | no |
| `docs/PHASE_1_RUN_EXPORT.md` | **new** — this doc | no |

**Untouched (locked scope):** `agents/agent_definitions.py`, `agents/prompts.py`,
`tools/agent_tools.py`, `mcp_server/server.py`, `config.py`, `eval/eval_harness.py`.

---

## 8. Acceptance criteria

1. `python main.py --no-hitl --export runs/golden_q1_review.json` writes a valid
   JSON file conforming to the v1.0 schema.
2. `anomalies` is non-empty (≈7 items) and `recommendations` reflects only the
   current run.
3. `metrics.total_tokens > 0` and derives from real `usage_metadata`, not the
   word-count estimate.
4. `evaluation.detection` shows the expected P/R/F1 (~0.818 / 0.90 / 0.857) and
   `evaluation.judge.average_score` is populated.
5. `totals.identified_annual_savings_usd` is a sensible positive number.
6. Plain `python main.py` and `python main.py --eval` behave exactly as before
   (no regression).
7. The JSON loads cleanly with `json.load` and round-trips (no non-serializable
   objects; `default=str` covers timestamps).

---

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| `usage_metadata` absent on some events | Accumulate when present; treat missing as 0; document totals semantics |
| Recommendation text parse misses a field | Best-effort only; raw `recommendation_text` always retained for UI |
| Judge calls add latency/token cost to capture | Only runs during golden capture; can pass `run_evaluation=False` for quick captures |
| Span-tree recursion on malformed tree | Defensive serialize with cycle guard / depth cap |
| Concurrent `vendor_history` writes | id-snapshot diff is concurrency-safe |

---

## 10. Out of scope (next phases)

- **Phase 2** — Streamlit dashboard rendering this JSON (hero, pipeline animation,
  anomaly cards, HITL card, observability + eval strip).
- **Phase 2.5** — CSV/Excel upload, column mapping, session-isolated temp DB.
- **Phase 3** — Streamlit Community Cloud deployment (replay-only public default;
  live toggle behind a key/password).
```
