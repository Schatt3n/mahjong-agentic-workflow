from __future__ import annotations

"""Backward-compatible imports for the refactored service layer.

New code should import from :mod:`mahjong_agent_runtime.services`.  This module
remains intentionally small so existing applications and tests do not break.
"""

from .services.action_service import ActionProcessor
from .services.contracts import SingleToolExecution
from .services.tool_service import ToolExecutionService, input_batch_run_is_stale

__all__ = [
    "ActionProcessor",
    "SingleToolExecution",
    "ToolExecutionService",
    "input_batch_run_is_stale",
]
