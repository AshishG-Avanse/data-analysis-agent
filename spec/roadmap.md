# Roadmap

---

## What This Agent Does

A local, single-user data analysis agent. The user uploads one CSV or Excel file, then asks a series of plain-English questions about it in a single sitting. For each question the agent writes analysis code, runs it locally against the real data, inspects the result, and retries with a different approach if it fails — before answering with plain language, key numbers, a chart, a summary table, and the exact code (collapsible) that produced the answer.

## Who Uses It

A single local user (analyst, PM, founder — anyone with a spreadsheet and a question) who wants to interrogate one file conversationally without writing pandas code themselves. One person, one browser tab, one file at a time.

## Core Problem Being Solved

Answering ad-hoc questions about a CSV/Excel file today means opening a notebook or spreadsheet and hand-writing formulas or pandas code. This agent removes that step: ask in English, get a grounded, code-backed answer, in the same sitting.

## Success Criteria

- [ ] A user can upload a real CSV/Excel file (a few MB) and get a correct schema read back within seconds.
- [ ] A user can ask a plain-English question and receive an answer whose key numbers are provably computed from the FULL uploaded dataset (not a truncated sample), backed by real, visible pandas code.
- [ ] When the first analysis attempt fails, the agent retries with a different approach (up to a configurable limit) without the user needing to rephrase anything.
- [ ] No raw row data ever appears in any prompt sent to the LLM (verified by an automated regression test, not just code review).
- [ ] A user can ask multiple follow-up questions in one sitting and get answers that account for earlier turns.
- [ ] Every query is visible afterward as one line in a local log file with an approximate cost.

## What This Agent Does NOT Do (Out of Scope)

- **Never joins or compares multiple files.** One file per session, permanently — not a Phase 1 limitation, a permanent design constraint. A new upload replaces the session, it never adds a second dataset.
- No cross-session / cross-restart persistence. Conversation history and the parsed file live only for the current server session; restarting the server clears everything and the user re-uploads.
- No proactive behavior: no auto-profiling, no unsolicited insights or suggestions — the agent answers only the question asked.
- No external integrations (no Slack, email, export, webhook triggers). Standalone local tool.
- No user accounts, auth, or multi-user support — single local user, no login.
- No production-grade reliability guarantee: this is an experimental/prototype-grade tool. Imperfect answers on hard questions are acceptable; there is no full audit trail beyond the basic query log.
- No streaming/step-by-step progress UI — a single spinner while a question is processed, no step counter, no token-by-token streaming.

## Key Constraints

- **Scale:** small files only (a few MB, tens of thousands of rows at most). Latency is not a concern — correctness on the one file in front of the user matters more than speed.
- **Privacy:** raw row data must never be sent to the LLM API — only schema/summary/aggregate information (see `spec/architecture.md` → "Data Privacy Boundary"). This is a hard constraint, not a preference.
- **Reliability bar:** experimental/prototype. A best-effort answer after retries, or a plain failure message, are both acceptable outcomes — there is no requirement to always succeed.
- **Cost visibility:** every query shows an approximate USD cost estimate; exact billing accuracy is not required.
- **Single sitting:** the whole system (uploaded data, parsed frame, conversation) is ephemeral in-process memory — no requirement to survive a restart.

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** It must work perfectly the first time the user tests it. Its backend is minimal but REAL on the one core path. Its frontend is visually complete: real UI for the one working path PLUS clearly-labelled NON-FUNCTIONAL stubs for everything coming later.

### Phase 1 — Upload, Ask, Answer (with real retry loop)

- **Goal:** The user uploads one CSV/Excel file, asks one question in plain English, and sees a plain-language answer with the actual pandas code that produced it (collapsible). Parsing is real, the retry loop (generate → execute → inspect → retry, up to a configurable N, default 3) is real, and every LLM call hits the real Gemini API using the key in `.env`. Charts, tables, cost display, multi-turn conversation memory, and best-effort malformed-file handling are all visible as clearly-labelled, non-functional stubs — not wired yet.
- **Independent slices (parallel build units):**
  - `file-parsing` (backend) — pure local parsing + schema-profile extraction, no API/session wiring. Deps: none.
  - `session-store-and-upload-api` (backend) — in-memory session store + `POST /api/sessions` upload endpoint; calls into `file-parsing`'s functions. Deps: `file-parsing` (calls its parse/profile functions directly).
  - `qa-graph-core` (backend) — the LangGraph state/nodes/edges/assembly for the generate→execute→inspect→retry loop, the subprocess code executor, the privacy guard, and the two prompt templates. Built and unit-tested against a fixture schema profile — does not need the real upload path to compile or to be tested in isolation. Deps: none.
  - `questions-api-and-wiring` (backend) — `POST /api/sessions/{session_id}/questions`; wires the session store to the compiled graph; settings additions (model/retry/timeout env vars); LangSmith + structured logging wiring. Deps: `session-store-and-upload-api`, `qa-graph-core` (calls both).
  - `frontend-upload-and-chat-ui` (frontend) — upload area, chat-style Q&A thread, collapsible code viewer (all real), plus clearly-labelled stub placeholders for chart, table, cost display, and malformed-file warnings; Playwright e2e smoke test. Deps: none (builds against the documented `spec/api.md` contract).
- **Key surfaces / files:**
  - `file-parsing`: `src/tools/file_parser.py`, `src/tools/schema_profile.py`, `tests/unit/tools/test_file_parser.py`, `tests/unit/tools/test_schema_profile.py`
  - `session-store-and-upload-api`: `src/tools/session_store.py`, `src/domain/session.py`, `src/api/sessions.py`, `tests/unit/api/test_sessions.py`
  - `qa-graph-core`: `src/graph/state.py`, `src/graph/nodes.py`, `src/graph/edges.py`, `src/graph/agent.py`, `src/tools/code_executor.py`, `src/tools/exec_worker.py`, `src/tools/privacy_guard.py`, `src/prompts/codegen.md`, `src/prompts/interpret.md`, `src/llm/providers/gemini.py` (extended), `tests/unit/graph/test_agent.py`, `tests/unit/tools/test_privacy_guard.py`
  - `questions-api-and-wiring`: `src/api/questions.py`, `src/domain/question.py`, `src/config/settings.py` (extended), `src/observability/events.py` (extended), `src/graph/runner.py` (extended), `tests/integration/test_phase1_qa.py`, `tests/fixtures/sales_1000.csv`
  - `frontend-upload-and-chat-ui`: `frontend/src/app/page.tsx`, `frontend/src/app/components/*`, `tests/e2e/phase1_qa.spec.ts`
- **Gate command:**
  `uv run alembic upgrade head && uv run alembic current && uv run pytest tests/unit tests/integration/test_phase1_qa.py -q`
  followed by `cd frontend && pnpm build` and `npx playwright test tests/e2e/ --reporter=line` against `uv run python agent.py --run` serving `http://localhost:8001/app/`.
  - `tests/integration/test_phase1_qa.py` calls the real Gemini API (key from `.env`) end-to-end against `tests/fixtures/sales_1000.csv` — a 1,000-row fixture engineered so the first 5 rows carry a deliberately anomalous value; the test asserts the returned answer's key number matches the TRUE full-dataset aggregate, not the anomalous first-rows value, proving the generated code runs against the whole file rather than a truncated sample.
  - `tests/unit/tools/test_privacy_guard.py` asserts (a) a simulated raw-row-shaped result is rejected by the aggregate guard, and (b) rendering the codegen/interpret prompt templates with a fixture DataFrame never contains any "canary" cell value that exists only in the raw rows.
- **How the user tests it (handoff seed):**
  1. `copy .env.example .env` and fill in `AGENT_GEMINI_API_KEY` (once, already done per intake).
  2. `uv run python agent.py --run` from the repo root.
  3. Open `http://localhost:8001/app/`.
  4. Upload a small CSV or Excel file (drag-drop or browse).
  5. Confirm the schema readout (columns, row count) appears — this is real.
  6. Type a question (e.g. "what is the average of column X?") and submit.
  7. Confirm: a spinner shows while processing (no step counter), then a plain-language answer with the actual number appears, with a "View code" toggle that expands to show the real pandas code that produced it.
  8. Confirm the following areas are visibly present but labelled as NOT YET FUNCTIONAL: a chart placeholder, a summary-table placeholder, a cost-per-query placeholder, and a file-warnings banner area. None of these do anything yet — that is expected, not a bug.
  9. Ask a follow-up question — it will be answered independently, without using the first question's context (multi-turn memory is a labelled Phase 2 feature; the chat thread visually stacks past Q&A but the backend does not yet feed prior turns into the prompt).

### Phase 2 — Memory, Rich Results & Robust Ingestion

- **Goal:** Turn the four Phase 1 stubs into real features: multi-turn conversation memory (follow-up questions use prior Q&A), interactive charts and summary tables from the aggregate result, a visible approximate cost per query plus a structured local query/answer log, and best-effort handling of malformed/unsupported files with visible warnings. Completes all 4 capabilities.
- **Independent slices (parallel build units):** the first four are pure, self-contained additions that do not touch the graph or the questions endpoint, so they build fully in parallel; the fifth slice is the only one that wires their outputs together and is declared dependent on all four.
  - `conversation-memory-store` (backend) — extend the session store with a conversation-turn list and an append method; extend `GET /api/sessions/{session_id}` to return it. Deps: none.
  - `cost-and-logging` (backend) — token-usage-based cost estimator, per-model approximate pricing config, append-only `data/query_log.jsonl` writer, and the `QueryRunRow` SQLite table + Alembic migration. Deps: none.
  - `malformed-file-handling` (backend) — extend `file-parsing`'s parse function (owned solely by this slice, in place) with best-effort partial-read recovery (corrupt rows, unreadable sheets) and a structured `warnings: list[str]` result. Deps: none.
  - `chart-spec-derivation` (backend) — pure, standalone deterministic result-shape → chart-spec/table-spec mapping function, not yet wired to any endpoint. Deps: none.
  - `phase2-integration` (backend) — the ONLY slice touching `graph/nodes.py`, `graph/state.py`, `prompts/*.md`, and `api/questions.py`: threads `conversation_history` into both prompts, calls the cost estimator and chart-spec derivation from `finalize`, appends to the session's conversation history and the JSONL log, and updates the questions/sessions endpoints to return the now-real values. Deps: `conversation-memory-store`, `cost-and-logging`, `malformed-file-handling`, `chart-spec-derivation` (calls all four's functions) — this slice is serialized after the other four land.
  - `frontend-rich-results` (frontend) — wire the chart/table/cost/warnings placeholders from Phase 1 into real components rendering server-provided `chart_spec`/`table`/`cost_estimate_usd`/`warnings`; extend the e2e suite. Deps: none (builds against the already-documented `spec/api.md` response shape, which does not change between phases — only the previously-`null` fields become populated).
- **Key surfaces / files:**
  - `conversation-memory-store`: `src/tools/session_store.py`, `src/domain/session.py`
  - `cost-and-logging`: `src/tools/cost_estimator.py`, `src/tools/query_log.py`, `src/db/models.py` (add `QueryRunRow`), `alembic/versions/0002_query_run.py`, `src/config/settings.py` (pricing env vars), `tests/unit/tools/test_cost_estimator.py`, `tests/unit/tools/test_query_log.py`
  - `malformed-file-handling`: `src/tools/file_parser.py`, `tests/unit/tools/test_file_parser_malformed.py`, `tests/fixtures/corrupt_rows.csv`, `tests/fixtures/protected.xlsx`
  - `chart-spec-derivation`: `src/tools/chart_spec.py`, `tests/unit/tools/test_chart_spec.py`
  - `phase2-integration`: `src/graph/state.py`, `src/graph/nodes.py`, `src/prompts/codegen.md`, `src/prompts/interpret.md`, `src/api/questions.py`, `src/api/sessions.py`, `tests/integration/test_conversation_memory.py`
  - `frontend-rich-results`: `frontend/src/app/components/Chart.tsx`, `frontend/src/app/components/ResultTable.tsx`, `frontend/src/app/components/CostBadge.tsx`, `frontend/src/app/components/WarningsBanner.tsx`, `tests/e2e/phase2_rich_results.spec.ts`
- **Gate command:**
  `uv run alembic upgrade head && uv run alembic current && uv run pytest tests/unit tests/integration -q`
  followed by `cd frontend && pnpm build` and `npx playwright test tests/e2e/ --reporter=line` against `uv run python agent.py --run` at `http://localhost:8001/app/`.
  - Integration tests call the real Gemini API using `.env` keys; `test_conversation_memory.py` asks a first question, then a follow-up that only makes sense with the first answer's context (e.g. "and what about just the top category?"), and asserts the second answer's generated code/prompt reflects the first turn.
  - `test_file_parser_malformed.py` feeds a CSV with deliberately corrupt rows and asserts the file is NOT hard-rejected — it parses the salvageable rows and returns a non-empty `warnings` list.
- **How the user tests it (handoff seed):**
  1. `uv run python agent.py --run`, open `http://localhost:8001/app/`.
  2. Upload the same file as before, ask a question, then ask a follow-up that references the previous answer (e.g. "now break that down by category") — confirm the answer uses the prior context correctly.
  3. Confirm a chart now renders for a result shaped as categories + numbers, and a summary table renders the aggregate result rows.
  4. Confirm a cost estimate (e.g. "~$0.002") now appears next to each answer.
  5. Upload a deliberately messy CSV (some broken rows) and confirm the file still loads with a visible warning banner listing what was skipped, instead of a hard rejection.
  6. Open `data/query_log.jsonl` and confirm one JSON line was appended per question asked, with timestamp, question, status, retry count, and cost.
