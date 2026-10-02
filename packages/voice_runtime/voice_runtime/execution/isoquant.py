"""Pipecat LLM adapter for Isoquant's OpenAI-compatible chat stream."""

from pipecat.services.openai.llm import OpenAILLMService


class IsoquantLLMService(OpenAILLMService):
    """Use Isoquant chat completions while retaining Pipecat context and tool handling."""

    def __init__(
        self, *, api_key: str, reasoning_effort: str = "low", zdr_required: bool = True, **kwargs
    ):
        self.reasoning_effort = reasoning_effort
        headers = {"Isoquant-ZDR": "required"} if zdr_required else None
        super().__init__(
            api_key=api_key,
            base_url="https://api.isoquant.ai/v1",
            default_headers=headers,
            **kwargs,
        )

    def build_chat_completion_params(self, params_from_context) -> dict:
        params = super().build_chat_completion_params(params_from_context)
        params.pop("temperature", None)
        params.pop("top_p", None)
        params.pop("max_completion_tokens", None)
        params["extra_body"] = {
            "reasoning_effort": self.reasoning_effort,
            "include_reasoning": False,
        }
        return params

    async def get_chat_completions(self, context):
        stream = await super().get_chat_completions(context)

        async def checked_stream():
            completed = False
            try:
                async for chunk in stream:
                    for choice in chunk.choices:
                        if choice.finish_reason in {"stop", "tool_calls"}:
                            completed = True
                        elif choice.finish_reason:
                            raise RuntimeError(
                                f"Isoquant chat response ended with {choice.finish_reason}"
                            )
                    yield chunk
                if not completed:
                    request_id = getattr(getattr(stream, "response", None), "headers", {}).get(
                        "x-request-id"
                    )
                    detail = f" (x-request-id: {request_id})" if request_id else ""
                    raise RuntimeError(f"Isoquant chat stream ended before completion{detail}")
            finally:
                await stream.close()

        return checked_stream()
