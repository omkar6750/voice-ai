from fastapi import APIRouter, Depends
from voice_api.api.deps import require_operator
from voice_runtime.contracts import AgentConfig, ToolConfig, WorkspaceConfig

router = APIRouter(tags=["providers"])
Operator = Depends(require_operator)


@router.get("/providers")
async def providers(_: None = Operator) -> dict:
    return {
        "providers": [
            {
                "provider": "sarvam",
                "slots": ["stt", "tts"],
                "models": ["saaras:v3", "bulbul:v3"],
            },
            {
                "provider": "groq",
                "slots": ["llm", "classifier", "summarizer"],
                "models": ["qwen/qwen3.8-27b"],
            },
            {"provider": "cartesia", "slots": ["tts"], "models": ["sonic-3"]},
            {
                "provider": "gemini",
                "slots": ["embedding"],
                "models": ["gemini-embedding-001"],
            },
        ]
    }


@router.get("/config-schema")
async def config_schema(_: None = Operator) -> dict:
    return {
        "agent": AgentConfig.model_json_schema(),
        "tool": ToolConfig.model_json_schema(),
        "workspace": WorkspaceConfig.model_json_schema(),
    }
