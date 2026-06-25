"""
AgentLedger Run-Record Builder
================================
Assembles a single, self-contained JSON-serializable dict describing one
pipeline run, for the Phase 2 demo dashboard to render.

Design principle: every field is pulled from a reliable structured source
(deterministic detection tools, the vendor_history table, the tracer) rather
than parsed out of free-form LLM prose. See docs/PHASE_1_RUN_EXPORT.md.
"""

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from config import SPEND_SPIKE_THRESHOLD, RENEWAL_WARNING_DAYS
from tools.agent_tools import (
    fetch_all_invoices,
    fetch_all_contracts,
    detect_spend_spikes,
    detect_duplicate_tools,
    detect_upcoming_renewals,
)
from eval.eval_harness import (
    evaluate_detection,
    load_ground_truth,
    llm_judge_recommendation,
)

SCHEMA_VERSION = "1.0"


def get_vendor_history_max_id(db_path: Path) -> int:
    """Snapshot the current max vendor_history id, to isolate this run's recs."""
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM vendor_history").fetchone()
    conn.close()
    return row[0]


def get_recommendations_since(db_path: Path, since_id: int) -> list[dict]:
    """Fetch vendor_history rows created after the given id (this run's recs)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM vendor_history WHERE id > ? ORDER BY id", (since_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_dataset_counts(db_path: Path) -> dict:
    """Count rows in each source table for the dataset summary."""
    conn = sqlite3.connect(db_path)
    counts = {}
    for table, key in [
        ("invoices", "invoices"),
        ("usage_records", "usage_records"),
        ("contracts", "contracts"),
    ]:
        counts[key] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.close()
    return counts


def _parse_recommendation_fields(text: str) -> dict:
    """
    Best-effort line-based parse of the negotiation agent's enforced output
    format (Action / Estimated Annual Savings / Draft Email). Raw text is
    always preserved by the caller regardless of parse success.
    """
    action = ""
    savings = 0.0
    draft_email = ""

    action_match = re.search(r"Action:\s*([A-Z]+)", text)
    if action_match:
        action = action_match.group(1)

    savings_match = re.search(r"Estimated Annual Savings:\s*\$?([\d,]+(?:\.\d+)?)", text)
    if savings_match:
        try:
            savings = float(savings_match.group(1).replace(",", ""))
        except ValueError:
            savings = 0.0

    email_match = re.search(
        r"Draft Email:\s*(.*?)(?:\nRisk:|\Z)", text, re.DOTALL
    )
    if email_match:
        candidate = email_match.group(1).strip()
        if candidate and candidate.upper() not in ("N/A", "NONE", "-"):
            draft_email = candidate

    return {
        "action": action,
        "annual_savings_usd": savings,
        "draft_email": draft_email,
    }


def build_anomalies(db_path: Path) -> list[dict]:
    """Re-run the deterministic detection tools to populate anomalies (reproducible)."""
    invoices = fetch_all_invoices()
    contracts = fetch_all_contracts()

    spikes = detect_spend_spikes(invoices)
    duplicates = detect_duplicate_tools(contracts)
    renewals = detect_upcoming_renewals(contracts)

    import json
    return (
        json.loads(spikes) + json.loads(duplicates) + json.loads(renewals)
    )


async def build_run_record(
    *,
    query: str,
    mode: str,
    results: dict,
    tracer,
    db_path: Path,
    recommendations: list[dict],
    run_evaluation: bool = True,
) -> dict:
    """
    Assemble the full run-record dict for export.

    Args:
        query: The user query that drove this run.
        mode: "live" or "replay".
        results: The dict returned by run_agent_pipeline (all_agent_outputs, etc).
        tracer: The Tracer instance for this run.
        db_path: Path to the SQLite database.
        recommendations: vendor_history rows created during this run
            (see get_vendor_history_max_id / get_recommendations_since).
        run_evaluation: Whether to compute detection metrics + LLM-judge scores.

    Returns:
        A JSON-serializable dict conforming to schema v1.0.
    """
    anomalies = build_anomalies(db_path)

    parsed_recs = []
    for rec in recommendations:
        parsed = _parse_recommendation_fields(rec.get("recommendation", ""))
        parsed_recs.append({
            "vendor": rec.get("vendor", ""),
            "period": rec.get("period", ""),
            "action": parsed["action"],
            "annual_savings_usd": parsed["annual_savings_usd"],
            "recommendation_text": rec.get("recommendation", ""),
            "draft_email": parsed["draft_email"],
            "saved_at": rec.get("recommendation_date", ""),
        })

    total_savings = round(sum(r["annual_savings_usd"] for r in parsed_recs), 2)

    pipeline_agents = []
    for order, output in enumerate(results.get("all_agent_outputs", []), start=1):
        pipeline_agents.append({
            "name": output["agent"],
            "order": order,
            "status": "ok",
            "output_text": output["text"],
            "tokens_in": output.get("tokens_in", 0),
            "tokens_out": output.get("tokens_out", 0),
        })

    evaluation = {}
    if run_evaluation:
        ground_truth = load_ground_truth()
        detection_result = evaluate_detection(anomalies, ground_truth)

        judge_scores = {}
        for rec in parsed_recs:
            score = await llm_judge_recommendation(rec["recommendation_text"], rec["vendor"])
            judge_scores[rec["vendor"]] = score
        avg_judge = (
            round(sum(judge_scores.values()) / len(judge_scores), 2)
            if judge_scores else 0.0
        )

        evaluation = {
            "detection": {
                "precision": round(detection_result.precision, 3),
                "recall": round(detection_result.recall, 3),
                "f1": round(detection_result.f1, 3),
                "true_positives": detection_result.true_positives,
                "false_positives": detection_result.false_positives,
                "false_negatives": detection_result.false_negatives,
            },
            "judge": {
                "average_score": avg_judge,
                "scores": judge_scores,
            },
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": tracer.run_id,
        "captured_at": datetime.now().isoformat(),
        "mode": mode,
        "query": query,
        "dataset": {
            "source": "synthetic",
            **get_dataset_counts(db_path),
        },
        "pipeline": {"agents": pipeline_agents},
        "anomalies": anomalies,
        "recommendations": parsed_recs,
        "hitl": {
            "requested": tracer.metrics.approvals_requested > 0,
            "granted": (
                True if tracer.metrics.approvals_granted > 0
                else False if tracer.metrics.approvals_rejected > 0
                else None
            ),
        },
        "trace": {"root": tracer.serialize_span()},
        "logs": tracer.serialize_logs(),
        "metrics": tracer.serialize_metrics(),
        "evaluation": evaluation,
        "totals": {"identified_annual_savings_usd": total_savings},
    }
