from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from mahjong_agent.trial_manual_game import TrialManualGameAdapter


TZ = ZoneInfo("Asia/Shanghai")


def parse_dt(value):
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    return datetime.fromisoformat(str(value))


def build_adapter(*, games: dict[str, dict] | None = None, captured: dict | None = None) -> TrialManualGameAdapter:
    games = games if games is not None else {}
    captured = captured if captured is not None else {}

    def action_record_factory(**kwargs):
        action = {
            "action_id": "act_manual",
            "idempotency_key": f"{kwargs['trace_id']}:{kwargs['stage']}:{kwargs['action_name']}",
            "protocol": "controlled_agent.v1",
            "stage": kwargs["stage"],
            "tool_name": kwargs["action_name"],
            "arguments": kwargs["arguments"],
            "source": kwargs["source"],
            "proposed_by": kwargs["proposed_by"],
            "risk_level": kwargs["risk_level"],
            "approval_required": kwargs["approval_required"],
            "reason": kwargs["reason"],
            "validation": kwargs["validation"],
        }
        captured["action"] = action
        return action

    def action_executor(action, fn):
        captured["executed_action"] = action
        return fn()

    def state_writer(**kwargs):
        game = {
            "id": kwargs["game_id"],
            "status": kwargs["status"],
            "organizer_id": kwargs["organizer_id"],
            "organizer_name": kwargs["organizer_name"],
            "source_text": kwargs["source_text"],
            "parsed": kwargs["parsed"],
            "notes": kwargs["notes"],
        }
        games[kwargs["game_id"]] = game
        return {"ok": True, "game_id": kwargs["game_id"], "status": kwargs["status"]}

    return TrialManualGameAdapter(
        action_record_factory=action_record_factory,
        action_executor=action_executor,
        action_plan_projector=lambda **kwargs: {
            "stage": kwargs["stage"],
            "source": kwargs["source"],
            "validated_actions": [kwargs["action"]],
        },
        game_state_writer=state_writer,
        game_lookup=lambda game_id: games.get(game_id),
        state_loader=lambda now: {"now": now.isoformat(), "game_count": len(games)},
        trace_id_factory=lambda: "trace_generated",
        now_factory=lambda: datetime(2026, 7, 1, 13, 0, tzinfo=TZ),
        parse_datetime=parse_dt,
        timezone=TZ,
        action_compactor=lambda action: {"tool_name": action["tool_name"], "code": action["validation"]["code"]},
        active_game_statuses={"待组局", "邀约中"},
        final_game_statuses={"已取消", "已成局"},
        game_cache_updater=lambda game_id: captured.setdefault("cached_game_id", game_id),
    )


def test_trial_manual_game_adapter_creates_controlled_game() -> None:
    captured: dict = {}
    adapter = build_adapter(captured=captured)

    result = adapter.create(
        {
            "trace_id": "trace_manual",
            "organizer_id": "zhang",
            "organizer_name": "张哥",
            "game_label": "杭麻",
            "variant": "caiqiao",
            "level": "0.5",
            "start_time": "14点半",
            "duration_hours": 4,
            "current_player_count": 2,
            "smoke": "no_smoke",
            "rules": "无花,包厢A",
        }
    )

    parsed = result["game"]["parsed"]
    assert result["ok"] is True
    assert parsed["game_type"] == "hangzhou_mahjong"
    assert parsed["game_label"] == "杭麻 财敲"
    assert parsed["start_time"] == "14:30"
    assert parsed["current_player_count"] == 2
    assert parsed["missing_count"] == 2
    assert parsed["rules"] == ["杭麻", "财敲", "无烟", "无花", "包厢A"]
    assert parsed["summary"] == "杭麻 财敲 0.5档 14:30 缺2 无烟"
    assert result["agent_actions"][0]["stage"] == "manual_create_game"
    assert captured["action"]["tool_name"] == "create_game"
    assert captured["action"]["arguments"]["duration_hours"] == 4.0
    assert result["game"]["notes"][-1]["action"] == {"tool_name": "create_game", "code": "manual_approved"}
    assert captured["cached_game_id"] == result["game"]["id"]


def test_trial_manual_game_adapter_rolls_past_time_to_next_day() -> None:
    adapter = build_adapter()

    result = adapter.create(
        {
            "trace_id": "trace_manual_tomorrow",
            "level": "1",
            "start_time": "12:00",
            "duration_hours": 5,
            "missing_count": 1,
            "now": "2026-07-01T13:00:00+08:00",
        }
    )

    assert result["game"]["parsed"]["start_at"] == "2026-07-02T12:00:00+08:00"
    assert result["game"]["parsed"]["current_player_count"] == 3
    assert result["game"]["parsed"]["missing_count"] == 1


def test_trial_manual_game_adapter_rejects_missing_required_fields() -> None:
    adapter = build_adapter()

    with pytest.raises(ValueError, match="档位"):
        adapter.create({"start_time": "14:00", "duration_hours": 4})

    with pytest.raises(ValueError, match="开局时间"):
        adapter.create({"level": "0.5", "duration_hours": 4})

    with pytest.raises(ValueError, match="预计时长"):
        adapter.create({"level": "0.5", "start_time": "14:00"})
