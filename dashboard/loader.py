"""
AgentLedger Dashboard Loader
=============================
Discovers and loads run-record JSON files from runs/ for replay mode.
"""

import json
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"


def list_golden_runs() -> list[Path]:
    """Return all committed golden_*.json run records, sorted by name."""
    if not RUNS_DIR.exists():
        return []
    return sorted(RUNS_DIR.glob("golden_*.json"))


def load_run_record(path: Path) -> dict:
    return json.loads(path.read_text())


def run_label(path: Path, record: dict | None = None) -> str:
    """A human-friendly label for the replay selectbox."""
    if record is None:
        record = load_run_record(path)
    query = record.get("query", "")
    short_query = query if len(query) <= 60 else query[:57] + "..."
    return f"{path.stem} — {short_query}"
