"""Wires the session store to the compiled QA graph for one question.

Replaces the old generic `run_agent(input_text)` slot (the `transform_text`
placeholder capability) — the graph is now the specialized generate ->
execute -> inspect -> retry -> answer loop described in `spec/agent.md`, and
this module is the single place that resolves a `session_id` into the state
the graph needs, then persists the outcome.

Phase 1 DB persistence deliberately reuses the existing generic `RunRow`
shape (see `spec/data.md`: "Phase 1 uses the existing generic `RunRow`
shape"). A dedicated `QueryRunRow` table/migration is an explicit Phase 2
deliverable (`cost-and-logging` slice) — not built here.
"""

from __future__ import annotations

from config.settings import get_settings
from db.session import create_db_session
from db.models import RunRow
from graph.agent import agentic_ai
from graph.state import QAState
from observability.events import get_logger
from tools import session_store

logger = get_logger("qa_runner")


class SessionNotFoundError(Exception):
    """Raised when `session_id` does not resolve to an active session.

    The API layer (`api/questions.py`) catches this and maps it to a 404.
    """


def run_question(session_id: str, question: str) -> dict:
    """Run one question through the QA graph and persist the outcome.

    Returns a plain dict with everything `api/questions.py` needs to build
    its response: `question`, `status`, `answer`, `code`, `retry_count`,
    `cost_estimate_usd`, `chart_spec`, `table_data`, and `error` (set only
    on a fatal/`status == "failed"` outcome).
    """
    session = session_store.get_session(session_id)
    if session is None:
        logger.warning("run_question.session_not_found", session_id=session_id)
        raise SessionNotFoundError(f"Session '{session_id}' not found.")

    logger.info(
        "run_question.received",
        session_id=session_id,
        question_length=len(question),
    )

    settings = get_settings()

    with create_db_session() as db_session:
        run = RunRow(input_text=question)
        db_session.add(run)
        db_session.flush()
        run_id = run.id

    initial: QAState = {
        "session_id": session_id,
        "query_run_id": run_id,
        "question": question,
        "schema_profile": session.schema_profile,
        "conversation_history": session.conversation_history,
        "dataframe_path": session.dataframe_path,
        "generated_code": None,
        "execution_result": None,
        "execution_error": None,
        "retry_count": 0,
        "max_retries": settings.max_retries,
        "final_answer": None,
        "chart_spec": None,
        "table_data": None,
        "cost_estimate_usd": None,
        "status": None,
        "error": None,
    }

    final: QAState = agentic_ai.invoke(initial)

    status = final.get("status")
    final_answer = final.get("final_answer")
    error = final.get("error")

    logger.info(
        "run_question.outcome",
        session_id=session_id,
        status=status,
        retry_count=final.get("retry_count", 0),
        error=error,
    )

    with create_db_session() as db_session:
        run = db_session.get(RunRow, run_id)
        run.status = status
        run.output_text = final_answer
        run.error_message = error

    return {
        "question": question,
        "status": status,
        "answer": final_answer,
        "code": final.get("generated_code") if status == "completed" else None,
        "retry_count": final.get("retry_count", 0),
        "cost_estimate_usd": final.get("cost_estimate_usd"),
        "chart_spec": final.get("chart_spec"),
        "table_data": final.get("table_data"),
        "error": error,
    }
