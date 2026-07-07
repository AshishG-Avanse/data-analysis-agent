from pydantic import BaseModel


class CreateSessionResponse(BaseModel):
    """Response body for `POST /api/sessions` (see spec/api.md)."""

    session_id: str
    filename: str
    row_count: int
    column_count: int
    schema_profile: dict
    warnings: list[str] = []


class GetSessionResponse(BaseModel):
    """Response body for `GET /api/sessions/{session_id}` (see spec/api.md)."""

    session_id: str
    filename: str
    schema_profile: dict
    warnings: list[str] = []
    conversation_history: list[dict] = []
