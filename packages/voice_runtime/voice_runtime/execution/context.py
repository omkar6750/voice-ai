"""Compact only an unchanged captured prefix; durable transcript remains outside context."""

from copy import deepcopy
from dataclasses import dataclass


@dataclass(frozen=True)
class ContextMessage:
    id: str
    payload: dict


class ContextHistory:
    def __init__(self):
        self.messages: list[ContextMessage] = []

    def append(self, message_id: str, payload: dict) -> None:
        if any(message.id == message_id for message in self.messages):
            raise ValueError("Duplicate context message identity")
        self.messages.append(ContextMessage(message_id, deepcopy(payload)))

    def capture_prefix(self, keep_opening: int, keep_recent: int) -> tuple[str, ...]:
        if keep_opening < 0 or keep_recent < 0:
            raise ValueError("Retention counts cannot be negative")
        stop = max(keep_opening, len(self.messages) - keep_recent)
        selected = self.messages[keep_opening:stop]
        # Never split tool call/result groups. Skip compaction instead of orphaning them.
        if not self._complete_pairs(selected):
            return ()
        return tuple(message.id for message in selected)

    @staticmethod
    def _complete_pairs(messages: list[ContextMessage]) -> bool:
        calls, results = set(), set()
        for message in messages:
            calls.update(call["id"] for call in message.payload.get("tool_calls", []))
            if message.payload.get("role") == "tool":
                results.add(message.payload.get("tool_call_id"))
        return calls == results

    def apply_summary(self, captured: tuple[str, ...], summary_id: str, text: str) -> bool:
        if not captured or not text or any(m.id == summary_id for m in self.messages):
            return False
        ids = [message.id for message in self.messages]
        if captured[0] not in ids:
            return False
        start = ids.index(captured[0])
        end = start + len(captured)
        if tuple(ids[start:end]) != captured or not self._complete_pairs(self.messages[start:end]):
            return False
        self.messages[start:end] = [ContextMessage(summary_id, {"role": "system", "content": text})]
        return True
