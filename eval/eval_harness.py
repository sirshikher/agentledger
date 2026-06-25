"""
AgentLedger Evaluation Harness
================================
Implements Day 4 evaluation concepts:
  - Detection precision/recall against planted anomalies
  - LLM-as-a-Judge scoring for recommendation quality
  - HITL evaluation metrics (approval/rejection rates)
  - Cost-per-run tracking

Usage:
    python -m eval.eval_harness
"""

import json
import sqlite3
from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config import DB_PATH, GEMINI_MODEL_JUDGE, GOOGLE_API_KEY

console = Console()


@dataclass
class EvalResult:
    """Results from a single evaluation run."""
    # Detection metrics
    true_positives: list[str] = field(default_factory=list)
    false_positives: list[str] = field(default_factory=list)
    false_negatives: list[str] = field(default_factory=list)

    # Quality scores (from LLM-as-Judge)
    recommendation_scores: dict[str, float] = field(default_factory=dict)

    # Cost metrics
    total_tokens: int = 0
    total_cost_usd: float = 0
    total_duration_ms: float = 0

    @property
    def precision(self) -> float:
        tp = len(self.true_positives)
        fp = len(self.false_positives)
        return tp / (tp + fp) if (tp + fp) > 0 else 0

    @property
    def recall(self) -> float:
        tp = len(self.true_positives)
        fn = len(self.false_negatives)
        return tp / (tp + fn) if (tp + fn) > 0 else 0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0

    @property
    def avg_recommendation_score(self) -> float:
        scores = list(self.recommendation_scores.values())
        return sum(scores) / len(scores) if scores else 0


def load_ground_truth() -> list[dict]:
    """Load planted anomalies from the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM anomaly_ground_truth").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def evaluate_detection(detected_anomalies: list[dict], ground_truth: list[dict]) -> EvalResult:
    """
    Compare detected anomalies against ground truth.
    Day 4: evaluation harness with precision/recall.

    Args:
        detected_anomalies: List of anomalies found by the agent pipeline.
        ground_truth: List of planted anomalies from the database.

    Returns:
        EvalResult with TP, FP, FN classifications.
    """
    result = EvalResult()

    # Build lookup of ground truth by type + vendor
    gt_keys = set()
    for gt in ground_truth:
        if gt.get("vendor"):
            gt_keys.add((gt["type"], gt["vendor"]))
        if gt.get("vendors"):
            vendors = json.loads(gt["vendors"]) if isinstance(gt["vendors"], str) else gt["vendors"]
            for v in vendors:
                gt_keys.add((gt["type"], v))

    # Match detected against ground truth
    detected_keys = set()
    for det in detected_anomalies:
        det_type = det.get("type", "")
        det_vendor = det.get("vendor", "")
        det_vendors = det.get("vendors", [])

        matched = False
        if det_vendor:
            key = (det_type, det_vendor)
            if key in gt_keys:
                result.true_positives.append(f"{det_type}:{det_vendor}")
                detected_keys.add(key)
                matched = True
        for v in det_vendors:
            key = (det_type, v)
            if key in gt_keys:
                result.true_positives.append(f"{det_type}:{v}")
                detected_keys.add(key)
                matched = True

        if not matched:
            result.false_positives.append(f"{det_type}:{det_vendor or ','.join(det_vendors)}")

    # Find missed anomalies
    for gt in ground_truth:
        if gt.get("vendor"):
            key = (gt["type"], gt["vendor"])
            if key not in detected_keys:
                result.false_negatives.append(f"{gt['type']}:{gt['vendor']}")
        if gt.get("vendors"):
            vendors = json.loads(gt["vendors"]) if isinstance(gt["vendors"], str) else gt["vendors"]
            any_found = any((gt["type"], v) in detected_keys for v in vendors)
            if not any_found:
                result.false_negatives.append(f"{gt['type']}:{','.join(vendors)}")

    return result


async def llm_judge_recommendation(recommendation: str, vendor: str) -> float:
    """
    LLM-as-a-Judge (Day 4): Score a recommendation on quality.
    Returns a score from 1-5.

    Criteria:
    - Actionability: Can a finance team execute this?
    - Specificity: Are dollar amounts and timelines included?
    - Rationale: Is the reasoning sound?
    - Completeness: Does it cover risks and alternatives?
    """
    from google import genai

    client = genai.Client(api_key=GOOGLE_API_KEY)

    judge_prompt = f"""You are evaluating the quality of a vendor cost recommendation.

RECOMMENDATION FOR {vendor}:
{recommendation}

Score this recommendation from 1-5 on each criterion:
1. ACTIONABILITY: Can a finance team execute this immediately? (1=vague, 5=step-by-step)
2. SPECIFICITY: Are dollar amounts, timelines, and next steps included? (1=none, 5=all present)
3. RATIONALE: Is the reasoning sound and data-backed? (1=unsupported, 5=well-reasoned)
4. COMPLETENESS: Are risks and alternatives addressed? (1=missing, 5=thorough)

Respond ONLY with a JSON object:
{{"actionability": N, "specificity": N, "rationale": N, "completeness": N, "overall": N}}

Where overall is the average of the four scores, rounded to 1 decimal.
Do not include any other text.
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL_JUDGE,
            contents=judge_prompt,
        )
        text = response.text.strip()
        # Clean potential markdown fencing
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        scores = json.loads(text)
        return float(scores.get("overall", 3.0))
    except Exception as e:
        console.print(f"[yellow]LLM-as-Judge error for {vendor}: {e}[/yellow]")
        return 3.0  # Default middle score on error


def display_eval_results(result: EvalResult):
    """Display evaluation results in a rich table."""
    console.print()
    console.rule("[bold magenta]Evaluation Results (Day 4)[/bold magenta]")

    # Detection metrics
    det_table = Table(title="Detection Performance", show_lines=True)
    det_table.add_column("Metric", style="bold", width=20)
    det_table.add_column("Value", justify="right", width=15)
    det_table.add_column("Details", width=45)

    det_table.add_row("True Positives", str(len(result.true_positives)),
                      ", ".join(result.true_positives[:5]) or "-")
    det_table.add_row("False Positives", str(len(result.false_positives)),
                      ", ".join(result.false_positives[:5]) or "-")
    det_table.add_row("False Negatives", str(len(result.false_negatives)),
                      ", ".join(result.false_negatives[:5]) or "-")
    det_table.add_row("Precision", f"{result.precision:.1%}", "")
    det_table.add_row("Recall", f"{result.recall:.1%}", "")
    det_table.add_row("F1 Score", f"{result.f1:.1%}", "")

    console.print(det_table)

    # Recommendation quality
    if result.recommendation_scores:
        qual_table = Table(title="Recommendation Quality (LLM-as-Judge)", show_lines=True)
        qual_table.add_column("Vendor", style="cyan", width=25)
        qual_table.add_column("Score (1-5)", justify="center", width=15)
        qual_table.add_column("Rating", width=15)

        for vendor, score in result.recommendation_scores.items():
            rating = "Excellent" if score >= 4.5 else "Good" if score >= 3.5 else "Fair" if score >= 2.5 else "Poor"
            color = "green" if score >= 4.0 else "yellow" if score >= 3.0 else "red"
            qual_table.add_row(vendor, f"[{color}]{score:.1f}[/{color}]", rating)

        qual_table.add_row("[bold]Average[/bold]",
                          f"[bold]{result.avg_recommendation_score:.1f}[/bold]", "")
        console.print(qual_table)

    # Cost metrics
    cost_table = Table(title="Cost Metrics", show_lines=True)
    cost_table.add_column("Metric", style="bold", width=25)
    cost_table.add_column("Value", justify="right", width=20)

    cost_table.add_row("Total Tokens", f"{result.total_tokens:,}")
    cost_table.add_row("Estimated Cost", f"${result.total_cost_usd:.4f}")
    cost_table.add_row("Duration", f"{result.total_duration_ms:.0f} ms")

    console.print(cost_table)
    console.print()
