# Agent

---

## Agent Architecture Pattern

**Chosen: Graph (LangGraph)** — a bounded ReAct-style tool-use loop (`harness/patterns/agentic-ai.md` #5 Tool Use, #17 ReAct reasoning, #22 LLM-Generated Code Execution) with an explicit retry edge (#12 Exception Handling and Recovery). One question = one graph invocation. The loop is: generate code → execute it locally → inspect the result → on failure, retry with the error fed back (up to `max_retries`) → on success, synthesize a plain-language answer. This is the base ReAct loop described in `harness/patterns/agentic-ai.md` — no planning, reflection, or multi-agent coordination is warranted; the task (write code, run it, check it, retry) does not need anything heavier, so no "Agentic Stack Upgrade" phase is planned (see `spec/roadmap.md`).

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| `generate_code` | Gemini | `gemini-3.1-pro-preview` (env: `AGENT_LLM_MODEL_CODEGEN`) | Code correctness matters most here — a stronger model produces correct pandas code more often, cutting the number of retries (and total cost/latency) versus a faster/weaker model that fails more often |
| `synthesize_answer` | Gemini | `gemini-2.5-flash` (env: `AGENT_LLM_MODEL_INTERPRET`) | Input is a small aggregate JSON; the task is straightforward summarization — the cheap/fast model is sufficient and keeps per-query cost low |

**Fallback behaviour:** If the Gemini API itself is unreachable, times out, or returns an auth/rate-limit error (as opposed to the model simply producing broken code — that's a normal retryable loop iteration), the node sets `state["error"]` and the graph routes to `handle_error` → a clear, surfaced error message ("The analysis service is temporarily unavailable — try again.") — never a silent fallback and never an invented answer. There is no offline stub in the gated path; both nodes call the real Gemini API in every environment the gate runs in.

**Prompt strategy:** Both prompts are Markdown templates (`src/prompts/codegen.md`, `src/prompts/interpret.md`) loaded at runtime and rendered with an f-string/`.format()`-style substitution of the fields listed below — no few-shot examples needed for Phase 1 (may be added in Phase 2 if code-gen accuracy needs it). `generate_code` expects the model to return a single fenced Python code block (a function body operating on a variable named `df`); the executor extracts that block. `synthesize_answer` expects plain text (no structured output needed — the interpretation is prose).

---

## Tools & Tool Calling

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `execute_pandas_code` | Runs LLM-generated code against the real cached DataFrame, isolated from the main process | `code: str`, `dataframe_path: Path` (cached parquet for this session) | `{"success": bool, "result": <json-serializable aggregate> \| None, "error": str \| None}` | Spawns one subprocess per attempt; hard-killed on timeout (`AGENT_EXEC_TIMEOUT_SECONDS`, default 15s); no network access inside the subprocess |
| `assert_aggregate_only` | Privacy/size guard applied to every execution result before it can reach the interpretation prompt or the API response | `result: Any` | raises `AggregateGuardError` or returns the validated result unchanged | None (pure validation) — see `spec/architecture.md` → "Data Privacy Boundary" for exact thresholds |
| `extract_schema_profile` | Builds the `SchemaProfile` from a parsed DataFrame at upload time (not part of the per-question graph — runs once per session in the upload endpoint) | `df: pandas.DataFrame` | `SchemaProfile` dict (see `spec/architecture.md`) | None (pure function) |

**Tool selection strategy:** Not model-chosen — the graph is a fixed pipeline (`generate_code` always followed by `execute_code`), not an LLM-driven tool router. `execute_pandas_code` is always invoked after `generate_code`; there is no other tool for the model to pick.

**Tool failure handling:** `execute_pandas_code` failures (Python exception raised by the generated code, non-zero subprocess exit, or timeout) and `assert_aggregate_only` rejections are both treated identically by the graph: increment `retry_count`, capture the error text, and — if `retry_count < max_retries` — route back to `generate_code` with that error appended to the next prompt. Once `retry_count >= max_retries`, route to `give_up` (a plain failure message, no partial code/result surfaced).

---

## Agent State

```python
class QAState(TypedDict, total=False):
    # Identity
    session_id: str                      # set at invocation, keys the session store
    query_run_id: str                    # DB row id for this question (Phase 2 QueryRunRow; Phase 1 reuses RunRow)

    # Input
    question: str                        # the user's plain-English question
    schema_profile: dict                 # extracted once at upload, passed in per question (see architecture.md)
    conversation_history: list[dict]     # [{"question": str, "answer": str}, ...] prior turns this session
                                          # — Phase 1: always [] (memory capability not wired yet, see roadmap.md);
                                          #   Phase 2: populated from the session store

    # Loop data (populated progressively across generate/execute/inspect iterations)
    generated_code: str | None           # the most recent code attempt (Python source, operates on `df`)
    execution_result: dict | None        # aggregate JSON from the most recent execution attempt, post-guard
    execution_error: str | None          # error text from the most recent failed attempt (fed back on retry)
    retry_count: int                     # attempts made so far, starts at 0
    max_retries: int                     # configurable ceiling, default 3 (env: AGENT_MAX_RETRIES)

    # Output
    final_answer: str | None             # plain-language answer (success) or apology message (give_up)
    chart_spec: dict | None              # Phase 2 — derived deterministically from execution_result
    table_data: dict | None              # Phase 2 — derived deterministically from execution_result
    cost_estimate_usd: float | None      # Phase 2 — approximate, from token usage × configured pricing

    # Control
    status: str                          # "completed" | "gave_up" | "failed"
    error: str | None                    # set on a FATAL (infra) failure — distinct from a retryable code failure
```

---

## Nodes / Steps

### `generate_code`

**Reads from state:** `question`, `schema_profile`, `conversation_history`, `generated_code` (prior attempt, if any), `execution_error` (if retrying)

**Writes to state:** `generated_code`

**LLM call:** yes — `gemini-3.1-pro-preview`, prompt = `src/prompts/codegen.md` rendered with `schema_profile` JSON + `question` + (if `retry_count > 0`) the prior `generated_code` and `execution_error` + (Phase 2) `conversation_history`. Output format: a single fenced Python code block.

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API | `generate_content` (code-gen model) | Auth/network/rate-limit failure → fatal, sets `state["error"]`, routes to `handle_error`. A response that fails to contain an extractable code block → treated as a retryable code failure (same as an execution failure) |

**Behaviour:** Produces one candidate pandas code attempt per call. On the first call, the prompt has no retry context; on subsequent calls (routed back after a failed execution), the prompt includes the exact previous code and the exact error it produced, so the model can course-correct.

### `execute_code`

**Reads from state:** `generated_code`, `session_id` (to locate the cached DataFrame)

**Writes to state:** `execution_result`, `execution_error`, `retry_count` (incremented on failure)

**LLM call:** no

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Local subprocess (`execute_pandas_code`) | Runs `generated_code` against the cached DataFrame with a hard timeout | Exception/timeout/non-zero exit → sets `execution_error`, increments `retry_count` (retryable, not fatal) |
| `assert_aggregate_only` (in-process) | Validates the subprocess result is a small aggregate, never raw rows | Guard rejection → treated identically to an execution failure: sets `execution_error` (with guidance text), increments `retry_count` (retryable, not fatal) |

**Behaviour:** Runs the generated code in an isolated subprocess against the real, full DataFrame (never a sample). On any failure (Python exception in the generated code, non-zero exit, timeout, or a guard rejection because the result looks like raw data), the node records the error and increments `retry_count` — it does not itself decide whether to retry or give up; that is the following edge's job.

### `synthesize_answer`

**Reads from state:** `execution_result`, `question`, `conversation_history`

**Writes to state:** `final_answer`, `chart_spec` (Phase 2), `table_data` (Phase 2), `cost_estimate_usd` (Phase 2), `status`

**LLM call:** yes — `gemini-2.5-flash`, prompt = `src/prompts/interpret.md` rendered with the guarded `execution_result` JSON + `question` + (Phase 2) `conversation_history`. Output format: plain text.

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API | `generate_content` (interpretation model) | Failure here is fatal for this question (no retry loop on the interpretation step, since the underlying analysis already succeeded) — sets `state["error"]`, routes to `handle_error` |

**Behaviour:** Turns the already-validated small aggregate result into a plain-language answer that must reference the actual computed numbers (the prompt gives the model no other numeric source). Also computes the deterministic chart/table specs from `execution_result` and the approximate cost estimate from token usage (both Phase 2).

### `give_up`

**Reads from state:** `retry_count`, `max_retries`

**Writes to state:** `final_answer` (a fixed plain apology/failure message), `status = "gave_up"`

**LLM call:** no

**Behaviour:** Reached only when `retry_count >= max_retries` with no successful execution. Produces ONLY a plain failure message — no code, no partial result, no retry trail is ever surfaced to the user (though the attempt count is logged internally per `finalize`, below).

### `handle_error`

**Reads from state:** `error`, `session_id`

**Writes to state:** `status = "failed"`

**Behaviour:** The fatal-infra path (Gemini unreachable, subprocess launch itself failing, session not found). Logs the error with `session_id`/`query_run_id` context and terminates the graph; the API surfaces a clear, generic error — never an `HTTPException` raised out of the pipeline (render/return the state's error field per `harness/patterns/code.md`).

### `finalize`

**Reads from state:** everything above

**Writes to state:** none (terminal) — persists results

**Behaviour:** Appends one line to `data/query_log.jsonl` (timestamp, `session_id`, `question`, `status`, `retry_count`, `cost_estimate_usd`, `error`) and writes/updates the `QueryRunRow` (Phase 1: reuses the existing generic `RunRow` shape; Phase 2: migrates to a dedicated `QueryRunRow` — see `spec/data.md`). On success, also appends `{question, answer, code}` to the session's in-memory `conversation_history` (Phase 2).

---

## Graph / Flow Topology

```
START
  │
  ▼
generate_code ──(fatal LLM/API error)──► handle_error ──► END
  │
  ▼
execute_code ──(fatal: session/DataFrame missing)──► handle_error ──► END
  │
  ├──(success: valid aggregate)────────────────► synthesize_answer
  │
  ├──(failure, retry_count < max_retries)──────► generate_code   [loop]
  │
  └──(failure, retry_count >= max_retries)─────► give_up
                                                       │
synthesize_answer ──(fatal LLM/API error)──► handle_error ──► END
  │
  ▼
finalize ◄────────────────────────────────────── give_up
  │
  ▼
 END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| `generate_code` | `state["error"]` is not `None` (fatal Gemini failure) | `handle_error` |
| `generate_code` | otherwise | `execute_code` |
| `execute_code` | `state["error"]` is not `None` (fatal — e.g. session/DataFrame missing) | `handle_error` |
| `execute_code` | `execution_error` is `None` (execution + guard succeeded) | `synthesize_answer` |
| `execute_code` | `execution_error` is not `None` and `retry_count < max_retries` | `generate_code` |
| `execute_code` | `execution_error` is not `None` and `retry_count >= max_retries` | `give_up` |
| `synthesize_answer` | `state["error"]` is not `None` (fatal Gemini failure) | `handle_error` |
| `synthesize_answer` | otherwise | `finalize` |
| `give_up` | always | `finalize` |

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| **Within a run (one question)** | LangGraph state (`QAState`) | All in-progress loop data — code attempts, errors, retry count |
| **Across questions (session)** | In-process session store (`src/tools/session_store.py`), a `dict[session_id, SessionState]` | The cached DataFrame, `SchemaProfile`, upload warnings, and (Phase 2) `conversation_history` — held in server-process memory only, never persisted to disk beyond the uploaded file and the SQLite log record |
| **Across restarts** | None, by design | Nothing — restarting the server drops all sessions; the user re-uploads (see `spec/roadmap.md` → Out of Scope) |
| **Conversation** | `conversation_history: list[dict]` field on `SessionState`, threaded into `QAState` per question | Question/answer text pairs only (never data) — Phase 1: not yet wired (always empty, see the `> Assumed:` note in `spec/ui.md`); Phase 2: real, threaded into both prompts |

**Context window management:** Not a concern at this scale — a session's `conversation_history` is a handful of short Q&A text pairs per sitting, well within any Gemini context window. No summarization/truncation is planned; if a pathologically long session ever became an issue, the fix would be a simple sliding window (last N turns), not implemented now (no requirement to build ahead of need).

---

## Error Handling & Recovery

**Node-level:** Each node catches its own exceptions. `generate_code`/`synthesize_answer` distinguish a genuine API/infra failure (fatal → `state["error"]`) from a usable-but-wrong model output (handled by the normal retry path, not an exception). `execute_code` catches everything the subprocess can throw (exception, timeout, non-zero exit) and treats all of it as a retryable `execution_error`, never a fatal one.

**Graph-level (`handle_error` node):**
- Reads: `state["error"]`, `state["session_id"]`, `state["query_run_id"]`
- Updates the DB record: status → `"failed"`, `error_message` set
- Logs the error (structured, with `session_id`/`query_run_id` context) via `structlog`
- Terminates the graph — the API renders a clear, generic error message, never a bare `HTTPException` from inside the pipeline (`harness/patterns/code.md`)

**Resume / retry strategy:** No resume across HTTP requests — each question is one synchronous graph invocation that completes (successfully, given-up, or failed) within a single request/response cycle. The retry loop is entirely internal to that one invocation; there is no checkpointing across requests (see Concurrency Model below).

**Partial failure:** The retry loop itself IS the partial-failure handling — a failed code attempt never aborts the question, it retries with feedback up to `max_retries`. Only exhausting retries (→ `give_up`, a clean non-fatal end state) or a genuine infra failure (→ `handle_error`) end the loop without a real answer.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| **Trace** | One trace per question, one span per node (`generate_code`, `execute_code`, `synthesize_answer`, retries as repeated spans) | LangSmith (`LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY` in `.env`) |
| **LLM calls** | Prompt (schema-shaped, never raw data), completion, token counts, latency, model ID | LangSmith + structured `structlog` line per call |
| **Tool calls** | `execute_pandas_code` — code hash/length, success/error, latency, retry number | Structured log (`structlog`, stdout) |
| **Run outcome** | `status`, `retry_count`, `cost_estimate_usd`, error if any | `data/query_log.jsonl` + `QueryRunRow` (DB) |

Wired from Phase 1 — never deferred, per `harness/patterns/phases.md`.

---

## Concurrency Model

- **Run isolation:** One graph invocation per HTTP request; FastAPI/uvicorn handles requests independently. A per-session lock in the session store serializes access to that session's cached DataFrame (safety net against a double-submit from the same browser tab — this is a single-user local tool, not a high-concurrency service).
- **Parallel nodes within a run:** None — the loop is strictly sequential (generate → execute → inspect → maybe retry → synthesize). No node runs in parallel with another; there is no independent sub-work to parallelize.
- **Checkpointing:** None. Each question completes synchronously within one request; there is no long-running/paused execution requiring `SqliteSaver`/`PostgresSaver`-style checkpointing.

---

## Graph Assembly (`src/graph/agent.py`)

```python
from langgraph.graph import StateGraph, END
from graph.state import QAState
from graph.nodes import generate_code, execute_code, synthesize_answer, give_up, handle_error, finalize
from graph.edges import after_generate_code, after_execute_code, after_synthesize_answer

def _build_graph() -> StateGraph:
    g = StateGraph(QAState)
    g.add_node("generate_code", generate_code)
    g.add_node("execute_code", execute_code)
    g.add_node("synthesize_answer", synthesize_answer)
    g.add_node("give_up", give_up)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)

    g.set_entry_point("generate_code")

    g.add_conditional_edges(
        "generate_code", after_generate_code,
        {"execute_code": "execute_code", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "execute_code", after_execute_code,
        {
            "synthesize_answer": "synthesize_answer",
            "generate_code": "generate_code",   # retry loop
            "give_up": "give_up",
            "handle_error": "handle_error",
        },
    )
    g.add_conditional_edges(
        "synthesize_answer", after_synthesize_answer,
        {"finalize": "finalize", "handle_error": "handle_error"},
    )
    g.add_edge("give_up", "finalize")
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()

agentic_ai = _build_graph()
```
