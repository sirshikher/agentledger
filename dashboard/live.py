"""
AgentLedger Dashboard Live Runner
====================================
Runs the real ADK pipeline from inside Streamlit and builds an in-memory
run-record, identical in shape to the Phase 1 exported JSON, so it renders
through the same dashboard/render.py code as replay.
"""

import asyncio
import uuid

from config import DB_PATH
from main import run_agent_pipeline
from observability.tracer import Tracer
from observability.run_record import (
    build_run_record,
    get_vendor_history_max_id,
    get_recommendations_since,
)


def run_live(query: str) -> dict:
    """
    Run the pipeline synchronously (for a Streamlit script run) and return a
    fully-built run-record dict. HITL is disabled here — the dashboard's own
    Approve/Reject buttons provide the gate instead. The judge is skipped for
    speed; detection metrics (free, deterministic) are still computed.
    """
    return asyncio.run(_run_live_async(query))


async def _run_live_async(query: str) -> dict:
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    tracer = Tracer(run_id=run_id)

    recs_since_id = get_vendor_history_max_id(DB_PATH)

    results = await run_agent_pipeline(
        user_query=query,
        tracer=tracer,
        enable_hitl=False,
    )

    tracer.finalize()
    this_run_recs = get_recommendations_since(DB_PATH, recs_since_id)

    return await build_run_record(
        query=query,
        mode="live",
        results=results,
        tracer=tracer,
        db_path=DB_PATH,
        recommendations=this_run_recs,
        run_detection=True,
        run_judge=False,
    )
