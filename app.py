"""
AgentLedger Demo Dashboard
============================
Streamlit entry point. Renders a run-record (replay, default) or runs the
real pipeline live (gated). See docs/PHASE_2_DASHBOARD.md for the full spec.
"""

import os

import streamlit as st

st.set_page_config(
    page_title="AgentLedger — SaaS Cost Manager",
    page_icon=":material/account_balance:",
    layout="wide",
)

from dashboard.styles import inject_css
from dashboard.loader import list_golden_runs, load_run_record, run_label
from dashboard.render import (
    render_hero,
    render_pipeline,
    render_anomalies,
    render_recommendations,
    render_metrics_strip,
    render_details,
)

inject_css()


def _get_secret(key: str) -> str:
    try:
        return st.secrets.get(key, "")
    except Exception:
        return ""


# config.py loads .env (local dev) — import it eagerly (it's lightweight,
# no ADK/genai imports) so the key is in os.environ before we check it.
from config import GOOGLE_API_KEY as _ENV_API_KEY

api_key = _ENV_API_KEY or _get_secret("GOOGLE_API_KEY")
if api_key and not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = api_key

app_password = _get_secret("APP_PASSWORD")
live_enabled = bool(api_key)

st.title("AgentLedger")
st.caption("Autonomous SaaS Cost & Vendor Renewal Manager — Kaggle Capstone Demo")

with st.sidebar:
    st.header("Mode")
    mode_options = ["Replay"] + (["Live"] if live_enabled else [])
    mode = st.radio("Select mode", mode_options, label_visibility="collapsed")

    if not live_enabled:
        st.caption("Live mode is hidden — no API key configured. This is the public, $0 deployment.")

    record = None

    if mode == "Replay":
        runs = list_golden_runs()
        if not runs:
            st.error("No golden run records found in runs/.")
        else:
            chosen = st.selectbox(
                "Golden run",
                runs,
                format_func=lambda p: run_label(p),
            )
            record = load_run_record(chosen)

            if st.button("Play intro animation"):
                st.session_state.animate_once = True

    else:  # Live
        unlocked = True
        if app_password:
            entered = st.text_input("App password", type="password")
            unlocked = entered == app_password
            if entered and not unlocked:
                st.error("Incorrect password.")

        query = st.text_area(
            "Query",
            value=(
                "Review our SaaS spend for the last quarter. Flag any anomalies, "
                "identify savings opportunities, and prepare recommendations for "
                "upcoming renewals."
            ),
        )

        if unlocked and st.button("Run pipeline", type="primary"):
            from dashboard.live import run_live

            with st.spinner("Running the agent pipeline (ingestion → anomaly → negotiation → reporting)…"):
                st.session_state.live_record = run_live(query)
            st.session_state.pop("hitl_decision", None)

        record = st.session_state.get("live_record")
        if record is None and unlocked:
            st.caption("Run the pipeline to see results here.")

if record:
    animate = st.session_state.pop("animate_once", False)
    render_hero(record)
    render_pipeline(record, animate=animate)
    render_anomalies(record)
    render_recommendations(record)
    render_metrics_strip(record)
    render_details(record)
else:
    st.info("Select a golden run from the sidebar, or switch to Live mode if available.")
