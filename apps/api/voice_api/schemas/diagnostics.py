"""Typed runtime diagnostic request and response contracts."""

from datetime import datetime

from voice_runtime.contracts.diagnostics import DiagnosticInput
from voice_runtime.contracts.diagnostics import DiagnosticPayload as DiagnosticPayload


class DiagnosticResponse(DiagnosticInput):
    run_id: str
    created_at: datetime
