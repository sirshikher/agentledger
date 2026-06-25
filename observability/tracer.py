"""
AgentLedger Observability Layer
================================
Implements the three pillars from Day 4:
  - Logs:    Per-step structured diary with tool call audit trail
  - Traces:  End-to-end causal chain across all agent hops with latency
  - Metrics: Cost, latency, detection precision per run

This is the core differentiator. Most capstone submissions skip observability.
"""

import time
import json
from dataclasses import dataclass, field
from typing import Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree

console = Console()


@dataclass
class LogEntry:
    """Single agent log entry (Day 4: Logs - the diary)."""
    timestamp: float
    agent_name: str
    action: str
    input_summary: str
    output_summary: str
    tool_calls: list[str] = field(default_factory=list)
    tokens_used: int = 0
    duration_ms: float = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class TraceSpan:
    """A single span in a trace (Day 4: Traces - the narrative)."""
    span_id: str
    agent_name: str
    operation: str
    start_time: float
    end_time: float = 0
    parent_span_id: str | None = None
    tool_calls: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    status: str = "ok"
    children: list["TraceSpan"] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        if self.end_time == 0:
            return 0
        return (self.end_time - self.start_time) * 1000

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out


@dataclass
class RunMetrics:
    """Aggregate metrics for a full run (Day 4: Metrics - the health report)."""
    run_id: str
    start_time: float = 0
    end_time: float = 0
    total_tokens: int = 0
    total_cost_usd: float = 0
    agents_invoked: int = 0
    tool_calls_made: int = 0
    anomalies_flagged: int = 0
    recommendations_made: int = 0
    approvals_requested: int = 0
    approvals_granted: int = 0
    approvals_rejected: int = 0

    @property
    def total_duration_ms(self) -> float:
        if self.end_time == 0:
            return 0
        return (self.end_time - self.start_time) * 1000

    @property
    def approval_rate(self) -> float:
        if self.approvals_requested == 0:
            return 0
        return self.approvals_granted / self.approvals_requested


class Tracer:
    """
    Central tracer for AgentLedger runs.
    Collects logs, builds traces, computes metrics.
    Inspired by OpenTelemetry patterns adapted for agent workflows.
    """

    # Approximate Gemini 2.0 Flash pricing (per 1M tokens)
    COST_PER_1M_INPUT = 0.10
    COST_PER_1M_OUTPUT = 0.40

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.logs: list[LogEntry] = []
        self.root_span: TraceSpan | None = None
        self._span_stack: list[TraceSpan] = []
        self.metrics = RunMetrics(run_id=run_id)
        self.metrics.start_time = time.time()

    # --- Span management (Day 4: Traces) ---

    def start_span(self, agent_name: str, operation: str) -> TraceSpan:
        """Start a new trace span for an agent operation."""
        parent = self._span_stack[-1] if self._span_stack else None
        span = TraceSpan(
            span_id=f"{agent_name}_{operation}_{len(self.logs)}",
            agent_name=agent_name,
            operation=operation,
            start_time=time.time(),
            parent_span_id=parent.span_id if parent else None,
        )
        if parent:
            parent.children.append(span)
        if self.root_span is None:
            self.root_span = span
        self._span_stack.append(span)
        self.metrics.agents_invoked += 1
        return span

    def end_span(self, span: TraceSpan, status: str = "ok"):
        """End a trace span."""
        span.end_time = time.time()
        span.status = status
        if self._span_stack and self._span_stack[-1].span_id == span.span_id:
            self._span_stack.pop()

    # --- Logging (Day 4: Logs) ---

    def log(self, agent_name: str, action: str, input_summary: str,
            output_summary: str, tool_calls: list[str] | None = None,
            tokens_used: int = 0, **metadata):
        """Record a structured log entry."""
        entry = LogEntry(
            timestamp=time.time(),
            agent_name=agent_name,
            action=action,
            input_summary=input_summary[:200],
            output_summary=output_summary[:200],
            tool_calls=tool_calls or [],
            tokens_used=tokens_used,
            metadata=metadata,
        )
        self.logs.append(entry)

        # Update metrics
        self.metrics.total_tokens += tokens_used
        self.metrics.tool_calls_made += len(entry.tool_calls)

        # Update cost estimate
        self.metrics.total_cost_usd = (
            self.metrics.total_tokens / 1_000_000 *
            (self.COST_PER_1M_INPUT + self.COST_PER_1M_OUTPUT) / 2
        )

    def log_tool_call(self, agent_name: str, tool_name: str, args: dict, result_summary: str):
        """Log a specific tool call."""
        self.log(
            agent_name=agent_name,
            action=f"tool_call:{tool_name}",
            input_summary=json.dumps(args, default=str)[:200],
            output_summary=result_summary[:200],
            tool_calls=[tool_name],
        )

    # --- Metrics helpers ---

    def record_anomaly(self, count: int = 1):
        self.metrics.anomalies_flagged += count

    def record_recommendation(self, count: int = 1):
        self.metrics.recommendations_made += count

    def record_approval(self, granted: bool):
        self.metrics.approvals_requested += 1
        if granted:
            self.metrics.approvals_granted += 1
        else:
            self.metrics.approvals_rejected += 1

    def finalize(self):
        """Finalize the run metrics."""
        self.metrics.end_time = time.time()

    # --- Display (Rich terminal output) ---

    def display_trace(self):
        """Display the full trace tree (Day 4: Traces visualization)."""
        if not self.root_span:
            console.print("[yellow]No trace data collected.[/yellow]")
            return

        tree = Tree(
            f"[bold cyan]Trace: {self.run_id}[/bold cyan] "
            f"({self.metrics.total_duration_ms:.0f}ms total)"
        )
        self._build_tree(tree, self.root_span)
        console.print(Panel(tree, title="Agent Trace (Day 4: Traces)", border_style="cyan"))

    def _build_tree(self, tree: Tree, span: TraceSpan):
        status_icon = "✓" if span.status == "ok" else "✗"
        color = "green" if span.status == "ok" else "red"
        label = (
            f"[{color}]{status_icon}[/{color}] "
            f"[bold]{span.agent_name}[/bold] → {span.operation} "
            f"[dim]({span.duration_ms:.0f}ms, {span.total_tokens} tokens)[/dim]"
        )
        if span.tool_calls:
            label += f" [yellow]tools: {', '.join(span.tool_calls)}[/yellow]"

        branch = tree.add(label)
        for child in span.children:
            self._build_tree(branch, child)

    def display_logs(self):
        """Display structured logs table (Day 4: Logs visualization)."""
        table = Table(title="Agent Logs (Day 4: Logs)", show_lines=True)
        table.add_column("Time", style="dim", width=10)
        table.add_column("Agent", style="cyan", width=18)
        table.add_column("Action", style="green", width=22)
        table.add_column("Tools", style="yellow", width=20)
        table.add_column("Tokens", justify="right", width=8)
        table.add_column("Output", width=40)

        base_time = self.logs[0].timestamp if self.logs else 0
        for entry in self.logs:
            elapsed = f"+{(entry.timestamp - base_time):.1f}s"
            tools = ", ".join(entry.tool_calls) if entry.tool_calls else "-"
            table.add_row(
                elapsed, entry.agent_name, entry.action,
                tools, str(entry.tokens_used), entry.output_summary[:40],
            )

        console.print(table)

    def display_metrics(self):
        """Display aggregate metrics dashboard (Day 4: Metrics visualization)."""
        m = self.metrics
        table = Table(title="Run Metrics (Day 4: Metrics)", show_lines=True)
        table.add_column("Metric", style="bold", width=28)
        table.add_column("Value", justify="right", width=20)

        table.add_row("Run ID", m.run_id)
        table.add_row("Total Duration", f"{m.total_duration_ms:.0f} ms")
        table.add_row("Agents Invoked", str(m.agents_invoked))
        table.add_row("Tool Calls Made", str(m.tool_calls_made))
        table.add_row("Total Tokens", f"{m.total_tokens:,}")
        table.add_row("Estimated Cost", f"${m.total_cost_usd:.4f}")
        table.add_row("Anomalies Flagged", str(m.anomalies_flagged))
        table.add_row("Recommendations Made", str(m.recommendations_made))
        table.add_row("Approvals Requested", str(m.approvals_requested))
        table.add_row("Approval Rate", f"{m.approval_rate:.0%}" if m.approvals_requested > 0 else "N/A")

        console.print(table)

    def display_all(self):
        """Display complete observability dashboard."""
        console.print()
        console.rule("[bold magenta]AgentLedger Observability Dashboard[/bold magenta]")
        console.print()
        self.display_trace()
        console.print()
        self.display_logs()
        console.print()
        self.display_metrics()
        console.print()

    def to_dict(self) -> dict:
        """Export trace data as dict for eval harness."""
        return {
            "run_id": self.run_id,
            "metrics": {
                "total_duration_ms": self.metrics.total_duration_ms,
                "total_tokens": self.metrics.total_tokens,
                "total_cost_usd": self.metrics.total_cost_usd,
                "agents_invoked": self.metrics.agents_invoked,
                "tool_calls_made": self.metrics.tool_calls_made,
                "anomalies_flagged": self.metrics.anomalies_flagged,
                "recommendations_made": self.metrics.recommendations_made,
            },
            "log_count": len(self.logs),
        }

    # --- Full serialization (Phase 1: run-record export) ---

    def serialize_span(self, span: TraceSpan | None = None, _depth: int = 0) -> dict | None:
        """Recursively serialize a trace span (and its children) to a plain dict."""
        if span is None:
            span = self.root_span
        if span is None or _depth > 50:
            return None
        return {
            "span_id": span.span_id,
            "agent_name": span.agent_name,
            "operation": span.operation,
            "duration_ms": span.duration_ms,
            "tokens_in": span.tokens_in,
            "tokens_out": span.tokens_out,
            "status": span.status,
            "tool_calls": span.tool_calls,
            "children": [
                self.serialize_span(child, _depth + 1) for child in span.children
            ],
        }

    def serialize_logs(self) -> list[dict]:
        """Serialize all log entries to a flat list of plain dicts."""
        base_time = self.logs[0].timestamp if self.logs else 0
        return [
            {
                "t_offset_s": round(entry.timestamp - base_time, 3),
                "agent": entry.agent_name,
                "action": entry.action,
                "tools": entry.tool_calls,
                "tokens": entry.tokens_used,
                "output": entry.output_summary,
            }
            for entry in self.logs
        ]

    def serialize_metrics(self) -> dict:
        """Serialize aggregate run metrics to a plain dict."""
        m = self.metrics
        return {
            "total_duration_ms": m.total_duration_ms,
            "total_tokens": m.total_tokens,
            "total_cost_usd": m.total_cost_usd,
            "agents_invoked": m.agents_invoked,
            "tool_calls_made": m.tool_calls_made,
            "anomalies_flagged": m.anomalies_flagged,
            "recommendations_made": m.recommendations_made,
            "approvals_requested": m.approvals_requested,
            "approvals_granted": m.approvals_granted,
            "approvals_rejected": m.approvals_rejected,
        }
