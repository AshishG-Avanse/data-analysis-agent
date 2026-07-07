from typing import TypedDict


class QAState(TypedDict, total=False):
    """State threaded through the generate -> execute -> inspect -> retry loop.

    See spec/agent.md -> "Agent State" for the authoritative field list and
    the rationale behind each one.
    """

    # Identity
    session_id: str                      # set at invocation, keys the session store
    query_run_id: str                    # DB row id for this question

    # Input
    question: str                        # the user's plain-English question
    schema_profile: dict                 # extracted once at upload, passed in per question
    conversation_history: list[dict]     # [{"question": str, "answer": str}, ...] prior turns
                                          # Phase 1: always [] (memory not wired yet)
    dataframe_path: str                  # path to the cached DataFrame (parquet) for this session
                                          # — resolved by the caller (questions-api-and-wiring
                                          #   slice) from session_id; this graph never looks it
                                          #   up itself.

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
    cost_estimate_usd: float | None      # Phase 2 — approximate, from token usage x configured pricing

    # Control
    status: str                          # "completed" | "gave_up" | "failed"
    error: str | None                    # set on a FATAL (infra) failure — distinct from a retryable code failure
