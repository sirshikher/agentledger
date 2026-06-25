"""
AgentLedger Dashboard Styles
=============================
Concrete dark-theme palette + Tabler icon helpers + CSS injection, mirroring
the approved mockup (docs mockup: dark cards, 0.5px borders, severity
left-borders, colored action badges, compact pipeline row).
"""

# --- Palette (concrete values matching the mockup's design tokens, dark) ---
BG_PRIMARY = "#262624"        # cards
BG_SECONDARY = "#201F1D"      # hero / metric strip
BORDER = "rgba(255,255,255,0.10)"
TEXT = "#E8E8E3"
TEXT_SECONDARY = "#9B9B94"
TEXT_TERTIARY = "#6F6F69"
SUCCESS = "#6CC24A"           # green numbers / checks
INFO = "#6AA6E0"             # blue (active pipeline node)
INFO_BORDER = "#4F7FB8"
INFO_BG = "rgba(90,140,210,0.14)"
WARNING = "#D6A23F"
DANGER = "#E0625F"

# Anomaly severity → left-border + label color (brightened for dark bg)
SEVERITY = {
    "high": {"border": "#E24B4A", "label": "#E88B89"},
    "medium": {"border": "#BA7517", "label": "#D6A23F"},
    "low": {"border": "#378ADD", "label": "#6AA6E0"},
}

# Action → badge background + text (light pill on dark, like mockup CONSOLIDATE)
ACTION_BADGE = {
    "CONSOLIDATE": {"bg": "#C0DD97", "text": "#173404"},
    "CANCEL": {"bg": "#F0B4B2", "text": "#5C1311"},
    "DOWNGRADE": {"bg": "#EBC98C", "text": "#4A3208"},
    "RENEGOTIATE": {"bg": "#A9CBEC", "text": "#0E2E50"},
    "MONITOR": {"bg": "#D5D3CB", "text": "#33322D"},
}

# Tabler icon class names (mockup uses ti ti-*)
AGENT_ICONS = {
    "ingestion_agent": "database",
    "anomaly_agent": "alert-triangle",
    "negotiation_agent": "message-2",
    "reporting_agent": "file-text",
}
ANOMALY_ICONS = {
    "spend_spike": "trending-up",
    "duplicate_tools": "copy",
    "upcoming_renewal": "calendar-due",
}

SEVERITY_SHORT = {"high": "HIGH", "medium": "MED", "low": "LOW"}


def icon(name: str, color: str = "", size: int = 0) -> str:
    style = ""
    if color:
        style += f"color:{color};"
    if size:
        style += f"font-size:{size}px;"
    style_attr = f' style="{style}"' if style else ""
    return f'<i class="ti ti-{name}" aria-hidden="true"{style_attr}></i>'


def severity_style(severity: str) -> dict:
    return SEVERITY.get(severity, SEVERITY["low"])


def action_badge(action: str) -> dict:
    return ACTION_BADGE.get(action, ACTION_BADGE["MONITOR"])


def inject_css():
    import streamlit as st

    st.markdown(
        f"""
        <style>
        @import url('https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@2.47.0/dist/tabler-icons.min.css');

        .block-container {{ padding-top: 2.5rem; max-width: 1140px; }}

        /* Approve / Reject — outline text buttons matching the mockup */
        .st-key-approve_btn button {{
            background: transparent !important;
            border: 1px solid {SUCCESS} !important;
            color: {SUCCESS} !important;
        }}
        .st-key-reject_btn button {{
            background: transparent !important;
            border: 1px solid {DANGER} !important;
            color: {DANGER} !important;
        }}
        .st-key-approve_btn button:hover {{ background: rgba(108,194,74,0.12) !important; }}
        .st-key-reject_btn button:hover  {{ background: rgba(224,98,95,0.12) !important; }}

        .al-section-title {{
            font-size: 13px; font-weight: 600; letter-spacing: 0.04em;
            text-transform: uppercase; color: {TEXT_SECONDARY};
            margin: 0.5rem 0 0.4rem 0;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
