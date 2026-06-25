"""
AgentLedger — Main Demo Runner
================================
Interactive demo that runs the full AgentLedger pipeline with observability.

Demonstrates ALL course concepts:
  Day 1: Multi-agent ADK, agent taxonomy, security scoping
  Day 2: Custom tools, MCP server, HITL long-running operation
  Day 3: Session state, long-term memory, context engineering
  Day 4: Logs, Traces, Metrics, LLM-as-Judge, eval harness
  Day 5: A2A-style delegation, production governance

Usage:
    python main.py              # Interactive demo
    python main.py --eval       # Run eval harness
    python main.py --no-hitl    # Skip approval gate (for eval)
"""

import asyncio
import argparse
import json
import uuid
import sys
from pathlib import Path

from google import genai
from google.adk.runners import InMemoryRunner
from google.adk.sessions import Session
from google.genai import types as genai_types

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from config import GOOGLE_API_KEY, GEMINI_MODEL, DB_PATH
from agents.agent_definitions import root_agent
from observability.tracer import Tracer
from eval.eval_harness import (
    evaluate_detection,
    load_ground_truth,
    display_eval_results,
    llm_judge_recommendation,
    EvalResult,
)

console = Console()


def ensure_data_exists():
    """Check if synthetic data exists, generate if not."""
    if not DB_PATH.exists():
        console.print("[yellow]No database found. Generating synthetic data...[/yellow]")
        from scripts.generate_data import main as generate
        generate()
        console.print("[green]Data generated successfully.[/green]\n")


def print_banner():
    """Print the AgentLedger banner."""
    banner = """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   ╔═╗╔═╗╔═╗╔╗╔╔╦╗  ╦  ╔═╗╔╦╗╔═╗╔═╗╦═╗                     ║
║   ╠═╣║ ╦║╣ ║║║ ║   ║  ║╣  ║║║ ╦║╣ ╠╦╝                     ║
║   ╩ ╩╚═╝╚═╝╝╚╝ ╩   ╩═╝╚═╝═╩╝╚═╝╚═╝╩╚═                     ║
║                                                               ║
║   Autonomous SaaS Cost & Vendor Renewal Manager               ║
║   Kaggle Capstone · Agents for Business                       ║
║                                                               ║
║   Course Concepts: ADK Multi-Agent │ MCP │ HITL │ Memory      ║
║   Observability: Logs │ Traces │ Metrics │ LLM-as-Judge       ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")


async def run_agent_pipeline(user_query: str, tracer: Tracer, enable_hitl: bool = True) -> dict:
    """
    Run the full AgentLedger pipeline via ADK InMemoryRunner.

    Day 5: A2A-style delegation — the orchestrator delegates to sub-agents
    with structured task envelopes (the ADK session carries context).

    Args:
        user_query: The user's request (e.g., "Review last quarter's spend")
        tracer: Observability tracer for logs/traces/metrics
        enable_hitl: Whether to pause for human approval

    Returns:
        Dict with pipeline results including anomalies and recommendations.
    """
    # Day 3: Session state management
    runner = InMemoryRunner(agent=root_agent, app_name="agentledger")
    session = await runner.session_service.create_session(
        app_name="agentledger",
        user_id="demo_user",
    )

    # Start root trace span
    root_span = tracer.start_span("orchestrator", "full_pipeline")

    results = {
        "anomalies": [],
        "recommendations": [],
        "report": "",
        "all_agent_outputs": [],
    }

    console.print(f"\n[bold]User Query:[/bold] {user_query}\n")
    console.rule("[dim]Pipeline Start[/dim]")

    # Send user query and collect agent responses
    user_content = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=user_query)]
    )

    agent_response_text = ""

    async for event in runner.run_async(
        session_id=session.id,
        user_id="demo_user",
        new_message=user_content,
    ):
        # Track which agent is responding (Day 4: Traces)
        if hasattr(event, 'author') and event.author:
            agent_name = event.author
        else:
            agent_name = "orchestrator"

        # Process text responses
        if hasattr(event, 'content') and event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, 'text') and part.text:
                    text = part.text
                    agent_response_text += text

                    # Log agent output (Day 4: Logs)
                    tracer.log(
                        agent_name=agent_name,
                        action="response",
                        input_summary=user_query,
                        output_summary=text[:200],
                        tokens_used=len(text.split()) * 2,  # Rough estimate
                    )

                    # Display agent output
                    console.print(f"\n[bold cyan]{agent_name}:[/bold cyan]")
                    console.print(Panel(text[:500] + ("..." if len(text) > 500 else ""),
                                       border_style="dim"))

                    results["all_agent_outputs"].append({
                        "agent": agent_name,
                        "text": text,
                    })

        # Track tool calls (Day 4: Traces)
        if hasattr(event, 'content') and event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    tool_name = part.function_call.name
                    tool_args = dict(part.function_call.args) if part.function_call.args else {}
                    tracer.log_tool_call(
                        agent_name=agent_name,
                        tool_name=tool_name,
                        args=tool_args,
                        result_summary=f"Called {tool_name}",
                    )

    tracer.end_span(root_span)

    # --- HITL Approval Gate (Day 2: long-running operation) ---
    if enable_hitl and results["all_agent_outputs"]:
        console.print()
        console.rule("[bold yellow]Human-in-the-Loop Approval Gate[/bold yellow]")
        console.print(
            "[yellow]The agent has prepared recommendations. "
            "Review and approve before any actions are taken.[/yellow]\n"
            "[dim](Day 2: HITL long-running operation — "
            "agent pauses for human confirmation)[/dim]\n"
        )

        approved = Confirm.ask("Approve the recommendations above?", default=True)
        tracer.record_approval(granted=approved)

        if approved:
            console.print("[green]✓ Recommendations approved.[/green]")
        else:
            console.print("[red]✗ Recommendations rejected. No actions taken.[/red]")

    return results


async def run_eval_mode(tracer: Tracer):
    """
    Run the eval harness (Day 4: evaluation framework).
    Tests detection accuracy against planted anomalies.
    """
    console.rule("[bold magenta]Evaluation Mode[/bold magenta]")
    console.print("Running anomaly detection against planted ground truth...\n")

    from tools.agent_tools import (
        fetch_all_invoices,
        fetch_all_contracts,
        detect_spend_spikes,
        detect_duplicate_tools,
        detect_upcoming_renewals,
    )

    # Run deterministic detection tools
    invoices = fetch_all_invoices()
    contracts = fetch_all_contracts()

    spikes = json.loads(detect_spend_spikes(invoices))
    duplicates = json.loads(detect_duplicate_tools(contracts))
    renewals = json.loads(detect_upcoming_renewals(contracts))

    all_detected = spikes + duplicates + renewals
    ground_truth = load_ground_truth()

    # Evaluate detection
    eval_result = evaluate_detection(all_detected, ground_truth)

    # Add cost metrics from tracer
    eval_result.total_tokens = tracer.metrics.total_tokens
    eval_result.total_cost_usd = tracer.metrics.total_cost_usd
    eval_result.total_duration_ms = tracer.metrics.total_duration_ms

    # Display results
    display_eval_results(eval_result)

    console.print(f"\n[dim]Detected {len(all_detected)} anomalies against "
                  f"{len(ground_truth)} planted ground truth items.[/dim]")

    return eval_result


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="AgentLedger - SaaS Cost Manager")
    parser.add_argument("--eval", action="store_true", help="Run evaluation harness")
    parser.add_argument("--no-hitl", action="store_true", help="Skip HITL approval gate")
    parser.add_argument("--query", type=str, default="",
                        help="Custom query (default: review last quarter's spend)")
    args = parser.parse_args()

    # Validate API key
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "YOUR_API_KEY_HERE":
        console.print("[red]Error: GOOGLE_API_KEY not set in .env. Add your API key and try again.[/red]")
        sys.exit(1)

    print_banner()
    ensure_data_exists()

    # Initialize tracer (Day 4: observability)
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    tracer = Tracer(run_id=run_id)

    if args.eval:
        # Eval mode: test detection accuracy
        await run_eval_mode(tracer)
    else:
        # Interactive demo mode
        query = args.query or "Review our SaaS spend for the last quarter. Flag any anomalies, identify savings opportunities, and prepare recommendations for upcoming renewals."

        results = await run_agent_pipeline(
            user_query=query,
            tracer=tracer,
            enable_hitl=not args.no_hitl,
        )

    # Finalize and display observability (Day 4: the differentiator)
    tracer.finalize()
    tracer.display_all()

    console.print("[bold green]AgentLedger run complete.[/bold green]\n")


if __name__ == "__main__":
    asyncio.run(main())
