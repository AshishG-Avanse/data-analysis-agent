# Architecture

---

## System Overview

A single-process local web app: a Next.js frontend talks to a FastAPI backend over HTTP on `localhost:8001`. The backend holds one uploaded file's data in server-process memory per session, runs a LangGraph-orchestrated generate→execute→inspect→retry loop against it for each question, and calls the Gemini API twice per question (once to generate analysis code, once to turn the resulting aggregate into a plain-language answer). No data leaves the local machine except the two Gemini calls, and those calls never carry raw row data — only schema/aggregate summaries (see "Data Privacy Boundary" below).

## Component Map

```
Browser (Next.js static export, served at :8001/app/)
    │  fetch()
    ▼
FastAPI app (src/api/)
    │  POST /api/sessions            → file-parsing + session store
    │  POST /api/sessions/{id}/questions → QA graph runner
    ▼
Session Store (in-process dict, src/tools/session_store.py)
    │  holds: pandas DataFrame, schema profile, warnings, conversation turns
    ▼
QA Graph (LangGraph, src/graph/)
    │
    ├──► Gemini API (code generation)         ←→ Gemini API (Google)
    ├──► Code Executor (isolated subprocess)   ←→ local filesystem (cached DataFrame)
    └──► Gemini API (result interpretation)    ←→ Gemini API (Google)
    │
    ▼
Structured Log (data/query_log.jsonl)  +  SQLite (data/agent.db, QueryRunRow)
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| Frontend (Next.js) | Upload UI, chat-style Q&A thread, collapsible code viewer, chart/table/cost rendering |
| API (FastAPI routers) | HTTP contract: upload a file, ask a question, fetch session state |
| Session Store | In-memory holder of the one active file's DataFrame, schema profile, and conversation turns |
| Agent Graph (LangGraph) | The per-question generate→execute→inspect→retry→answer loop |
| Tools | Pure functions: file parsing, schema profiling, subprocess code execution, the privacy guard, cost estimation, chart-spec derivation, the JSONL logger |
| LLM Client | Thin wrapper over the Gemini SDK, one instance per node-specific model |
| Storage | SQLite (`QueryRunRow`, minimal per-question record) + local file log + local upload files — all ephemeral/local, no cloud storage |

## Data Flow

1. Trigger: user uploads a CSV/XLSX file via the browser.
2. `POST /api/sessions` parses the file locally (pandas), extracts a `SchemaProfile` (columns/dtypes/aggregates only — see privacy section), stores the DataFrame + profile in the in-process session store, and returns a `session_id` + the schema readout to the browser.
3. User submits a question via `POST /api/sessions/{session_id}/questions`.
4. The QA graph runs: `generate_code` (Gemini call, prompt = schema profile + question + retry context) → `execute_code` (local subprocess against the real DataFrame) → guard/inspect (aggregate-only check) → on failure, loop back to `generate_code` with the error appended, up to `max_retries`; on success, `synthesize_answer` (Gemini call, prompt = the aggregate result + question) → `finalize`.
5. Output: a JSON response with the plain-language answer, the last successful code (only on success), an aggregate result (for chart/table rendering), and (Phase 2) cost estimate and chart/table specs. `finalize` also appends one JSONL log line and one `QueryRunRow` DB record.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Gemini API (code generation) | Turn schema + question into pandas code | Treated as a retryable failure within the loop; if the API itself is unreachable (not just a bad code attempt), the graph routes to `handle_error` and the API returns a generic "agent unavailable" error — never a silent fallback |
| Gemini API (result interpretation) | Turn the aggregate result into plain language | On failure, routes to `handle_error`; the user sees a clear error, not an invented answer |
| Local filesystem | Uploaded file storage (`data/uploads/<session_id>/`), SQLite file (`data/agent.db`), JSONL log (`data/query_log.jsonl`) | Disk-full / permission errors surface as a 500 with a clear message; never silently drop data |
| SQLite (via SQLAlchemy + Alembic) | Minimal per-question run record (`QueryRunRow`) | Same process as the app; if the DB file is locked/corrupt, the API returns a 500 rather than crashing the process |

## Data Privacy Boundary — No Raw Data to the LLM

This is a hard, non-negotiable constraint: **raw row data is never included in any prompt sent to the Gemini API.** Gemini is used ONLY for (a) generating pandas code and (b) interpreting an already-computed aggregate result. The analysis code itself always executes locally, against the real DataFrame, in an isolated subprocess — the LLM never sees a single data row.

### Exactly what is extracted at upload (`SchemaProfile`)

Computed once per upload by `src/tools/schema_profile.py`, entirely locally:

```json
{
  "row_count": 48213,
  "column_count": 7,
  "columns": [
    {"name": "region", "dtype": "object", "null_count": 0, "non_null_count": 48213},
    {"name": "revenue", "dtype": "float64", "null_count": 12, "non_null_count": 48201}
  ],
  "categorical_samples": {
    "region": ["North", "South", "East", "West"]
  },
  "numeric_summary": {
    "revenue": {"min": 0.0, "max": 98213.4, "mean": 4213.9, "std": 1893.2, "median": 3900.0}
  }
}
```

Rules for what may appear here:
- `categorical_samples` includes a column's distinct values ONLY when that column has **≤ 20 distinct values** (a genuinely categorical column) — this is a derived/aggregated fact (the distinct-value set), never a sample of raw rows, and is capped at 20 values.
- `numeric_summary` includes only aggregate statistics (min/max/mean/std/median) for numeric-dtype columns — never individual cell values.
- Free-text / high-cardinality columns (> 20 distinct values, non-numeric) contribute ONLY their name, dtype, and null counts — no values at all.
- No row is ever assembled or referenced by index in this structure.

### Exactly what is templated into each Gemini prompt

- **Code-generation prompt** (`src/prompts/codegen.md`): the `SchemaProfile` JSON above + the user's question text +, on a retry, the previously generated code and the resulting error text (code/errors are also schema-shaped, never data) + (Phase 2) prior question/answer text pairs from this session (text only, never data).
- **Interpretation prompt** (`src/prompts/interpret.md`): the guarded aggregate `execution_result` JSON (see guard below) + the original question text + (Phase 2) prior question/answer text pairs.

Nothing else is ever concatenated into a Gemini prompt. Neither prompt template ever receives the DataFrame object, a file path, or a row/record.

### The guard that enforces this at runtime

`src/tools/privacy_guard.py::assert_aggregate_only(result)` runs immediately after the subprocess executor returns a result, BEFORE that result is ever placed into the interpretation prompt or returned via the API. It rejects (raises `AggregateGuardError`, which the graph treats as a retryable execution failure) any result that:
- serializes to more than **50 KB**, or
- contains more than **20 rows** (i.e., looks like a list/DataFrame dump rather than an aggregate), or
- is not JSON-serializable (a raw DataFrame/Series object slipped through).

A code attempt that returns `df.to_dict()` or similar for a large DataFrame is caught here and never reaches Gemini — the graph retries with feedback telling the model to aggregate before returning.

### The regression test that would catch a leak

`tests/unit/tools/test_privacy_guard.py`:
1. Builds a fixture DataFrame with a "canary" cell value that exists ONLY in the raw rows (never in any aggregate/schema fact).
2. Renders the codegen and interpret prompt templates using the real `SchemaProfile`/`execution_result` builder functions against that fixture.
3. Asserts the canary value string never appears anywhere in either rendered prompt.
4. Separately, feeds a simulated large/raw-shaped result (> 20 rows) into `assert_aggregate_only` and asserts it raises `AggregateGuardError`.

This test must run in Phase 1's gate (`qa-graph-core` slice) and continue to pass in Phase 2 — any change to the prompt templates or the guard thresholds that lets a canary value leak through fails this test immediately.

## Stack

- **Language:** Python 3.11+ (backend, matches the existing `pyproject.toml` `requires-python`), TypeScript (frontend, Next.js — already scaffolded).
- **Agent framework:** LangGraph (already scaffolded in `src/graph/`) — a ReAct-style tool-use loop with a bounded retry edge (see `spec/agent.md`).
- **LLM provider + model:**
  - Provider: Google Gemini (`google-genai` SDK, already in `pyproject.toml`), auto-detected via `AGENT_GEMINI_API_KEY` per the existing `LLMClient`/provider-factory pattern.
  - Code generation node: `gemini-3.1-pro-preview` — higher-quality reasoning reduces the number of retries needed to produce correct pandas code, which matters more for total cost/latency than raw model speed here.
  - Result-interpretation node: `gemini-2.5-flash` — the input is a small aggregate JSON and the task is straightforward summarization; the cheaper/faster model is sufficient and keeps the per-query cost low.
  - Both model IDs are env-configurable (`AGENT_LLM_MODEL_CODEGEN`, `AGENT_LLM_MODEL_INTERPRET`) so they can be swapped without a code change, per `harness/patterns/tech-stack.md`'s model-naming rule.
- **Backend:** FastAPI (already scaffolded), served by `uvicorn`, run via `uv run python agent.py --run` (this repo's existing launcher — applies Alembic migrations, builds the frontend if `pnpm` is available, then starts uvicorn on port 8001).
- **Database + ORM:** SQLite (`data/agent.db`) + SQLAlchemy 2.0 + Alembic — appropriate here per `harness/patterns/tech-stack.md` because this is an explicitly local, single-user, ephemeral/prototype tool (not shared/production). Used only for a minimal per-question `QueryRunRow` record (Phase 2); Phase 1 keeps the existing generic `RunRow`-style table until Phase 2 introduces `QueryRunRow`.
- **Frontend:** Next.js 15 + React 19, static export (`output: 'export'`, `basePath: '/app'`) served by FastAPI's `StaticFiles` mount, per `harness/patterns/tech-stack.md`'s static-export rule. Charting via a lightweight React charting library (Recharts) added to `frontend/package.json` in Phase 2.
- **Data processing:** pandas (already available via the existing dependency set — added explicitly to `pyproject.toml`) + `openpyxl` for `.xlsx` reads.
- **Dependency management:** `uv` (Python, `pyproject.toml`), `pnpm` (frontend, already scaffolded).

| Key library | Version | Purpose |
|-------------|---------|---------|
| `pandas` | `>=2.2` | Local file parsing + all analysis code execution |
| `openpyxl` | `>=3.1` | `.xlsx`/`.xls` reading (pandas Excel engine) |
| `google-genai` | `>=2.9.0` (existing) | Gemini API calls (code-gen + interpretation) |
| `langgraph` | `>=0.1` (existing) | The generate→execute→inspect→retry graph |
| `structlog` | `>=24.1` (existing) | Structured stdout logging for every LLM call and question |
| `recharts` | `^2` | Phase 2 interactive chart rendering (frontend) |

**Avoid:** pandas `.query()`/`eval()` with untrusted strings executed outside the isolated subprocess (defeats the isolation); any direct `exec()`/`eval()` of generated code in the main FastAPI process (must always go through the subprocess executor); storing the uploaded file's raw rows in SQLite (only schema/aggregate/log records belong in the DB, per the privacy boundary above); any cross-session or cross-file joining logic (permanently out of scope).

## Deployment Model

Local long-running process only: `uv run python agent.py --run` applies Alembic migrations, builds the Next.js static export, and starts a single `uvicorn` process on port 8001 serving both the API and the static frontend at `/app/`. There is no separate deployment target — this is a tool the user runs on their own machine for the duration of one analysis session.
