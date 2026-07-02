from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import DEFAULT_TZ_V2


@dataclass(slots=True)
class TraceEventV2:
    trace_id: str
    step: str
    content: dict[str, Any]
    level: str = "INFO"
    occurred_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        occurred_at = self.occurred_at or datetime.now(DEFAULT_TZ_V2)
        return {
            "schema_version": "agent_runtime_v2.trace.v1",
            "trace_id": self.trace_id,
            "time": occurred_at.isoformat(),
            "step": self.step,
            "level": self.level.upper(),
            "content": _jsonable(self.content),
            "log_line": self.format_log_line(occurred_at),
        }

    def format_log_line(self, occurred_at: datetime | None = None) -> str:
        actual_time = occurred_at or self.occurred_at or datetime.now(DEFAULT_TZ_V2)
        content = json.dumps(_jsonable(self.content), ensure_ascii=False, sort_keys=True)
        return f"{self.trace_id}-{actual_time.strftime('%Y-%m-%d %H:%M:%S')}-{self.level.upper()}: {content}"


class InMemoryTraceRecorderV2:
    def __init__(self) -> None:
        self.events: dict[str, list[TraceEventV2]] = {}

    def record(self, trace_id: str, step: str, content: dict[str, Any], *, level: str = "INFO") -> TraceEventV2:
        event = TraceEventV2(trace_id=trace_id, step=step, content=_jsonable(content), level=level)
        self.events.setdefault(trace_id, []).append(event)
        return event

    def get_trace(self, trace_id: str) -> list[TraceEventV2]:
        return list(self.events.get(trace_id, []))


class JsonlTraceRecorderV2:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, trace_id: str, step: str, content: dict[str, Any], *, level: str = "INFO") -> TraceEventV2:
        event = TraceEventV2(trace_id=trace_id, step=step, content=_jsonable(content), level=level)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return event

    def get_trace(self, trace_id: str) -> list[TraceEventV2]:
        if not self.path.exists():
            return []
        events: list[TraceEventV2] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            if raw.get("trace_id") != trace_id:
                continue
            events.append(
                TraceEventV2(
                    trace_id=str(raw["trace_id"]),
                    step=str(raw["step"]),
                    content=dict(raw.get("content") or {}),
                    level=str(raw.get("level") or "INFO"),
                    occurred_at=datetime.fromisoformat(str(raw["time"])) if raw.get("time") else None,
                )
            )
        return events


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
