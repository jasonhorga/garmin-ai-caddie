"""Pure readiness-gate decision used to exercise the Fastfile contract in Python CI tests."""

from __future__ import annotations

from typing import Any


def preflight_gate(readiness: dict[str, Any], *, allow_degraded: bool = False) -> str:
    """Return ``wait``, ``pass`` or ``error`` using the Fastfile's B1/B2 rules."""
    checks = readiness.get("checks")
    if isinstance(checks, list) and any(
        isinstance(row, dict) and row.get("state") == "warming" for row in checks
    ):
        return "wait"
    if readiness.get("runtimeStatus") == "degraded" and not allow_degraded:
        return "error"
    return "pass"
