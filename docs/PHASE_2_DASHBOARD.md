# Phase 2 — Streamlit Demo Dashboard

> The visual front door for AgentLedger. A Streamlit app that renders the
> run-record JSON from Phase 1 into the dashboard mockup: hero savings number,
> animated agent pipeline, anomaly cards, an interactive HITL approval gate, and
> the observability + evaluation strip. Supports **replay** (render a committed
> golden run, no API key, $0) and **live** (run the real pipeline, gated).

---

## 1. Purpose & context

Phase 1 made every run exportable as a self-contained JSON. Phase 2 renders it.

```
  runs/golden_q1_review.json  ──►  Streamlit dashboard  ──►  judges / wider audience
        (replay, default)              (this phase)

  live pipeline run  ──►  build_run_record (in-memory)  ──►  same dashboard
        (gated toggle)
```

The replay path is the load-bearing one: it needs no API key, never fails on
stage, costs nothing, and is what the public URL serves by default. Live mode is
an authenticity bonus, enabled only when a key + password are present.

---

## 2. Goals / non-goals

### Goals
1. A Streamlit app (`app.py`) that renders a run-record into the six dashboard
   sections from the approved mockup.
2. **Replay mode** — pick a committed golden run from `runs/`, render instantly.
3. **Live mode** — run the real ADK pipeline, build the record in-memory, render
   it; gated behind API-key presence + a password.
4. A **UI-native HITL approval gate** (Approve / Reject buttons) that does not
   depend on the terminal `Confirm.ask`.
5. Polished, dark/light-safe visuals matching the mockup (hero, pipeline row,
   severity-colored anomaly cards, recommendation cards with draft emails,
   observability trace + metrics, eval scorecard).
6. **Deploy-ready** structure (`.streamlit/config.toml`, documented secrets) so
   Phase 3 is just clicking "deploy".

### Non-goals (later phases)
- CSV/Excel upload + column mapping + session isolation (**Phase 2.5** — seam left).
- Actual deployment to Streamlit Community Cloud (**Phase 3**).
- Real-time token-by-token streaming of agent output during live runs (live mode
  runs to completion behind a spinner in v1; streaming is a stretch).

---

## 3. App structure

```
app.py                       # Entry: page config, sidebar, mode routing, HITL state
dashboard/
  __init__.py
  loader.py                  # discover + load run-record JSON files from runs/
  live.py                    # async wrapper: run pipeline live, build record in-memory
  render.py                  # the six section renderers (pure: take dict, draw UI)
  styles.py                  # CSS injection + severity/action color + icon helpers
.streamlit/
  config.toml                # theme (committed, deploy-ready)
  secrets.toml.example       # documents GOOGLE_API_KEY + APP_PASSWORD (real one gitignored)
```

`render.py` functions are **pure renderers**: they accept the run-record dict (or
a slice of it) and draw Streamlit components. They never run agents or hit the DB,
so both replay and live paths render through identical code — guaranteeing the
live output looks exactly like the golden run.

---

## 4. Section-by-section render spec

All six map 1:1 to the approved mockup. Field paths reference the v1.0 schema.

### 4.1 Hero
- Left: `query` + a small "AgentLedger — SaaS cost review" label.
- Right: big number = `totals.identified_annual_savings_usd` (formatted
  `$73,200`), label "Identified annual savings".
- Source: `query`, `totals`.

### 4.2 Agent pipeline row
- One node per stage: ingestion → anomaly → negotiation → reporting (fixed order).
- Each node shows: name, an icon, status (`✓ done` / running / queued), and a
  one-line stat (e.g. tool count or token count) derived from `pipeline.agents[]`
  and `trace`.
- **Animation** (see §6): in replay, nodes reveal/illuminate sequentially; in
  live, they update as the run progresses (or fill in on completion).
- Source: `pipeline.agents[]`, `trace.root.children`.

### 4.3 Anomaly findings
- A responsive grid of cards, one per item in `anomalies[]`.
- Card content varies by `type`:
  - `spend_spike` → vendor, `previous_amount → current_amount` (+`change_pct`%),
    a tiny prev-vs-current bar. Left border colored by `severity`.
  - `duplicate_tools` → category, `vendors[]` joined, `total_monthly_cost`.
  - `upcoming_renewal` → vendor, `days_until_renewal`, `renewal_date`.
- Severity → color: high = red, medium = amber, low = blue (see styles.py).
- Source: `anomalies[]`.

### 4.4 Recommendations + HITL gate
- One card per item in `recommendations[]`:
  - `action` as a colored badge, `annual_savings_usd` on the right.
  - First line of intent + an expander revealing `draft_email` and the full
    `recommendation_text`.
- Below the cards: the **approval gate** — Approve all / Reject buttons that
  write to `st.session_state` and show the resulting state. In replay, the
  recorded `hitl.granted` is shown as the default/initial state.
- Source: `recommendations[]`, `hitl`.

### 4.5 Observability
- Trace: render `trace.root` as a nested tree (agent → operation, with
  `duration_ms` and tokens). Use indented `st.markdown` or `st.expander` tree.
- Metric cards row: latency (`metrics.total_duration_ms`), tokens
  (`metrics.total_tokens`), cost (`metrics.total_cost_usd`), tool calls.
- Optional: logs table from `logs[]` in an expander.
- Source: `trace`, `metrics`, `logs`.

### 4.6 Evaluation scorecard
- Detection: precision / recall / F1 from `evaluation.detection` (metric cards or
  a small gauge/bar). Optionally list TP/FP/FN in an expander.
- Judge: `evaluation.judge.average_score` as a prominent score (e.g. 4.7/5) +
  per-vendor `scores` in an expander.
- If `evaluation` is empty (live run with judge skipped), show detection only and
  a muted "judge not run" note.
- Source: `evaluation`.

---

## 5. Mode routing & security

Sidebar controls:
- **Mode**: Replay (default) | Live.
- Replay: a selectbox listing `runs/golden_*.json` (via `loader.py`).
- Live: a query text input + "Run pipeline" button.

### Live-mode gating (protects the API credit)
Live mode is only available when **both**:
1. `GOOGLE_API_KEY` is present (from `.env` locally, or `st.secrets` on Cloud), and
2. the user enters an `APP_PASSWORD` matching `st.secrets["APP_PASSWORD"]`.

On the public Cloud deployment we simply **omit `APP_PASSWORD`/key from secrets**,
so the live toggle is hidden and the app is replay-only — bulletproof and free.
Locally, `.env` provides the key and live is enabled (password optional locally).

| Environment | Key present? | Live toggle | Default view |
|---|---|---|---|
| Local dev | yes (.env) | enabled | replay (golden) |
| Public Cloud (recommended) | no | hidden | replay only |
| Cloud + secrets (optional) | yes + password | enabled behind password | replay |

---

## 6. Live execution & animation details

### 6.1 Running the pipeline from Streamlit
- `dashboard/live.py` exposes `run_live(query) -> dict`:
  - snapshots `vendor_history` max id,
  - calls `run_agent_pipeline(query, tracer, enable_hitl=False)` via
    `asyncio.run(...)` (Streamlit's script thread has no running loop; add
    `nest_asyncio` only if a conflict surfaces),
  - calls `build_run_record(..., run_judge=False)` (see §8) for a fast (~15s) live
    record — detection metrics included (free), judge skipped for speed.
- Wrapped in `st.spinner("Running the agent pipeline…")`. v1 renders on completion;
  per-agent live updates are a stretch goal.
- **HITL**: live runs use `enable_hitl=False` (no terminal prompt). The dashboard's
  own Approve/Reject buttons (§4.4) provide the gate in the UI instead. The
  terminal HITL in `main.py` is untouched.

### 6.2 Replay animation
- A stepped reveal: `st.session_state.step` advances the visible pipeline stage,
  driven by a "Play" button or a short auto-advance loop using placeholders
  (`st.empty()`) + `time.sleep`. Falls back gracefully to full static render so
  the dashboard is never blank.

---

## 7. Visual approach

- **Theme**: `.streamlit/config.toml` sets base, primary color (a finance green),
  font. Auto-respects light/dark.
- **Cards/badges/hero**: targeted custom CSS injected once via `styles.py`
  (`st.markdown(..., unsafe_allow_html=True)`), mirroring the mockup (0.5px
  borders, rounded cards, severity left-borders, colored action badges). Kept
  minimal — layout uses native `st.columns`/`st.container`; CSS only for the
  card chrome the mockup needs.
- **Charts**: Streamlit-native (`st.bar_chart`/`st.metric`) or Altair (already a
  Streamlit dep — no new heavy package). The spend-spike mini-bar and the
  precision/recall display use these. **No Plotly** (avoids a large dependency).
- **Icons**: Streamlit Material icon shortcodes (`:material/...:`); no external
  icon font needed.
- **Number formatting**: all currency via `f"${n:,.0f}"`, percentages to 1 decimal
  — never raw floats.

---

## 8. Small additive touch-up to Phase 1 (run_record.py)

Live mode wants detection metrics (free) without the slow judge. Currently
`build_run_record(run_evaluation=...)` couples both. Phase 2 adds a minimal,
**additive** refinement:

- Replace/augment with two flags: `run_detection: bool = True`,
  `run_judge: bool = True`. Detection (deterministic, free) computes whenever
  `run_detection`; the LLM judge runs only when `run_judge`.
- `run_evaluation` retained as a back-compat alias (both default True), so the
  Phase 1 `--export` golden capture is unchanged.

This stays within our presentation-layer work and does not touch the locked agent
architecture (`agent_definitions.py`, `prompts.py`, `agent_tools.py`, MCP server).

---

## 9. File / directory changes

| Path | Change | Invasive? |
|---|---|---|
| `app.py` | **new** — Streamlit entry + routing | no |
| `dashboard/` (loader, live, render, styles, `__init__`) | **new** | no |
| `.streamlit/config.toml` | **new** — theme | no |
| `.streamlit/secrets.toml.example` | **new** — documents secrets | no |
| `observability/run_record.py` | **additive** — `run_detection`/`run_judge` flags | no (back-compat) |
| `requirements.txt` | `streamlit>=1.38.0` (already added) | no |
| `.gitignore` | add `.streamlit/secrets.toml` | no |
| `docs/PHASE_2_DASHBOARD.md` | **new** — this doc | no |

**Untouched (locked scope):** `agents/*`, `tools/agent_tools.py`,
`mcp_server/server.py`. `main.py` terminal flow unchanged (live UI bypasses its
HITL by passing `enable_hitl=False`).

---

## 10. Acceptance criteria

1. `streamlit run app.py` launches; replay mode loads `runs/golden_q1_review.json`
   and renders all six sections with no API key set.
2. Hero shows the correct savings total; anomaly cards reflect all
   `anomalies[]`; recommendation cards expand to show draft emails; observability
   shows the trace tree + metric cards; eval shows F1 + judge score.
3. Approve / Reject buttons update visible state without errors.
4. With a key + password configured, Live mode runs the pipeline (~15s, judge
   skipped), builds a record in-memory, and renders it through the same code.
5. Without a key, the Live toggle is hidden; the app is fully usable in replay.
6. Layout is readable in both light and dark mode; all numbers are formatted.
7. No regression to `python main.py` / `--eval` / `--export`.

---

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| `asyncio.run` conflicts inside Streamlit | Run in script thread (no active loop); add `nest_asyncio` only if needed |
| Live run slow / costs tokens | Default live to `run_judge=False` (~15s); replay is the primary path |
| Custom CSS breaks in dark mode | Use Streamlit theme variables / tested color pairs; verify both modes |
| Public URL abused for live runs | Live hidden unless key+password in secrets; public deploy ships neither |
| Streamlit Cloud Python version vs google-adk | Verified in Phase 3; replay path needs no adk import at all |
| Animation jank under Streamlit reruns | Stepped reveal degrades to static full render |

---

## 12. Out of scope (next phases)

- **Phase 2.5** — CSV/Excel upload, column mapping, session-isolated temp DB
  (`loader.py` leaves a seam for an alternate data source).
- **Phase 3** — Streamlit Community Cloud deployment: push secrets config, verify
  `google-adk` install on Cloud Python, set replay-only public default, capture
  the public URL for the Kaggle writeup.
