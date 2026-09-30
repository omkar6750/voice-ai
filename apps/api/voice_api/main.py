"""Control plane. The runtime owns audio; this API owns durable state."""

import os
from time import perf_counter

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import ValidationError
from voice_runtime.safe_logs import configure_safe_logging

# Install before importing routes, Pipecat or SDKs: wire logs and exception
# renderers must never acquire caller/provider data, even during startup.
configure_safe_logging()

from voice_api.api.v1.api import api_router  # noqa: E402
from voice_api.core.config import get_settings  # noqa: E402

app = FastAPI(title="Voice AI API", version="0.2.0")


@app.middleware("http")
async def request_timing(request, call_next):
    if os.getenv("VOICE_DEBUG_PERF", "").lower() != "true":
        return await call_next(request)
    started_at = perf_counter()
    response = await call_next(request)
    logger.info(
        "request {} {} {} {:.0f}ms",
        request.method,
        request.url.path,
        response.status_code,
        (perf_counter() - started_at) * 1000,
    )
    return response
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
    return JSONResponse(
        status_code=422,
        content={
            # Custom validator messages and arbitrary mapping keys in `loc`
            # can contain submitted secrets. Do not serialize either.
            "detail": [{"type": "validation_error", "msg": "Request validation failed"}]
        },
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "voice-api"}


# Include the API router under /api/v1 (standardized) and /api (backward compatibility)
app.include_router(api_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api")
