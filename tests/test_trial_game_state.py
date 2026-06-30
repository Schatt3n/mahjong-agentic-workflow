from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from mahjong_agent.models import GameRequest
from mahjong_agent.trial_game_state import (
    TrialCreateGameStateInput,
    TrialGameStateCreationAdapter,
    TrialGameStateCreationCallbacks,
)


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 7, 1, 16, 0, tzinfo=TZ)


def make_game() -> GameRequest:
    return GameRequest(
        id="game_1",
        organizer_id="zhang",
        organizer_name="张哥",
        channel_id="boss_trial",
        game_type="杭麻",
        level="0.5",
        missing_count=3,
        current_player_count=1,
        rules=["无烟"],
    )


def test_trial_game_state_creation_adapter_executes_controlled_create_game_and_caches() -> None:
    game = make_game()
    executed_actions: list[dict] = []
    writes: list[dict] = []
    cached: list[dict] = []

    def workflow_state_action_record(**kwargs):
        return {
            "action_id": "act_create",
            "idempotency_key": "idem_create",
            "source": kwargs["source"],
            "arguments": kwargs["arguments"],
            "validation": kwargs["validation"],
        }

    def execute_controlled_action(action, operation):
        executed_actions.append(action)
        return operation()

    def create_game_state_write(**kwargs):
        writes.append(kwargs)
        return {"ok": True, "game_id": kwargs["game"].id, "status": kwargs["status"]}

    def cache_game(game_arg, outbox, *, status, source_text):
        cached.append({"game_id": game_arg.id, "outbox": outbox, "status": status, "source_text": source_text})

    adapter = TrialGameStateCreationAdapter(
        TrialGameStateCreationCallbacks(
            game_status_label=lambda game_arg, missing_fields, has_outbox: "邀约中" if has_outbox else "待组局",
            workflow_state_action_record=workflow_state_action_record,
            execute_controlled_action=execute_controlled_action,
            create_game_state_write=create_game_state_write,
            compact_action_record=lambda action: {"action_id": action["action_id"]},
            cache_game=cache_game,
            single_action_plan_view=lambda **kwargs: {
                "stage": kwargs["stage"],
                "source": kwargs["source"],
                "action_id": kwargs["action"]["action_id"],
            },
        )
    )

    result = adapter.create(
        TrialCreateGameStateInput(
            trace_id="trace_create",
            game=game,
            sender_id="zhang",
            sender_name="张哥",
            source_text="下午两点0.5无烟杭麻，组一桌",
            parsed={"missing_count": 3, "start_at": "14:00", "level": "0.5", "rules": ["无烟"]},
            suggested_reply={"text": "好的，我帮你问问。"},
            fallback_reply_text="收到",
            missing_fields=[],
            decision_notes=["note"],
            user_action_record={"source": "llm", "reason": "用户明确要组局"},
            effective_user_action="create_game",
            outbox=[{"id": "out_1"}],
            now=NOW,
        )
    )

    assert result.status == "邀约中"
    assert result.create_result == {"ok": True, "game_id": "game_1", "status": "邀约中"}
    assert result.action["arguments"] == {
        "game_id": "game_1",
        "status": "邀约中",
        "organizer_id": "zhang",
        "organizer_name": "张哥",
        "missing_fields": [],
        "missing_count": 3,
        "start_at": "14:00",
        "level": "0.5",
        "rules": ["无烟"],
        "source": "analyze",
    }
    assert result.action["validation"]["notes"] == [
        "这是内部状态写入，不会自动外发消息。",
        "semantic_action_source=llm",
        "semantic_effective_action=create_game",
    ]
    assert executed_actions == [result.action]
    assert writes[0]["reply_text"] == "好的，我帮你问问。"
    assert writes[0]["notes"] == ["note", {"kind": "controlled_action", "action": {"action_id": "act_create"}}]
    assert cached == [
        {
            "game_id": "game_1",
            "outbox": [{"id": "out_1"}],
            "status": "邀约中",
            "source_text": "下午两点0.5无烟杭麻，组一桌",
        }
    ]
    assert result.action_plan == {"stage": "create_game", "source": "llm", "action_id": "act_create"}
