from __future__ import annotations

import json
import re
from pathlib import Path

from config.settings import get_settings
from graph.state import QAState
from llm.client import LLMClient
from llm.providers.gemini import GeminiProvider
from observability.events import get_logger
from tools.code_executor import execute_pandas_code

logger = get_logger("qa_graph")

_CODEGEN_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "codegen.md"
_INTERPRET_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "interpret.md"

# Matches a fenced code block, optionally tagged ```python, non-greedy so a
# reply with exactly one block (possibly wrapped in surrounding prose) is
# extracted cleanly.
_CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n?(.*?)```", re.DOTALL)

_GIVE_UP_MESSAGE = (
    "I wasn't able to find a working way to analyze that after several attempts. "
    "Please try rephrasing your question, or ask something more specific about the data."
)


def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_code_block(text: str) -> str | None:
    """Extract the single fenced Python code block from a model response.

    Handles the model wrapping the whole reply in prose plus one fenced
    block (the common case); returns None if no fenced block is found.
    """
    match = _CODE_BLOCK_RE.search(text or "")
    if not match:
        return None
    code = match.group(1).strip()
    return code or None


def generate_code(state: QAState) -> QAState:
    """Ask the codegen model for one candidate `analyze(df)` implementation.

    On a fatal Gemini/SDK failure (auth/network/rate-limit), sets
    `state["error"]` so the graph routes to `handle_error`. A response with
    no extractable code block is treated as a retryable failure — it sets
    `execution_error` (NOT `state["error"]`) and leaves `retry_count`
    untouched here; `execute_code` is the single place that increments
    `retry_count`, keeping the count-per-attempt logic in one spot.
    """
    settings = get_settings()
    retry_count = state.get("retry_count", 0)

    if retry_count > 0 and state.get("generated_code") and state.get("execution_error"):
        retry_context = (
            "Previous code attempt:\n```python\n"
            f"{state['generated_code']}\n"
            "```\n\n"
            f"That attempt failed with this error:\n{state['execution_error']}\n\n"
            "Fix the SPECIFIC problem above in your next attempt."
        )
    else:
        retry_context = "N/A (first attempt)."

    prompt_template = _load_prompt(_CODEGEN_PROMPT_PATH)
    prompt = prompt_template.format(
        schema_profile=json.dumps(state.get("schema_profile", {}), indent=2),
        question=state.get("question", ""),
        retry_context=retry_context,
    )

    try:
        model = settings.llm_model_codegen or GeminiProvider.DEFAULT_MODEL_CODEGEN
        response_text = LLMClient(model=model).call_model(prompt)
    except Exception as exc:  # genuine infra/API failure — fatal
        logger.error(
            "generate_code.fatal_llm_error",
            session_id=state.get("session_id"),
            error=str(exc),
        )
        return {
            **state,
            "error": "The analysis service is temporarily unavailable — try again.",
        }

    code = _extract_code_block(response_text)
    if code is None:
        logger.warning(
            "generate_code.no_code_block",
            session_id=state.get("session_id"),
            retry_count=retry_count,
        )
        return {
            **state,
            "generated_code": None,
            "execution_error": "The model's response did not contain an extractable Python code block.",
        }

    logger.info(
        "generate_code.success",
        session_id=state.get("session_id"),
        retry_count=retry_count,
        code_length=len(code),
    )
    return {**state, "generated_code": code}


def execute_code(state: QAState) -> QAState:
    """Run the most recent `generated_code` in an isolated subprocess.

    Sole owner of the `retry_count` increment: any failure path here
    (missing code, subprocess exception/timeout/non-zero exit, or a privacy
    guard rejection surfaced by the worker as `success: false`) increments
    `retry_count` exactly once. Success clears `execution_error` and sets
    `execution_result` to the already guard-validated aggregate.
    """
    settings = get_settings()
    retry_count = state.get("retry_count", 0)
    session_id = state.get("session_id")
    code = state.get("generated_code")

    if not code:
        error = state.get("execution_error") or "No analysis code was generated."
        logger.warning("execute_code.no_code", session_id=session_id, retry_count=retry_count)
        return {
            **state,
            "execution_result": None,
            "execution_error": error,
            "retry_count": retry_count + 1,
        }

    dataframe_path = state.get("dataframe_path")
    if not dataframe_path:
        # Fatal — infra problem (session/DataFrame missing), not a code-quality issue.
        logger.error("execute_code.fatal_missing_dataframe", session_id=session_id)
        return {
            **state,
            "error": "The session's data could not be found — please re-upload your file.",
        }

    outcome = execute_pandas_code(code, dataframe_path, settings.exec_timeout_seconds)

    if outcome.get("success"):
        logger.info("execute_code.success", session_id=session_id, retry_count=retry_count)
        return {**state, "execution_result": outcome.get("result"), "execution_error": None}

    error = outcome.get("error") or "Execution failed for an unknown reason."
    logger.warning(
        "execute_code.failure",
        session_id=session_id,
        retry_count=retry_count,
        error=error,
    )
    return {
        **state,
        "execution_result": None,
        "execution_error": error,
        "retry_count": retry_count + 1,
    }


def synthesize_answer(state: QAState) -> QAState:
    """Turn the guarded aggregate `execution_result` into a plain-language answer.

    A fatal Gemini/SDK failure here sets `state["error"]` (no retry — the
    underlying analysis already succeeded, per spec/agent.md).
    """
    settings = get_settings()
    prompt_template = _load_prompt(_INTERPRET_PROMPT_PATH)
    prompt = prompt_template.format(
        question=state.get("question", ""),
        execution_result=json.dumps(state.get("execution_result"), indent=2),
    )

    try:
        model = settings.llm_model_interpret or GeminiProvider.DEFAULT_MODEL_INTERPRET
        answer = LLMClient(model=model).call_model(prompt)
    except Exception as exc:
        logger.error(
            "synthesize_answer.fatal_llm_error",
            session_id=state.get("session_id"),
            error=str(exc),
        )
        return {
            **state,
            "error": "The analysis service is temporarily unavailable — try again.",
        }

    logger.info("synthesize_answer.success", session_id=state.get("session_id"))
    return {
        **state,
        "final_answer": answer.strip(),
        "status": "completed",
        # Phase 2 fields — kept as explicit keys (value None) so the API
        # layer can forward them generically without a schema change later.
        "chart_spec": None,
        "table_data": None,
        "cost_estimate_usd": None,
    }


def give_up(state: QAState) -> QAState:
    """Reached when `retry_count >= max_retries` with no successful execution.

    Surfaces ONLY a fixed, plain apology message — never partial code,
    results, or the retry trail.
    """
    logger.warning(
        "give_up",
        session_id=state.get("session_id"),
        retry_count=state.get("retry_count", 0),
    )
    return {
        **state,
        "final_answer": _GIVE_UP_MESSAGE,
        "status": "gave_up",
        "chart_spec": None,
        "table_data": None,
        "cost_estimate_usd": None,
    }


def handle_error(state: QAState) -> QAState:
    """The fatal-infra path. Logs and terminates; never raises."""
    logger.error(
        "handle_error",
        session_id=state.get("session_id"),
        query_run_id=state.get("query_run_id"),
        error=state.get("error"),
    )
    return {**state, "status": "failed"}


def finalize(state: QAState) -> QAState:
    """Phase 1 scope: terminal no-op beyond ensuring `status` is set.

    DB persistence of the question/answer is `questions-api-and-wiring`'s
    job (extending `graph/runner.py`); the JSONL query log is an explicit
    Phase 2 deliverable (`cost-and-logging` slice) — neither is built here.
    """
    return {**state, "status": state.get("status", "completed")}
