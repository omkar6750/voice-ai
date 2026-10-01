"""Build LLM services with main-stage cross-provider first-token failover."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from google.genai import errors as genai_errors
from google.genai import types as genai_types
from openai import APIConnectionError, APIStatusError, APITimeoutError
from openai.types.chat.chat_completion_chunk import (
    ChatCompletionChunk,
    Choice,
    ChoiceDelta,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)
from openai.types.completion_usage import CompletionUsage
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.openrouter.llm import OpenRouterLLMService
from pipecat.services.sarvam.llm import SarvamLLMService

from voice_runtime.execution.credential_keys import stage_api_key
from voice_runtime.safe_logs import RuntimeEvent, error_category, operational_event


class _Non200ProviderStatusError(Exception):
    def __init__(self, status_code: int):
        super().__init__("LLM provider returned an unexpected HTTP status")
        self.status_code = status_code


def _require_http_200(stream) -> None:
    status_code = getattr(getattr(stream, "response", None), "status_code", None)
    if isinstance(status_code, int) and status_code != 200:
        raise _Non200ProviderStatusError(status_code)


def _has_generated_content(chunk) -> bool:
    for choice in getattr(chunk, "choices", ()) or ():
        delta = getattr(choice, "delta", None)
        if not delta:
            continue
        if any(
            getattr(delta, field, None)
            for field in ("content", "tool_calls", "function_call", "refusal", "audio")
        ):
            return True
    return False


def _fallback_worthy(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
    return isinstance(
        error, (APIConnectionError, APIStatusError, APITimeoutError, genai_errors.APIError)
    ) or (isinstance(status_code, int) and status_code != 200)


def _google_has_generated_content(response) -> bool:
    for candidate in getattr(response, "candidates", None) or ():
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or ():
            if (getattr(part, "text", None) and not getattr(part, "thought", False)) or getattr(
                part, "function_call", None
            ):
                return True
    return False


async def _google_as_openai_chunks(service, context):
    tool_index = 0
    async for response in service._stream_response(context):
        choices = []
        for candidate in getattr(response, "candidates", None) or ():
            content = getattr(candidate, "content", None)
            candidate_index = getattr(candidate, "index", None) or 0
            for part in getattr(content, "parts", None) or ():
                if getattr(part, "text", None) and not getattr(part, "thought", False):
                    choices.append(
                        Choice(
                            index=candidate_index,
                            delta=ChoiceDelta(content=part.text),
                            finish_reason=None,
                        )
                    )
                function = getattr(part, "function_call", None)
                if function:
                    choices.append(
                        Choice(
                            index=candidate_index,
                            delta=ChoiceDelta(
                                tool_calls=[
                                    ChoiceDeltaToolCall(
                                        index=tool_index,
                                        id=getattr(function, "id", None) or uuid.uuid4().hex,
                                        type="function",
                                        function=ChoiceDeltaToolCallFunction(
                                            name=function.name,
                                            arguments=json.dumps(function.args or {}),
                                        ),
                                    )
                                ]
                            ),
                            finish_reason=None,
                        )
                    )
                    tool_index += 1
        usage = getattr(response, "usage_metadata", None)
        completion_usage = (
            CompletionUsage(
                prompt_tokens=usage.prompt_token_count or 0,
                completion_tokens=usage.candidates_token_count or 0,
                total_tokens=usage.total_token_count or 0,
            )
            if usage
            else None
        )
        response_id = getattr(response, "response_id", None) or uuid.uuid4().hex
        response_model = getattr(response, "model_version", None) or service._settings.model
        if not choices:
            if completion_usage:
                yield ChatCompletionChunk(
                    id=response_id,
                    choices=[],
                    created=int(time.time()),
                    model=response_model,
                    object="chat.completion.chunk",
                    usage=completion_usage,
                )
            continue
        for index, choice in enumerate(choices):
            yield ChatCompletionChunk(
                id=response_id,
                choices=[choice],
                created=int(time.time()),
                model=response_model,
                object="chat.completion.chunk",
                usage=completion_usage if index == len(choices) - 1 else None,
            )


async def _openai_as_google_chunks(service, context):
    stream = await service.get_chat_completions(context)
    _require_http_200(stream)
    iterator = stream.__aiter__()
    tool_calls: dict[int, dict[str, str]] = {}
    usage = None
    try:
        async for chunk in iterator:
            if chunk.usage:
                usage = genai_types.GenerateContentResponseUsageMetadata(
                    prompt_token_count=chunk.usage.prompt_tokens,
                    candidates_token_count=chunk.usage.completion_tokens,
                    total_token_count=chunk.usage.total_tokens,
                )
            for choice in chunk.choices or ():
                delta = choice.delta
                if delta.content:
                    yield genai_types.GenerateContentResponse(
                        response_id=chunk.id,
                        model_version=chunk.model,
                        candidates=[
                            genai_types.Candidate(
                                index=choice.index,
                                content=genai_types.Content(
                                    role="model",
                                    parts=[genai_types.Part(text=delta.content)],
                                ),
                            )
                        ],
                    )
                for call in delta.tool_calls or ():
                    entry = tool_calls.setdefault(
                        call.index, {"id": call.id or uuid.uuid4().hex, "name": "", "arguments": ""}
                    )
                    if call.id:
                        entry["id"] = call.id
                    if call.function:
                        entry["name"] += call.function.name or ""
                        entry["arguments"] += call.function.arguments or ""
        parts = []
        for call in tool_calls.values():
            try:
                arguments = json.loads(call["arguments"] or "{}")
            except json.JSONDecodeError:
                raise ValueError("Fallback tool arguments were not valid JSON") from None
            if not isinstance(arguments, dict):
                raise ValueError("Fallback tool arguments must be a JSON object")
            parts.append(
                genai_types.Part(
                    function_call=genai_types.FunctionCall(
                        id=call["id"], name=call["name"], args=arguments
                    )
                )
            )
        if parts or usage:
            yield genai_types.GenerateContentResponse(
                model_version=service._settings.model,
                candidates=(
                    [genai_types.Candidate(content=genai_types.Content(role="model", parts=parts))]
                    if parts
                    else None
                ),
                usage_metadata=usage,
            )
    finally:
        if hasattr(iterator, "aclose"):
            await iterator.aclose()
        if hasattr(stream, "close"):
            await stream.close()
        elif hasattr(stream, "aclose"):
            await stream.aclose()


class _FirstTokenFallback:
    """OpenAI-compatible failover before any caller-visible content is emitted."""

    def configure_fallback(self, service, config: dict[str, Any]) -> None:
        self._fallback_service = service
        self._fallback_config = config
        self._fallback_active = False
        self.active_provider = self._primary_provider
        self.active_model = self._primary_model

    async def cleanup(self) -> None:
        await super().cleanup()
        await self._fallback_service.cleanup()

    async def _fallback_stream(self, context):
        if isinstance(self._fallback_service, GoogleLLMService):
            return _google_as_openai_chunks(self._fallback_service, context)
        stream = await self._fallback_service.get_chat_completions(context)
        _require_http_200(stream)
        return stream

    def _activate_fallback(self, error: Exception) -> None:
        self._fallback_active = True
        self.active_provider = self._fallback_config["provider"]
        self.active_model = self._fallback_config["model"]
        operational_event(
            RuntimeEvent.LLM_FALLBACK_ACTIVATED,
            level="WARNING",
            provider=self.active_provider,
            operation="llm",
            status="started",
            error_category=error_category(error),
        )

    async def get_chat_completions(self, context):
        if self._fallback_active:
            try:
                return await self._fallback_service.get_chat_completions(context)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if not _fallback_worthy(error):
                    raise
                # Permit one bounded cycle per inference when the fallback is
                # also unavailable (for example, a second provider 429). The
                # next request starts from the primary again.
                self._fallback_active = False
                self.active_provider = self._primary_provider
                self.active_model = self._primary_model
                operational_event(
                    RuntimeEvent.PROVIDER_FAILED,
                    level="WARNING",
                    provider=self._fallback_config["provider"],
                    operation="llm_fallback",
                    status="failed",
                    error_category=error_category(error),
                )
                return await super().get_chat_completions(context)

        stream = None
        iterator = None
        buffered = []
        timeout = float(self._fallback_config["first_token_timeout_seconds"])
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        try:
            stream = await asyncio.wait_for(super().get_chat_completions(context), timeout=timeout)
            _require_http_200(stream)
            iterator = stream.__aiter__()
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError("Primary LLM first-token deadline exceeded")
                try:
                    chunk = await asyncio.wait_for(anext(iterator), timeout=remaining)
                except StopAsyncIteration as error:
                    raise TimeoutError(
                        "Primary LLM stream ended before response content"
                    ) from error
                buffered.append(chunk)
                if _has_generated_content(chunk):
                    break
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not isinstance(error, TimeoutError) and not _fallback_worthy(error):
                raise
            try:
                await self._close_stream(stream, iterator)
            except Exception:
                operational_event(
                    RuntimeEvent.PROVIDER_FAILED,
                    level="WARNING",
                    provider=self._primary_provider,
                    operation="llm",
                    status="failed",
                    error_category="runtime",
                )
            self._activate_fallback(error)
            return await self._fallback_stream(context)

        async def replay():
            try:
                for item in buffered:
                    yield item
                async for item in iterator:
                    yield item
            finally:
                await self._close_stream(stream, iterator)

        return replay()

    @staticmethod
    async def _close_stream(stream, iterator) -> None:
        if iterator is not None and hasattr(iterator, "aclose"):
            await iterator.aclose()
        if stream is not None:
            if hasattr(stream, "close"):
                await stream.close()
            elif hasattr(stream, "aclose"):
                await stream.aclose()


class _FallbackGroqLLMService(_FirstTokenFallback, GroqLLMService):
    pass


class _FallbackOpenRouterLLMService(_FirstTokenFallback, OpenRouterLLMService):
    pass


class _FallbackGoogleLLMService(_FirstTokenFallback, GoogleLLMService):
    async def _google_fallback_stream(self, context):
        if isinstance(self._fallback_service, GoogleLLMService):
            return self._fallback_service._stream_response(context)
        return _openai_as_google_chunks(self._fallback_service, context)

    async def _stream_response(self, context):
        if self._fallback_active:
            async for response in await self._google_fallback_stream(context):
                yield response
            return

        stream = super()._stream_response(context)
        iterator = stream.__aiter__()
        timeout = float(self._fallback_config["first_token_timeout_seconds"])
        deadline = asyncio.get_running_loop().time() + timeout
        buffered = []
        try:
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError("Primary Gemini first-token deadline exceeded")
                try:
                    response = await asyncio.wait_for(anext(iterator), timeout=remaining)
                except StopAsyncIteration as error:
                    raise TimeoutError(
                        "Primary Gemini stream ended before response content"
                    ) from error
                buffered.append(response)
                if _google_has_generated_content(response):
                    break
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not isinstance(error, TimeoutError) and not _fallback_worthy(error):
                raise
            if hasattr(iterator, "aclose"):
                await iterator.aclose()
            self._activate_fallback(error)
            async for response in await self._google_fallback_stream(context):
                yield response
            return

        try:
            for response in buffered:
                yield response
            async for response in iterator:
                yield response
        finally:
            if hasattr(iterator, "aclose"):
                await iterator.aclose()


class _FallbackSarvamLLMService(_FirstTokenFallback, SarvamLLMService):
    pass


def _settings(config: dict[str, Any], *, system_instruction: str | None = None) -> dict[str, Any]:
    values = {
        "model": config.get("model"),
        "temperature": config.get("temperature", 0.4),
        "max_tokens": config.get("max_tokens", config.get("max_output_tokens", 180)),
    }
    if config.get("top_p") is not None:
        values["top_p"] = config["top_p"]
    if system_instruction is not None:
        values["system_instruction"] = system_instruction
    if config.get("reasoning_effort") is not None:
        values["reasoning_effort"] = config["reasoning_effort"]
    return values


def build_llm_service(
    settings, config: dict[str, Any], *, stage: str, system_instruction: str | None = None
):
    """Build one Pipecat LLM service, resolving only the stage credential."""

    provider = config.get("provider", "groq")
    api_key = stage_api_key(settings, stage, provider)
    if not api_key:
        raise ValueError(f"{provider}_api_key is not configured for {stage}")
    values = _settings(config, system_instruction=system_instruction)

    if provider == "groq":
        values["reasoning_effort"] = "none"
        service_type = (
            _FallbackGroqLLMService if stage == "llm" and config.get("fallback") else GroqLLMService
        )
        service = service_type(api_key=api_key, settings=service_type.Settings(**values))
        return (
            _attach_fallback(settings, service, config, system_instruction)
            if config.get("fallback")
            else service
        )
    if provider == "gemini":
        values.pop("reasoning_effort", None)
        service_type = (
            _FallbackGoogleLLMService
            if stage == "llm" and config.get("fallback")
            else GoogleLLMService
        )
        service = service_type(api_key=api_key, settings=service_type.Settings(values))
        return (
            _attach_fallback(settings, service, config, system_instruction)
            if config.get("fallback")
            else service
        )
    if provider == "openrouter":
        preferences = config.get("provider_preferences") or {}
        extra: dict[str, Any] = {}
        if config.get("models"):
            extra["models"] = config["models"]
        if preferences:
            extra["provider"] = {
                **{
                    key: preferences[key]
                    for key in ("order", "only", "ignore")
                    if preferences.get(key)
                },
                **(
                    {"allow_fallbacks": preferences["allow_fallbacks"]}
                    if preferences.get("allow_fallbacks") is not None
                    else {}
                ),
                **(
                    {"data_collection": preferences["data_collection"]}
                    if preferences.get("data_collection")
                    else {}
                ),
                **({"zdr": preferences["zdr"]} if preferences.get("zdr") is not None else {}),
                **(
                    {
                        "sort": {
                            "by": preferences["sort_by"],
                            **(
                                {"partition": preferences["partition"]}
                                if preferences.get("partition")
                                else {}
                            ),
                        }
                    }
                    if preferences.get("sort_by")
                    else {}
                ),
            }
        try:
            from pipecat.services.openrouter.llm import OpenRouterLLMService

            values.pop("reasoning_effort", None)
            if extra:
                values["extra"] = extra
            service_type = (
                _FallbackOpenRouterLLMService
                if stage == "llm" and config.get("fallback")
                else OpenRouterLLMService
            )
            service = service_type(api_key=api_key, settings=service_type.Settings(**values))
            return (
                _attach_fallback(settings, service, config, system_instruction)
                if config.get("fallback")
                else service
            )
        except ImportError:
            from pipecat.services.openai.llm import OpenAILLMService

            values.pop("provider", None)
            return OpenAILLMService(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                settings=OpenAILLMService.Settings(**values),
            )
    if provider == "sarvam":
        if values.get("reasoning_effort") == "none":
            values["reasoning_effort"] = None
        elif values.get("reasoning_effort") == "provider_default":
            values.pop("reasoning_effort", None)
        service_type = (
            _FallbackSarvamLLMService
            if stage == "llm" and config.get("fallback")
            else SarvamLLMService
        )
        service = service_type(api_key=api_key, settings=service_type.Settings(**values))
        return (
            _attach_fallback(settings, service, config, system_instruction)
            if config.get("fallback")
            else service
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")


def _attach_fallback(settings, service, config: dict[str, Any], system_instruction: str | None):
    fallback = config["fallback"]
    fallback_service = build_llm_service(
        settings,
        {
            "provider": fallback["provider"],
            "model": fallback["model"],
            "temperature": config.get("temperature", 0.4),
            "max_tokens": config.get("max_tokens", 180),
            "top_p": config.get("top_p"),
        },
        stage="llm_fallback",
        system_instruction=system_instruction,
    )
    service._primary_provider = config["provider"]
    service._primary_model = config["model"]
    service.configure_fallback(fallback_service, fallback)
    return service
