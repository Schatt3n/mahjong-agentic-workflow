"""Shared idempotency lease semantics."""

from __future__ import annotations

from ..models import ToolResult


IDEMPOTENCY_CLAIM_LEASE_SECONDS = 120


def tool_result_is_in_progress(result: ToolResult) -> bool:
    """Return whether a ledger entry represents a live execution claim."""

    return bool(
        not result.called
        and result.allowed
        and isinstance(result.result, dict)
        and result.result.get("idempotency_status") == "claimed"
    )

