from __future__ import annotations

import json

from mahjong_agent_runtime.action_contract import parse_action_with_repairs


def terminal_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "goal": "记录用户补充条件",
        "objective_status": "needs_tool",
        "reasoning_summary": "约束已写入，短句确认后停止。",
        "reply_to_user": "好的，记下了。",
        "tool_calls": [],
        "needs_human": False,
        "stop_reason": {
            "can_stop": True,
            "why": "约束已经写入。",
            "pending_work": [],
            "depends_on_tool_results": True,
        },
    }
    payload.update(overrides)
    return payload


def test_parse_action_repairs_status_when_all_other_fields_are_terminal() -> None:
    action, errors, repairs = parse_action_with_repairs(json.dumps(terminal_payload(), ensure_ascii=False))

    assert errors == []
    assert action.objective_status == "completed"
    assert action.reply_to_user == "好的，记下了。"
    assert repairs == [
        {
            "field": "objective_status",
            "from": "needs_tool",
            "to": "completed",
            "reason": "all other contract fields describe a terminal reply with no tool work",
        }
    ]


def test_parse_action_does_not_repair_when_tool_work_is_still_pending() -> None:
    payload = terminal_payload(
        reply_to_user="",
        tool_calls=[
            {
                "name": "search_current_games",
                "arguments": {"requirement": {}},
                "reason": "需要先查询当前局。",
            }
        ],
        stop_reason={
            "can_stop": False,
            "why": "等待查询结果。",
            "pending_work": ["查询当前局"],
            "depends_on_tool_results": True,
        },
    )

    action, errors, repairs = parse_action_with_repairs(json.dumps(payload, ensure_ascii=False))

    assert errors == []
    assert action.objective_status == "needs_tool"
    assert len(action.tool_calls) == 1
    assert repairs == []


def test_parse_action_does_not_hide_ambiguous_invalid_contract() -> None:
    payload = terminal_payload(reply_to_user="", stop_reason={"can_stop": True, "why": "", "pending_work": [], "depends_on_tool_results": False})

    action, errors, repairs = parse_action_with_repairs(json.dumps(payload, ensure_ascii=False))

    assert action.objective_status == "needs_human"
    assert repairs == []
    assert "needs_tool requires at least one tool_call" in errors
    assert "needs_tool requires empty reply_to_user" not in errors
