from fastapi import APIRouter, UploadFile, File

from api._common import ok, api_error
from domain.session import CreateSessionResponse, GetSessionResponse
from tools import session_store
from tools.file_parser import FileParseError, UnsupportedFileTypeError, parse_file
from tools.schema_profile import extract_schema_profile

router = APIRouter()

# Hardcoded module-level constant (not a settings field — a parallel slice
# already owns the 4 fields added to src/config/settings.py).
MAX_UPLOAD_SIZE_MB = 20
_MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024


@router.post("/sessions")
async def create_session(file: UploadFile = File(...)) -> dict:
    file_bytes = await file.read()

    if len(file_bytes) > _MAX_UPLOAD_SIZE_BYTES:
        raise api_error(
            "FILE_TOO_LARGE",
            f"File exceeds the maximum upload size of {MAX_UPLOAD_SIZE_MB} MB.",
            413,
        )

    filename = file.filename or "upload"

    try:
        df = parse_file(file_bytes, filename)
    except UnsupportedFileTypeError as exc:
        raise api_error("UNSUPPORTED_FILE_TYPE", str(exc), 400) from exc
    except FileParseError as exc:
        raise api_error("FILE_PARSE_ERROR", str(exc), 400) from exc
    except Exception as exc:  # never leak a raw exception/stack trace to the client
        raise api_error(
            "INTERNAL_ERROR", f"Unexpected error while parsing '{filename}'.", 500
        ) from exc

    try:
        schema_profile = extract_schema_profile(df)
        record = session_store.create_session(filename, df, schema_profile)
    except Exception as exc:
        raise api_error(
            "INTERNAL_ERROR", "Unexpected error while starting the session.", 500
        ) from exc

    response = CreateSessionResponse(
        session_id=record.session_id,
        filename=record.filename,
        row_count=schema_profile["row_count"],
        column_count=schema_profile["column_count"],
        schema_profile=schema_profile,
        warnings=record.warnings,
    )
    return ok(response.model_dump())


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    record = session_store.get_session(session_id)
    if record is None:
        raise api_error("NOT_FOUND", f"Session '{session_id}' not found.", 404)

    response = GetSessionResponse(
        session_id=record.session_id,
        filename=record.filename,
        schema_profile=record.schema_profile,
        warnings=record.warnings,
        conversation_history=record.conversation_history,
    )
    return ok(response.model_dump())
