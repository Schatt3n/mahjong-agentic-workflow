from __future__ import annotations

import json

from mahjong_agent_runtime.action_contract import parse_action_with_repairs


def test_missing_plan_step_ids_are_repaired_as_structural_metadata():
    payload = {
        "goal": "完成未来预约",
        "objective_status": "completed",
        "reasoning_summary": "局已创建，等待招募窗口。",
        "objective_plan": [
            {"step_id": "1", "title": "创建局", "status": "done", "depends_on": []},
            {"title": "等待窗口", "status": "done", "depends_on": ["1"]},
        ],
        "reply_to_user": "好，记上了。",
        "tool_calls": [],
        "needs_human": False,
        "stop_reason": {
            "can_stop": True,
            "why": "本轮已经完成",
            "pending_work": [],
            "depends_on_tool_results": True,
        },
    }

    action, errors, repairs = parse_action_with_repairs(json.dumps(payload, ensure_ascii=False))

    assert errors == []
    assert action.objective_plan[1]["step_id"] == "2"
    assert repairs == [
        {
            "field": "objective_plan[2].step_id",
            "from": None,
            "to": "2",
            "reason": "plan step identifiers are structural metadata and can be assigned deterministically",
        }
    ]


def test_single_or_null_plan_dependencies_are_repaired_to_arrays():
    payload = {
        "goal": "安全回复客户",
        "objective_status": "completed",
        "reasoning_summary": "不披露其他客户的私聊。",
        "objective_plan": [
            {"step_id": "1", "title": "理解请求", "status": "done", "depends_on": None},
            {"step_id": "2", "title": "安全回复", "status": "done", "depends_on": "1"},
        ],
        "reply_to_user": "别人的私聊我不方便转述。",
        "tool_calls": [],
        "needs_human": False,
        "stop_reason": {
            "can_stop": True,
            "why": "已安全回复",
            "pending_work": [],
            "depends_on_tool_results": False,
        },
    }

    action, errors, repairs = parse_action_with_repairs(json.dumps(payload, ensure_ascii=False))

    assert errors == []
    assert action.objective_plan[0]["depends_on"] == []
    assert action.objective_plan[1]["depends_on"] == ["1"]
    assert [item["field"] for item in repairs] == [
        "objective_plan[1].depends_on",
        "objective_plan[2].depends_on",
    ]
