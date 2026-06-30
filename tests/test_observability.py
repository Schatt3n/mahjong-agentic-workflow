from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from mahjong_agent.observability import InMemoryTraceRecorder, JsonlTraceRecorder, TraceStep
from mahjong_agent.workflow_models import ActionName, ActionSource, ProposedAction


TZ = ZoneInfo("Asia/Shanghai")


def test_trace_event_formats_auditable_log_line() -> None:
    recorder = InMemoryTraceRecorder()

    event = recorder.record(
        "trace_001",
        TraceStep.ACTION_PROPOSED,
        {
            "action": ProposedAction(
                name=ActionName.CREATE_GAME,
                source=ActionSource.LLM,
                confidence=0.91,
                reason="用户确认组局",
            )
        },
        occurred_at=datetime(2026, 6, 30, 15, 8, 9, tzinfo=TZ),
    )

    assert event.format_log_line().startswith("trace_001-2026-06-30 15:08:09-INFO: ")
    assert '"name": "create_game"' in event.format_log_line()
    assert recorder.get_trace("trace_001") == [event]


def test_trace_recorder_clear_by_trace_or_all() -> None:
    recorder = InMemoryTraceRecorder()
    recorder.record("trace_a", "custom_step", {"a": 1})
    recorder.record("trace_b", "custom_step", {"b": 2})

    assert recorder.clear("trace_a") == 1
    assert recorder.get_trace("trace_a") == []
    assert recorder.clear() == 1
    assert recorder.get_trace("trace_b") == []


def test_jsonl_trace_recorder_persists_structured_events(tmp_path) -> None:
    path = tmp_path / "traces" / "workflow_trace.jsonl"
    recorder = JsonlTraceRecorder(path)

    recorder.record(
        "trace_jsonl",
        TraceStep.FINAL_OUTPUT,
        {"final_text": "好的，我帮你问问。"},
        occurred_at=datetime(2026, 6, 30, 16, 1, 2, tzinfo=TZ),
    )

    text = path.read_text(encoding="utf-8")
    assert '"step":"final_output"' in text
    assert "trace_jsonl-2026-06-30 16:01:02-INFO:" in text
    assert "好的，我帮你问问。" in text

    loaded = recorder.get_trace("trace_jsonl")
    assert len(loaded) == 1
    assert loaded[0].step == TraceStep.FINAL_OUTPUT
    assert loaded[0].content["final_text"] == "好的，我帮你问问。"
