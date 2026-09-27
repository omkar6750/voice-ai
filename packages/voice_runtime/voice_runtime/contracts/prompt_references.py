"""Editor-only tool markers in author-authored prompts."""

import re

_TOOL_REFERENCE = re.compile(r"(?<!\\)#([a-z][a-z0-9_]*)\b")


def tool_references(prompt: str) -> set[str]:
    return {match.group(1) for match in _TOOL_REFERENCE.finditer(prompt)}


def compile_tool_references(prompt: str, available_tools: set[str]) -> str:
    """Remove only markers for actual exposed functions; keep other text intact."""
    return _TOOL_REFERENCE.sub(
        lambda match: match.group(1) if match.group(1) in available_tools else match.group(0),
        prompt,
    )
