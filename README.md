# Data Analysis Agent

> All commands below run from the **repo root** (this directory — no subdirectory to `cd` into, except where noted for the frontend).

A local, single-user agent: upload one CSV/Excel file, ask plain-English questions about it, and get a grounded, code-backed answer. For each question the agent iterates: generate pandas code (Gemini) → execute it locally against the real file → inspect the result → retry on failure (up to `AGENT_MAX_RETRIES`, default 3) → synthesize a plain-language answer (Gemini). **Raw row data is never sent to the LLM** — only schema/aggregate summaries (see `spec/architecture.md` → "Data Privacy Boundary").

## Phase 1 (current)

Upload → ask → real answer with the exact pandas code shown (collapsible). Charts, summary tables, cost-per-query, multi-turn conversation memory, and best-effort malformed-file handling are visible in the UI as clearly-labelled **Phase 2** stubs — not yet wired.

## Setup

```
cp .env.example .env
# edit .env and set AGENT_GEMINI_API_KEY=<your key>
uv sync
cd frontend && pnpm install && cd ..
```

## Run

```
uv run python agent.py --run
```

This applies Alembic migrations, builds the frontend (if `pnpm` is available), and starts the server.

| URL | What |
|-----|------|
| `http://localhost:8001/app/` | **UI** — upload a file, then ask questions |
| `http://localhost:8001/health` | API health check |
| `http://localhost:8001/docs` | Interactive API docs (Swagger) |

## Tests

```
uv run pytest tests/unit -q                              # no LLM key needed
uv run pytest tests/integration/test_phase1_qa.py -v      # requires AGENT_GEMINI_API_KEY in .env
cd frontend && pnpm build && npx playwright test tests/e2e/ --reporter=line   # e2e, requires the server running
```

## API surface (Phase 1)

- `POST /api/sessions` — upload a CSV/XLSX/XLS file (multipart), returns `session_id` + schema profile
- `GET /api/sessions/{session_id}` — fetch the current session's schema/state
- `POST /api/sessions/{session_id}/questions` — ask a question, returns a plain-language answer + the analysis code

Full contract: `spec/api.md`.

## Repo layout

```
src/
  api/            sessions.py, questions.py, health.py
  tools/          file_parser.py, schema_profile.py, session_store.py,
                   code_executor.py, exec_worker.py, privacy_guard.py
  graph/          QAState, nodes (generate_code/execute_code/synthesize_answer/give_up/handle_error/finalize)
  llm/            LLMClient + Gemini/Anthropic providers
  prompts/        codegen.md, interpret.md
frontend/         Next.js static export, served by FastAPI at /app
tests/
  unit/           no LLM key needed
  integration/    real Gemini key required (tests/integration/test_phase1_qa.py)
  e2e/            Playwright, against the live server
spec/             roadmap, architecture (incl. privacy boundary), agent graph, api, data, ui
```

## Environment variables

See `.env.example`. Key ones: `AGENT_GEMINI_API_KEY` (required), `AGENT_MAX_RETRIES` (default 3), `AGENT_EXEC_TIMEOUT_SECONDS` (default 15), `AGENT_LLM_MODEL_CODEGEN` / `AGENT_LLM_MODEL_INTERPRET` (override the default Gemini models).
