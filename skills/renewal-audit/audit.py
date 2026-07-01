#!/usr/bin/env python3
"""
renewal-audit skill — bundled script
=====================================
A small, sandbox-runnable script invoked by the `renewal-audit` Skill playbook
(see SKILL.md). It runs AgentLedger's deterministic detection layer over the
billing store and prints a plain-text audit an operator can read in a terminal.

It REUSES the existing detection tools (it does not reimplement or modify them),
so the skill and the live agent pipeline share one source of truth.

Usage:
    python skills/renewal-audit/audit.py                 # audit everything
    python skills/renewal-audit/audit.py --renewals-only # just upcoming renewals
    python skills/renewal-audit/audit.py --as-of 2025-03-01
"""

import argparse
import json
import sys
from pathlib import Path

# Make the project importable when run from anywhere.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.agent_tools import (  # noqa: E402  (after sys.path tweak)
    fetch_all_contracts,
    fetch_all_invoices,
    detect_upcoming_renewals,
    detect_duplicate_tools,
    detect_spend_spikes,
)


def _fmt_usd(n) -> str:
    try:
        return f"${float(n):,.0f}"
    except (TypeError, ValueError):
        return str(n)


def _section(title: str) -> None:
    print(f"\n{'─' * 60}\n{title}\n{'─' * 60}")


def run_audit(renewals_only: bool, as_of: str) -> int:
    """Returns the number of findings (handy as a process exit signal)."""
    contracts_json = fetch_all_contracts()
    findings = 0

    _section("UPCOMING RENEWALS")
    renewals = json.loads(detect_upcoming_renewals(contracts_json, as_of))
    if renewals:
        for r in renewals:
            findings += 1
            print(
                f"  • {r.get('vendor', '?'):<22} renews {r.get('renewal_date', '?')} "
                f"({r.get('days_until_renewal', '?')} days) "
                f"· {_fmt_usd(r.get('monthly_cost'))}/mo"
            )
    else:
        print("  (none in the warning window)")

    if not renewals_only:
        _section("DUPLICATE TOOLS")
        dupes = json.loads(detect_duplicate_tools(contracts_json))
        if dupes:
            for d in dupes:
                findings += 1
                vendors = " · ".join(d.get("vendors", []))
                print(
                    f"  • {d.get('category', '?'):<22} {vendors} "
                    f"· {_fmt_usd(d.get('total_monthly_cost'))}/mo at stake"
                )
        else:
            print("  (no overlapping categories)")

        _section("SPEND SPIKES")
        spikes = json.loads(detect_spend_spikes(fetch_all_invoices()))
        if spikes:
            for s in spikes:
                findings += 1
                print(
                    f"  • {s.get('vendor', '?'):<22} "
                    f"{_fmt_usd(s.get('previous_amount'))} → "
                    f"{_fmt_usd(s.get('current_amount'))} "
                    f"(+{s.get('change_pct', '?')}%) in {s.get('period', '?')}"
                )
        else:
            print("  (no month-over-month spikes over threshold)")

    _section("SUMMARY")
    print(f"  {findings} finding(s). Review the items above before the next billing cycle.")
    return findings


def main() -> None:
    ap = argparse.ArgumentParser(description="AgentLedger renewal/cost audit (skill script).")
    ap.add_argument("--renewals-only", action="store_true", help="Only show upcoming renewals.")
    ap.add_argument("--as-of", default="", help="Reference date YYYY-MM-DD (default: today).")
    args = ap.parse_args()

    print("AgentLedger · renewal-audit skill")
    findings = run_audit(renewals_only=args.renewals_only, as_of=args.as_of)
    # Non-zero-ish signal is intentionally avoided: 0 findings is a valid, clean result.
    sys.exit(0 if findings >= 0 else 1)


if __name__ == "__main__":
    main()
