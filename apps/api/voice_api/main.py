from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Voice AI API", version="0.1.0")


class HealthResponse(BaseModel):
    status: str
    service: str


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="voice-api")


@app.get("/api/agent-config")
async def agent_config() -> dict:
    from voice_runtime.config import default_agent_config

    return default_agent_config().model_dump(mode="json")
