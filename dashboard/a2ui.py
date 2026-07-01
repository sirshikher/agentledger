"""
A2UI — Agent-to-User-Interface (generative, but safe)
=====================================================
Demonstrates the A2UI concept applied to the Evaluation Detail section: the
agent reads raw eval output (precision/recall/F1, per-vendor judge scores) and
*generates an interpreted UI spec* — a narrative, key metrics, and any weakness
callouts. The host renders through a fixed allowlist with html.escape() on all
model text. Model output is data, never code.

Two pieces:
  - generate_eval_ui_spec(record)  → one Gemini call, returns raw spec list
  - render_eval_a2ui(record)       → safe renderer (allowlist + escaping)
"""

import html
import json

import streamlit as st

from dashboard import styles as S

# --- Safety boundary ---------------------------------------------------------
ALLOWED_TYPES = {"note", "metric", "alert"}


# --- 1. Generative step ------------------------------------------------------

def generate_eval_ui_spec(record: dict, model: str | None = None) -> list[dict]:
    """Ask Gemini to interpret the evaluation results and compose a UI spec.
    Returns a raw list — caller must pass through render_eval_a2ui."""
    from google import genai
    from config import GOOGLE_API_KEY, GEMINI_MODEL

    client = genai.Client(api_key=GOOGLE_API_KEY)

    ev = record.get("evaluation", {})
    detection = ev.get("detection", {})
    judge = ev.get("judge", {})

    eval_data = {
        "detection": {
            "precision": detection.get("precision"),
            "recall": detection.get("recall"),
            "f1": detection.get("f1"),
            "true_positives": detection.get("true_positives", []),
            "false_positives": detection.get("false_positives", []),
            "false_negatives": detection.get("false_negatives", []),
        } if detection else None,
        "judge": {
            "average_score": judge.get("average_score"),
            "scores": judge.get("scores", {}),
        } if judge else None,
    }

    prompt = f"""You are an AI quality-assurance analyst. Given the evaluation results
of a multi-agent SaaS cost review pipeline, compose a concise interpreted summary
for an engineer reviewing system quality.

Return ONLY a JSON array of 5-9 components in this order:

1. One "note" with a 2-3 sentence narrative interpreting the results:
   - Lead with the F1 score and what it means practically
   - Call out any false positives or false negatives by name
   - End with one sentence on recommendation quality (judge score)

Then "metric" components for each key number (precision, recall, F1, judge avg).

Then 0-2 "alert" components for any meaningful weaknesses (false positives that
could cause wasted effort, false negatives that mean missed savings, low judge
scores). Omit alerts if results are clean.

Component schemas (all field values must be strings):
- {{"type":"note","text":"<narrative>"}}
- {{"type":"metric","label":"<label>","value":"<value>"}}
- {{"type":"alert","severity":"high|medium|low","title":"<issue title>","detail":"<one line>"}}

Rules:
- No markdown fences, no prose outside the array — ONLY the JSON array.
- Do not invent numbers. Use only what is in EVAL_DATA.
- Format percentages as "X.X%" and scores as "X.XX / 5".

EVAL_DATA:
{json.dumps(eval_data, indent=2)}
"""

    response = client.models.generate_content(
        model=model or GEMINI_MODEL,
        contents=prompt,
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    spec = json.loads(text)
    if not isinstance(spec, list):
        raise ValueError("Eval UI spec was not a JSON array")
    return spec


# --- 2. Deterministic fallback -----------------------------------------------

def fallback_eval_ui_spec(record: dict) -> list[dict]:
    ev = record.get("evaluation", {})
    detection = ev.get("detection", {})
    judge = ev.get("judge", {})

    spec: list[dict] = []

    if detection:
        p = detection.get("precision", 0)
        r = detection.get("recall", 0)
        f1 = detection.get("f1", 0)
        fps = detection.get("false_positives", [])
        fns = detection.get("false_negatives", [])
        narrative = (
            f"Detection F1 {f1 * 100:.1f}% (precision {p * 100:.1f}%, recall {r * 100:.1f}%). "
        )
        if fps:
            narrative += f"{len(fps)} false positive(s) flagged. "
        if fns:
            narrative += f"{len(fns)} anomaly(ies) missed. "
        if judge:
            narrative += f"Recommendation quality: {judge.get('average_score', 0):.2f} / 5."
        spec.append({"type": "note", "text": narrative})
        spec += [
            {"type": "metric", "label": "Precision", "value": f"{p * 100:.1f}%"},
            {"type": "metric", "label": "Recall", "value": f"{r * 100:.1f}%"},
            {"type": "metric", "label": "F1", "value": f"{f1 * 100:.1f}%"},
        ]
        if fps:
            spec.append({
                "type": "alert", "severity": "low",
                "title": f"{len(fps)} false positive(s)",
                "detail": "; ".join(fps[:3]),
            })
    if judge:
        spec.append({
            "type": "metric", "label": "Judge avg",
            "value": f"{judge.get('average_score', 0):.2f} / 5",
        })

    if not spec:
        spec.append({"type": "note", "text": "No evaluation data available for this run."})
    return spec


# --- 3. Safe renderer --------------------------------------------------------

def _esc(v) -> str:
    return html.escape(str(v), quote=True)


_SEVERITY_COLORS = {
    "high":   S.SEVERITY["high"],
    "medium": S.SEVERITY["medium"],
    "low":    S.SEVERITY["low"],
}


def _render_component(c: dict) -> str:
    t = c["type"]
    if t == "note":
        return (
            f'<p style="font-size:13px;line-height:1.65;color:{S.TEXT};margin:0 0 12px 0;">'
            f'{_esc(c.get("text", ""))}</p>'
        )
    if t == "metric":
        return (
            f'<div style="display:inline-block;min-width:110px;background:{S.BG_SECONDARY};'
            f'border:0.5px solid {S.BORDER};border-radius:10px;padding:10px 14px;margin:0 8px 8px 0;">'
            f'<div style="font-size:11px;color:{S.TEXT_SECONDARY};">{_esc(c.get("label",""))}</div>'
            f'<div style="font-size:18px;font-weight:600;color:{S.TEXT};">{_esc(c.get("value",""))}</div>'
            f'</div>'
        )
    if t == "alert":
        sev = c.get("severity", "low")
        col = _SEVERITY_COLORS.get(sev, _SEVERITY_COLORS["low"])
        return (
            f'<div style="background:{S.BG_PRIMARY};border:0.5px solid {S.BORDER};'
            f'border-left:3px solid {col["border"]};border-radius:0 8px 8px 0;'
            f'padding:9px 13px;margin-bottom:8px;">'
            f'<div style="font-size:11px;font-weight:600;color:{col["label"]};text-transform:uppercase;">'
            f'{_esc(sev)}</div>'
            f'<div style="font-size:13px;font-weight:600;color:{S.TEXT};">{_esc(c.get("title",""))}</div>'
            f'<div style="font-size:12px;color:{S.TEXT_SECONDARY};">{_esc(c.get("detail",""))}</div>'
            f'</div>'
        )
    return ""


def render_eval_a2ui(record: dict) -> None:
    """Render the A2UI-composed evaluation interpretation.
    Uses stored spec from record['a2ui']['components'] if present ($0 replay);
    falls back to deterministic spec otherwise."""
    stored = record.get("a2ui")
    if stored and isinstance(stored.get("components"), list):
        spec = stored["components"]
        generated_by = stored.get("generated_by")
    else:
        spec = fallback_eval_ui_spec(record)
        generated_by = None

    # Validate — only ALLOWED_TYPES dicts pass through
    clean, rejected = [], []
    for comp in spec if isinstance(spec, list) else []:
        if isinstance(comp, dict) and comp.get("type") in ALLOWED_TYPES:
            clean.append(comp)
        else:
            rejected.append(str(comp.get("type") if isinstance(comp, dict) else type(comp).__name__))

    if not clean:
        return

    provenance = (
        f'🪄 Composed by <code>{_esc(generated_by)}</code>'
        if generated_by else "Deterministic interpretation"
    )

    # Batch consecutive metrics into a flex row
    html_parts: list[str] = []
    i = 0
    while i < len(clean):
        c = clean[i]
        if c["type"] == "metric":
            row = []
            while i < len(clean) and clean[i]["type"] == "metric":
                row.append(_render_component(clean[i]))
                i += 1
            html_parts.append(
                f'<div style="display:flex;flex-wrap:wrap;gap:0;margin-bottom:6px;">'
                + "".join(row) + "</div>"
            )
        else:
            html_parts.append(_render_component(c))
            i += 1

    header = (
        f'<div style="font-size:11px;font-weight:600;letter-spacing:0.06em;'
        f'text-transform:uppercase;color:{S.INFO};margin-bottom:10px;">'
        f'AI interpretation &nbsp;·&nbsp; '
        f'<span style="font-weight:400;text-transform:none;letter-spacing:0;">{provenance}</span>'
        f'</div>'
    )

    box = (
        f'<div style="background:rgba(90,140,210,0.06);border:1px solid rgba(90,140,210,0.20);'
        f'border-radius:10px;padding:14px 16px;margin-bottom:10px;">'
        f'{header}{"".join(html_parts)}</div>'
    )
    st.markdown(box, unsafe_allow_html=True)

    if rejected:
        st.warning(f"🛡️ Safety guard rejected {len(rejected)} component(s): {', '.join(sorted(set(rejected)))}")
