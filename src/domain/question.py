from pydantic import BaseModel


class AskQuestionRequest(BaseModel):
    """Request body for `POST /api/sessions/{session_id}/questions` (spec/api.md).

    `question` defaults to "" (rather than being a required field) so a
    missing key in the request body reaches the route handler as an empty
    string instead of FastAPI auto-rejecting with a 422 — spec/api.md
    documents a 400 for "Empty/missing question", not a 422.
    """

    question: str = ""


class AskQuestionResponse(BaseModel):
    """Response body for `POST /api/sessions/{session_id}/questions` (spec/api.md).

    `cost_estimate_usd`, `chart_spec`, and `table` are always `None` in
    Phase 1 — populated from Phase 2 onward without a shape change here.
    """

    question: str
    status: str
    answer: str | None = None
    code: str | None = None
    retry_count: int = 0
    cost_estimate_usd: float | None = None
    chart_spec: dict | None = None
    table: dict | None = None
