# API

---

## API Style

REST (JSON over HTTP), served by FastAPI at `http://localhost:8001`. Local single-user tool — no authentication (see "Authentication" below).

## Endpoints / Commands

### `POST /api/sessions`

**Purpose:** Upload one CSV/XLSX/XLS file, parse it locally, and start a new session. Replaces any existing session's data.

**Request:** `multipart/form-data` with a single `file` field.

**Response:**
```json
{
  "data": {
    "session_id": "b3f1...": "string",
    "filename": "sales.csv",
    "row_count": 48213,
    "column_count": 7,
    "schema_profile": { "...": "see spec/architecture.md → Data Privacy Boundary for the exact shape" },
    "warnings": []
  },
  "error": null
}
```
`warnings` is always `[]` in Phase 1 (best-effort malformed-file recovery is a Phase 2 capability — Phase 1 either parses a well-formed file cleanly or rejects an unreadable one, see below).

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | Unsupported file type (not CSV/XLSX/XLS), or the file is entirely unreadable (nothing salvageable) |
| 413 | File exceeds the configured maximum upload size |
| 500 | Unexpected internal error while parsing |

### `GET /api/sessions/{session_id}`

**Purpose:** Fetch the current state of a session — its schema profile and (Phase 2) its conversation history so far. Used by the frontend to recover state after a page reload within the same server sitting.

**Response:**
```json
{
  "data": {
    "session_id": "string",
    "filename": "string",
    "schema_profile": { "...": "..." },
    "warnings": [],
    "conversation_history": []
  },
  "error": null
}
```
`conversation_history` is always `[]` in Phase 1.

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | `session_id` unknown — no active session (e.g. after a server restart, or it was never uploaded) |

### `POST /api/sessions/{session_id}/questions`

**Purpose:** Ask one plain-English question about the active session's file. Runs the full generate→execute→inspect→retry→answer loop (`spec/agent.md`).

**Request:**
```json
{ "question": "What is the average revenue by region?" }
```

**Response (success):**
```json
{
  "data": {
    "question": "What is the average revenue by region?",
    "status": "completed",
    "answer": "The average revenue by region ranges from $3,900 (South) to $5,120 (West).",
    "code": "def analyze(df):\n    return df.groupby('region')['revenue'].mean().to_dict()",
    "retry_count": 1,
    "cost_estimate_usd": null,
    "chart_spec": null,
    "table": null
  },
  "error": null
}
```
`cost_estimate_usd`, `chart_spec`, and `table` are `null` in Phase 1 (those capabilities are stubbed on the frontend and not yet computed on the backend — see `spec/roadmap.md`). They are populated from Phase 2 onward; the response shape does not change between phases.

**Response (gave up after exhausting retries):**
```json
{
  "data": {
    "question": "...",
    "status": "gave_up",
    "answer": "I wasn't able to find a reliable answer to that question about your file. Try rephrasing it or asking something more specific.",
    "code": null,
    "retry_count": 3,
    "cost_estimate_usd": null,
    "chart_spec": null,
    "table": null
  },
  "error": null
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | `session_id` unknown — no active session |
| 400 | Empty/missing `question` |
| 500 | A fatal infrastructure failure (e.g. Gemini API unreachable) — `handle_error` path in `spec/agent.md`; response body carries a clear, generic `error` message, never a raw exception |

### `GET /health`

**Purpose:** Liveness check (already scaffolded).

**Response:** `{"data": {"status": "ok"}, "error": null}`

## Authentication

None. This is a local, single-user tool running on the user's own machine — there are no accounts, tokens, or multi-tenant access controls. The server is expected to be bound to `localhost` only.
