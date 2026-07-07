# Data Model

---

## Storage Technology

SQLite (`data/agent.db`, via SQLAlchemy 2.0 + Alembic) for a minimal per-question run record, plus a local append-only JSONL log file (`data/query_log.jsonl`) for the simple, human-readable query/answer log the product explicitly asks for. The uploaded file's parsed data, its schema profile, and the running conversation are held only in server-process memory (never written to SQLite or disk beyond the original uploaded file) — this is an explicit, permanent design choice (see `spec/roadmap.md` → Key Constraints and `spec/agent.md` → Memory & Context), not a placeholder to be replaced later. See `spec/architecture.md` → "Stack" for why SQLite is appropriate for this explicitly local, single-user, ephemeral tool.

## Entities

### Entity: QueryRunRow (SQLite — Phase 1 uses the existing generic `RunRow` shape; Phase 2 introduces this dedicated shape)

Represents one asked question and its outcome. This is the durable half of the query/answer log (the JSONL file below is the other, user-facing half — see `spec/capabilities/answer-synthesis-and-conversation.md`).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | string (UUID) | yes | Primary key |
| session_id | string | yes | The in-memory session this question belonged to (not a foreign key to a persisted `Session` row — sessions are not persisted, see below) |
| question | text | yes | The user's plain-English question |
| status | text | yes | `completed` \| `gave_up` \| `failed` |
| retry_count | integer | yes | Number of code-generation attempts made |
| generated_code | text | no | The last successful code attempt (null if `gave_up`/`failed`) |
| final_answer | text | no | The plain-language answer (or the fixed apology message if `gave_up`) |
| cost_estimate_usd | float | no | Approximate combined cost of this question's Gemini calls |
| error_message | text | no | Set only when `status = "failed"` (a fatal infra error, not a normal retry) |
| created_at | timestamp | yes | When the question was submitted |
| updated_at | timestamp | yes | When the record was last updated |

### Entity: SessionState (in-memory only — NOT a database table)

Represents the one active uploaded file for a server sitting. Lives entirely in a `dict[session_id, SessionState]` in the FastAPI process (`src/tools/session_store.py`); never persisted to SQLite or disk beyond the raw uploaded file itself, and never survives a server restart.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| session_id | string (UUID) | yes | Generated on upload; the key into the in-memory store |
| filename | string | yes | Original uploaded filename |
| dataframe | in-memory pandas DataFrame | yes | The parsed dataset — never serialized to the log or the DB |
| schema_profile | structured data (see `spec/architecture.md` → Data Privacy Boundary) | yes | Columns/dtypes/aggregates only, no raw rows |
| warnings | list of strings | no | Populated when the source file had malformed/unreadable content (Phase 2) |
| conversation_history | list of `{question, answer}` | no | Populated as questions are answered in this sitting (Phase 2); empty list in Phase 1 |
| created_at | timestamp | yes | When the file was uploaded |

### Relationships

- `QueryRunRow.session_id` references a `SessionState.session_id` that exists only in memory — there is no DB-level foreign key or referential integrity, and a `QueryRunRow` can outlive its originating in-memory session (e.g. after a restart, the log/DB rows remain but the session itself is gone; the user must re-upload before asking anything new).
- One `SessionState` has exactly one active uploaded file at a time; uploading again replaces it in place rather than creating a second concurrent session (single-user, single-file, always).
- One `SessionState` has zero or more `QueryRunRow` records (one per question asked during that sitting).

## Data Lifecycle

- **Uploaded file:** written to `data/uploads/<session_id>/<filename>` on upload; parsed into the in-memory `SessionState`. Not automatically deleted — this is a local prototype tool; cleanup, if ever needed, is a manual/out-of-scope concern (no requirement to auto-expire).
- **SessionState:** created on upload, replaced on a new upload, and entirely lost on server restart. Never written to durable storage itself.
- **QueryRunRow:** created once per question, updated once when the graph finishes (`finalize` node) — never updated again afterward. Never deleted automatically (no audit-trail/retention requirement beyond "it exists locally").
- **JSONL log line:** appended once per question, immediately at `finalize`. Append-only — never edited or removed by the application.

## Sensitive Data

- The uploaded file may contain the user's own real business/personal data. It is processed entirely locally (parsing, execution) and is never transmitted to the Gemini API in raw form — only the derived `schema_profile` and aggregate `execution_result` (see `spec/architecture.md` → Data Privacy Boundary) ever leave the local process, and only to the Gemini API itself.
- `AGENT_GEMINI_API_KEY` (and any other provider key) is read from `.env` (gitignored) and is never logged, echoed, or written to `data/query_log.jsonl` or the SQLite DB.
- No other secrets or PII fields are deliberately collected; this is a single local user with no accounts.
