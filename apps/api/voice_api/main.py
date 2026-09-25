"""Control plane. The runtime owns audio; this API owns durable state."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from voice_api.api.v1.api import api_router

app = FastAPI(title="Voice AI API", version="0.2.0")


class DashboardFiles(StaticFiles):
    """Serve the client router on reload without turning missing API/assets into HTML."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            route = path.replace("\\", "/").lstrip("/")
            if (
                error.status_code != 404
                or scope["method"] not in ("GET", "HEAD")
                or route.startswith(("api/", "assets/"))
                or route in {"api", "health"}
                or "." in Path(route).name
            ):
                raise
            return await super().get_response("index.html", scope)


@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def validation_error(_request, error):
    # Validation responses must not echo write-only credential inputs.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": list(item["loc"]), "type": item["type"], "msg": item["msg"]}
                for item in error.errors()
            ]
        },
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "voice-api"}


# Include the API router under /api/v1 (standardized) and /api (backward compatibility)
app.include_router(api_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api")

dashboard_dist = Path(__file__).resolve().parents[2] / "dashboard" / "dist"
if dashboard_dist.is_dir():
    app.mount("/", DashboardFiles(directory=dashboard_dist, html=True), name="dashboard")
