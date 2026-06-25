"""
AgentLedger Dashboard Renderers
=================================
Pure section renderers that emit HTML matching the approved mockup, populated
with real run-record data. They never run agents or touch the DB, so replay and
live runs render through identical code.
"""

import re
import time

import streamlit as st

from dashboard import styles as S
from dashboard.styles import icon

PIPELINE_ORDER = ["ingestion_agent", "anomaly_agent", "negotiation_agent", "reporting_agent"]
PIPELINE_LABELS = {
    "ingestion_agent": "Ingestion",
    "anomaly_agent": "Anomaly",
    "negotiation_agent": "Negotiation",
    "reporting_agent": "Reporting",
}


# --- formatting helpers -----------------------------------------------------

def fmt_currency(n: float) -> str:
    return f"${n:,.0f}"


def fmt_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _card_open(bg: str = None, extra: str = "") -> str:
    bg = bg or S.BG_PRIMARY
    return (
        f'<div style="background:{bg}; border:0.5px solid {S.BORDER}; '
        f'border-radius:12px; padding:14px 18px; margin-bottom:14px; {extra}">'
    )


# --- 1. Hero ----------------------------------------------------------------

def hero_html(record: dict) -> str:
    query = record.get("query", "")
    short_q = query if len(query) <= 90 else query[:87] + "…"
    savings = record.get("totals", {}).get("identified_annual_savings_usd", 0.0)
    return f"""
    <div style="display:flex; align-items:center; justify-content:space-between;
         gap:16px; background:{S.BG_SECONDARY}; border:0.5px solid {S.BORDER};
         border-radius:14px; padding:18px 22px; margin-bottom:14px;">
      <div>
        <div style="font-size:13px; color:{S.TEXT_SECONDARY};">
          {icon('receipt', size=15)} AgentLedger — SaaS cost review</div>
        <div style="font-size:14px; color:{S.TEXT_SECONDARY}; margin-top:6px;">"{short_q}"</div>
      </div>
      <div style="text-align:right; white-space:nowrap;">
        <div style="font-size:12px; color:{S.TEXT_SECONDARY};">Identified annual savings</div>
        <div style="font-size:30px; font-weight:600; color:{S.SUCCESS};">{fmt_currency(savings)}</div>
      </div>
    </div>"""


def render_hero(record: dict):
    st.markdown(hero_html(record), unsafe_allow_html=True)


# --- 2. Pipeline ------------------------------------------------------------

def _pipeline_stat(record: dict, name: str) -> str:
    dataset = record.get("dataset", {})
    n_anom = len(record.get("anomalies", []))
    n_rec = len(record.get("recommendations", []))
    if name == "ingestion_agent":
        return f"{dataset.get('invoices', 0)} invoices"
    if name == "anomaly_agent":
        return f"{n_anom} flagged"
    if name == "negotiation_agent":
        return f"{n_rec} drafted"
    return "report ready"


def _node_html(record: dict, name: str, state: str) -> str:
    """state: 'done' | 'active' | 'queued'"""
    ic = S.AGENT_ICONS.get(name, "robot")
    label = PIPELINE_LABELS[name]
    if state == "active":
        bg, border, txtcol = S.INFO_BG, f"2px solid {S.INFO_BORDER}", S.INFO
        stat = f"{icon('loader')} working…"
        opacity = "1"
    elif state == "queued":
        bg, border, txtcol = S.BG_PRIMARY, f"0.5px solid {S.BORDER}", S.TEXT_TERTIARY
        stat = "queued"
        opacity = "0.55"
    else:  # done
        bg, border, txtcol = S.BG_PRIMARY, f"0.5px solid {S.BORDER}", S.SUCCESS
        stat = f"{icon('check')} {_pipeline_stat(record, name)}"
        opacity = "1"

    done_icon_colors = {
        "ingestion_agent": S.INFO,
        "anomaly_agent": S.WARNING,
        "negotiation_agent": S.INFO,
        "reporting_agent": S.TEXT_SECONDARY,
    }
    if state == "active":
        icon_color = S.INFO
    elif state == "queued":
        icon_color = S.TEXT_SECONDARY
    else:
        icon_color = done_icon_colors.get(name, S.INFO)
    name_color = S.INFO if state == "active" else "inherit"
    return f"""<div style="flex:1; background:{bg}; border:{border}; border-radius:10px;
        padding:12px 8px; text-align:center; opacity:{opacity};">
        {icon(ic, color=icon_color, size=19)}
        <div style="font-size:12px; font-weight:600; margin-top:5px; color:{name_color};">{label}</div>
        <div style="font-size:11px; color:{txtcol}; margin-top:2px;">{stat}</div>
        </div>"""


def _arrow() -> str:
    return (f'<div style="display:flex; align-items:center; color:{S.TEXT_TERTIARY};">'
            f'{icon("arrow-right")}</div>')


def _pipeline_row(record: dict, states: dict) -> str:
    parts = ['<div style="display:flex; align-items:stretch; gap:8px; margin-bottom:14px;">']
    for i, name in enumerate(PIPELINE_ORDER):
        parts.append(_node_html(record, name, states[name]))
        if i < len(PIPELINE_ORDER) - 1:
            parts.append(_arrow())
    parts.append("</div>")
    return "".join(parts)


def render_pipeline(record: dict, animate: bool = False, delay: float = 0.45):
    if not animate:
        states = {n: "done" for n in PIPELINE_ORDER}
        st.markdown(_pipeline_row(record, states), unsafe_allow_html=True)
        return

    placeholder = st.empty()
    for idx in range(len(PIPELINE_ORDER) + 1):
        states = {}
        for j, n in enumerate(PIPELINE_ORDER):
            if j < idx:
                states[n] = "done"
            elif j == idx:
                states[n] = "active"
            else:
                states[n] = "queued"
        placeholder.markdown(_pipeline_row(record, states), unsafe_allow_html=True)
        time.sleep(delay)
    placeholder.markdown(
        _pipeline_row(record, {n: "done" for n in PIPELINE_ORDER}),
        unsafe_allow_html=True,
    )


# --- 3. Anomalies -----------------------------------------------------------

def _anomaly_card(a: dict) -> str:
    sev = a.get("severity", "low")
    s = S.severity_style(sev)
    ic = S.ANOMALY_ICONS.get(a.get("type", ""), "info-circle")

    if a["type"] == "spend_spike":
        label = f"SPEND SPIKE · {S.SEVERITY_SHORT.get(sev, sev.upper())}"
        title = a["vendor"]
        detail = (f"{fmt_currency(a['previous_amount'])} → {fmt_currency(a['current_amount'])}"
                  f" / mo (+{a['change_pct']:.0f}%)")
    elif a["type"] == "duplicate_tools":
        label = f"DUPLICATE TOOLS · {S.SEVERITY_SHORT.get(sev, sev.upper())}"
        title = " · ".join(a.get("vendors", []))
        raw_cat = a.get("category", "")
        cat = raw_cat.upper() if len(raw_cat) <= 3 else raw_cat.replace("_", " ").title()
        detail = f"{cat} · {fmt_currency(a['total_monthly_cost'])}/mo at stake"
    elif a["type"] == "upcoming_renewal":
        label = f"RENEWAL · {a['days_until_renewal']} DAYS"
        title = a["vendor"]
        detail = f"Renews {a['renewal_date']} · {fmt_currency(a['monthly_cost'])}/mo"
    else:
        label = a.get("type", "ANOMALY").upper()
        title = a.get("vendor", "")
        detail = ""

    return f"""<div style="background:{S.BG_PRIMARY}; border:0.5px solid {S.BORDER};
        border-left:3px solid {s['border']}; border-radius:0 6px 6px 0; padding:12px 14px;">
        <div style="font-size:11px; font-weight:600; color:{s['label']}; letter-spacing:0.02em;">
          {icon(ic)} {label}</div>
        <div style="font-size:14px; font-weight:600; margin:5px 0 3px 0; color:{S.TEXT};">{title}</div>
        <div style="font-size:12px; color:{S.TEXT_SECONDARY};">{detail}</div>
        </div>"""


def render_anomalies(record: dict):
    anomalies = record.get("anomalies", [])
    st.markdown(
        f'<div class="al-section-title">Anomaly findings · {len(anomalies)}</div>',
        unsafe_allow_html=True,
    )
    if not anomalies:
        st.info("No anomalies detected in this run.")
        return
    cards = "".join(_anomaly_card(a) for a in anomalies)
    grid = (f'<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(230px,1fr));'
            f' gap:10px; margin-bottom:14px;">{cards}</div>')
    st.markdown(grid, unsafe_allow_html=True)


# --- 4. Recommendations + HITL ---------------------------------------------

def _rec_summary(rec: dict) -> tuple[str, str]:
    """(title, one-line summary) parsed from the recommendation text."""
    text = rec.get("recommendation_text", "")
    action = rec.get("action", "").title()

    m_vendor = re.search(r"Vendor:\s*(.+)", text)
    vendor_line = m_vendor.group(1).strip() if m_vendor else rec.get("vendor", "")
    title = f"{action}: {vendor_line}" if action else vendor_line

    m_rat = re.search(r"Rationale:\s*(.+)", text)
    summary = ""
    if m_rat:
        summary = m_rat.group(1).strip()
        summary = re.split(r"(?<=[.!?])\s", summary)[0]
        if len(summary) > 160:
            summary = summary[:157] + "…"
    if not summary:
        summary = "Draft email ready." if rec.get("draft_email") else "Review recommendation."
    return title, summary


def _rec_card(rec: dict) -> str:
    badge = S.action_badge(rec.get("action", ""))
    title, summary = _rec_summary(rec)
    savings = rec.get("annual_savings_usd", 0.0)
    savings_label = (f"{fmt_currency(savings)} / yr saved" if savings else "no direct savings")

    return f"""<div style="background:{S.BG_PRIMARY}; border:0.5px solid {S.BORDER};
        border-radius:12px; padding:14px 18px; margin-bottom:10px;">
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
          <span style="font-size:12px; font-weight:600; color:{badge['text']};
            background:{badge['bg']}; padding:3px 11px; border-radius:8px;">{rec.get('action','')}</span>
          <span style="font-size:14px; font-weight:600; color:{S.SUCCESS};">{savings_label}</span>
        </div>
        <div style="font-size:14px; font-weight:600; color:{S.TEXT};">{title}</div>
        <div style="font-size:13px; color:{S.TEXT_SECONDARY}; line-height:1.55; margin-top:6px;">{summary}</div>
        </div>"""


def render_recommendations(record: dict):
    recs = record.get("recommendations", [])
    st.markdown(
        f'<div class="al-section-title">Recommendations · {len(recs)}</div>',
        unsafe_allow_html=True,
    )
    if recs:
        st.markdown("".join(_rec_card(r) for r in recs), unsafe_allow_html=True)
        with st.expander("View draft emails & full recommendation text"):
            for rec in recs:
                st.markdown(f"**{rec.get('vendor', '')}** — {rec.get('action', '')}")
                if rec.get("draft_email"):
                    st.text(rec["draft_email"])
                else:
                    st.caption("No standalone draft email parsed; see full text below.")
                with st.popover("Full text"):
                    st.text(rec.get("recommendation_text", ""))
                st.divider()

    render_hitl_gate(record)


def render_hitl_gate(record: dict):
    if "hitl_decision" not in st.session_state:
        granted = record.get("hitl", {}).get("granted")
        st.session_state.hitl_decision = (
            "approved" if granted is True else "rejected" if granted is False else None
        )

    c1, c2, c3 = st.columns([5, 1, 1])
    with c1:
        st.markdown(
            f'<div style="font-size:12px; color:{S.TEXT_SECONDARY}; padding-top:8px;">'
            f'{icon("user-check")} Human approval required</div>',
            unsafe_allow_html=True,
        )
    with c2:
        if st.button("Approve", key="approve_btn", use_container_width=True):
            st.session_state.hitl_decision = "approved"
    with c3:
        if st.button("Reject", key="reject_btn", use_container_width=True):
            st.session_state.hitl_decision = "rejected"

    decision = st.session_state.hitl_decision
    if decision == "approved":
        st.success("Recommendations approved.")
    elif decision == "rejected":
        st.error("Recommendations rejected. No actions taken.")


# --- 5. Bottom metric strip (observability + evaluation headline) -----------

def _metric_card(label: str, value: str, success: bool = False) -> str:
    color = S.SUCCESS if success else S.TEXT
    return f"""<div style="background:{S.BG_SECONDARY}; border:0.5px solid {S.BORDER};
        border-radius:10px; padding:13px 15px;">
        <div style="font-size:12px; color:{S.TEXT_SECONDARY};">{label}</div>
        <div style="font-size:21px; font-weight:600; color:{color}; margin-top:2px;">{value}</div>
        </div>"""


def render_metrics_strip(record: dict):
    m = record.get("metrics", {})
    ev = record.get("evaluation", {})
    detection = ev.get("detection")
    judge = ev.get("judge")

    latency = f"{m.get('total_duration_ms', 0) / 1000:.1f}s"
    tokens_cost = f"{fmt_tokens(m.get('total_tokens', 0))} · ${m.get('total_cost_usd', 0):.2f}"
    f1 = f"{detection['f1'] * 100:.1f}%" if detection else "—"
    judge_val = f"{judge['average_score']:.2f} / 5" if judge else "—"

    cards = (
        _metric_card("Trace latency", latency)
        + _metric_card("Tokens / cost", tokens_cost)
        + _metric_card("Detection F1", f1)
        + _metric_card("Judge score", judge_val, success=bool(judge))
    )
    grid = (f'<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px,1fr));'
            f' gap:10px; margin-bottom:14px;">{cards}</div>')
    st.markdown(grid, unsafe_allow_html=True)


# --- 6. Details (extra depth, below the mockup strip) -----------------------

def _render_span(span: dict, depth: int = 0):
    if span is None:
        return
    indent = "&nbsp;" * (depth * 4)
    st.markdown(
        f"{indent}**{span.get('agent_name', '')}** · {span.get('operation', '')} "
        f"· {span.get('duration_ms', 0):.0f}ms "
        f"· {span.get('tokens_in', 0) + span.get('tokens_out', 0)} tokens",
        unsafe_allow_html=True,
    )
    for child in span.get("children", []) or []:
        _render_span(child, depth + 1)


def render_details(record: dict):
    with st.expander("Observability — trace & logs"):
        root = record.get("trace", {}).get("root")
        if root:
            _render_span(root)
        st.divider()
        logs = record.get("logs", [])
        if logs:
            st.dataframe(logs, width="stretch")

    ev = record.get("evaluation", {})
    detection = ev.get("detection")
    judge = ev.get("judge")
    if detection or judge:
        with st.expander("Evaluation detail"):
            if detection:
                st.markdown(f"**True positives:** {', '.join(detection.get('true_positives', [])) or '—'}")
                st.markdown(f"**False positives:** {', '.join(detection.get('false_positives', [])) or '—'}")
                st.markdown(f"**False negatives:** {', '.join(detection.get('false_negatives', [])) or '—'}")
            if judge:
                st.divider()
                st.markdown(f"**LLM-judge average:** {judge['average_score']:.2f} / 5")
                for vendor, score in judge.get("scores", {}).items():
                    st.markdown(f"- **{vendor}**: {score:.1f}/5")
            elif detection:
                st.caption("Judge not run for this record.")
