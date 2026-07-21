from __future__ import annotations

"""Internal contracts shared by runtime services."""

from dataclasses import dataclass

from ..models import ToolResult


@dataclass(slots=True)
class SingleToolExecution:
    """One tool outcome plus scheduler control signals."""

    result: ToolResult
    blocked_by_consistency: bool = False
    blocked_by_stale_run: bool = False


__all__ = ["SingleToolExecution"]
