from fastapi import APIRouter

from api._common import ok, api_error
from domain.question import AskQuestionRequest, AskQuestionResponse
from graph.runner import SessionNotFoundError, run_question
from observability.events import get_logger

router = APIRouter()
logger = get_logger("api.questions")


@router.post("/sessions/{session_id}/questions")
def ask_question(session_id: str, req: AskQuestionRequest) -> dict:
    question = (req.question or "").strip()
    if not question:
        raise api_error("EMPTY_QUESTION", "The 'question' field must not be empty.", 400)

    try:
        result = run_question(session_id, question)
    except SessionNotFoundError as exc:
        raise api_error("NOT_FOUND", str(exc), 404) from exc
    except Exception as exc:  # never leak a raw exception/stack trace to the client
        logger.error("ask_question.unexpected_error", session_id=session_id, error=str(exc))
        raise api_error(
            "INTERNAL_ERROR", "Unexpected error while answering the question.", 500
        ) from exc

    if result["status"] == "failed":
        # Fatal infra failure (spec/api.md: "A fatal infrastructure failure
        # ... response body carries a clear, generic error message").
        raise api_error(
            "ANALYSIS_SERVICE_UNAVAILABLE",
            "The analysis service is temporarily unavailable — try again.",
            500,
        )

    response = AskQuestionResponse(
        question=result["question"],
        status=result["status"],
        answer=result["answer"],
        code=result["code"],
        retry_count=result["retry_count"],
        cost_estimate_usd=result["cost_estimate_usd"],
        chart_spec=result["chart_spec"],
        table=result["table_data"],
    )
    return ok(response.model_dump())
