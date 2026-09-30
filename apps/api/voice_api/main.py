"""Control plane. The runtime owns audio; this API owns durable state."""

import os
from time import perf_counter

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import ValidationError
from voice_runtime.safe_logs import RuntimeEvent, configure_safe_logging, operational_event

# Install before importing routes, Pipecat or SDKs: wire logs and exception
# renderers must never acquire caller/provider data, even during startup.
configure_safe_logging()

from voice_api.api.v1.api import api_router  # noqa: E402
from voice_api.core.config import get_settings  # noqa: E402

app = FastAPI(title="Voice AI API", version="0.2.0")


@app.middleware("http")
async def request_timing(request, call_next):
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        _log_api_failure(request.method, 500, (perf_counter() - started_at) * 1000)
        raise
    if response.status_code >= 400:
        _log_api_failure(
            request.method,
            response.status_code,
            (perf_counter() - started_at) * 1000,
        )
    elif os.getenv("VOICE_DEBUG_PERF", "").lower() == "true":
        # Kept for local performance debugging. The safe logger intentionally
        # strips the URL because paths may contain organization/resource IDs.
        logger.info(
            "request {} {} {} {:.0f}ms",
            request.method,
            request.url.path,
            response.status_code,
            (perf_counter() - started_at) * 1000,
        )
    return response


def _log_api_failure(method: str, status_code: int, duration_ms: float) -> None:
    """Log API failures with safe metadata only, in development and production."""
    operational_event(
        RuntimeEvent.API_REQUEST_FAILED,
        level="ERROR" if status_code >= 500 else "WARNING",
        request_method=method,
        http_status=status_code,
        duration_ms=duration_ms,
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        part.strip() for part in get_settings().clerk_authorized_parties.split(",") if part.strip()
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Platform-Support-Session"],
)


@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def validation_error(_request, error):
    # Validation responses must not echo write-only credential inputs.
    settings = get_settings()
    if settings.debug_diagnostics and settings.env.casefold() in {"dev", "development", "local"}:
        _log_safe_validation_diagnostics(error)
    return JSONResponse(
        status_code=422,
        content={
            # Custom validator messages and arbitrary mapping keys in `loc`
            # can contain submitted secrets. Do not serialize either.
            "detail": [{"type": "validation_error", "msg": "Request validation failed"}]
        },
    )


def _log_safe_validation_diagnostics(error: RequestValidationError | ValidationError) -> None:
    """Report only fixed, allowlisted error locations; never log values or messages."""
    try:
        if isinstance(error, RequestValidationError):
            # FastAPI's wrapper exposes only errors() without Pydantic's
            # privacy keyword arguments. Read locations, but never serialize
            # this structure or include it in an operational event.
            details = error.errors()[:5]
        else:
            details = error.errors(
                include_url=False,
                include_context=False,
                include_input=False,
            )[:5]
    except Exception:
        details = None
    if not details:
        operational_event(
            RuntimeEvent.API_VALIDATION_FAILED,
            level="WARNING",
            validation_scope="internal",
            validation_detail_state="unavailable" if details is None else "empty",
        )
        return

    scopes = {
        "query": "request_query",
        "path": "request_path",
        "header": "request_header",
        "body": "request_body",
    }
    for detail in details:
        location = detail.get("loc", ())
        head = location[0] if location else None
        if isinstance(error, RequestValidationError):
            scope = scopes.get(head, "internal") if isinstance(head, str) else "internal"
        else:
            scope = "model_validation"
        field = next(
            (part for part in reversed(location) if isinstance(part, str)),
            None,
        )
        operational_event(
            RuntimeEvent.API_VALIDATION_FAILED,
            level="WARNING",
            validation_scope=scope,
            validation_field=field,
            validation_detail_state="available",
            validation_error_type=detail.get("type"),
        )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "voice-api"}


# Include the API router under /api/v1 (standardized) and /api (backward compatibility)
app.include_router(api_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api")
