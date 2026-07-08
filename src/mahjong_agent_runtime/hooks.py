from __future__ import annotations

"""Lightweight lifecycle hooks for the runtime.

Hooks are extension points around the agent loop. They are meant for cross-cutting
concerns such as observability, audits, eval collection, or alerts; business
semantics should stay in context, model contracts, and tools.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class HookEvent:
    name: str
    trace_id: str
    payload: dict[str, Any] = field(default_factory=dict)


HookHandler = Callable[[HookEvent], None]


@dataclass(slots=True)
class HookManager:
    """Register and emit runtime lifecycle hooks.

    By default hook failures are isolated from the main agent path. This keeps
    optional logging/eval extensions from breaking customer handling.
    """

    fail_fast: bool = False
    handlers: dict[str, list[HookHandler]] = field(default_factory=lambda: defaultdict(list))

    def register(self, event_name: str, handler: HookHandler) -> None:
        self.handlers[str(event_name)].append(handler)

    def emit(self, event_name: str, *, trace_id: str, payload: dict[str, Any] | None = None) -> list[Exception]:
        errors: list[Exception] = []
        event = HookEvent(name=str(event_name), trace_id=trace_id, payload=dict(payload or {}))
        for handler in list(self.handlers.get(event.name, [])):
            try:
                handler(event)
            except Exception as exc:
                if self.fail_fast:
                    raise
                errors.append(exc)
        return errors

