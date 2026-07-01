from __future__ import annotations

import json
from typing import Any


TOOL_REGISTRY_VERSION = "tool_registry.v1"

TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "search_current_open_games": {
        "name": "search_current_open_games",
        "risk_level": "low",
        "side_effect": False,
        "description": "搜索当前看板中未结束、未满、可拼或可加入的牌局。",
        "arguments_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "search_candidate_customers": {
        "name": "search_candidate_customers",
        "risk_level": "low",
        "side_effect": False,
        "description": "根据本局玩法、时间、档位、烟况和疲劳度，搜索可邀约客户候选人。",
        "arguments_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "send_message": {
        "name": "send_message",
        "risk_level": "high",
        "side_effect": True,
        "description": "创建待审批消息草稿。当前策略禁止直接外发，只能写入 outbox/followup 等老板审批。",
        "arguments_schema": {
            "type": "object",
            "properties": {"execution_mode": {"enum": []}},
            "required": ["execution_mode"],
            "additionalProperties": False,
        },
        "policy": "approval_required; direct_send_forbidden",
    },
}

TOOL_STAGE_POLICY: dict[str, dict[str, dict[str, Any]]] = {
    "before_open_game_search": {
        "search_current_open_games": {},
    },
    "after_open_game_search": {
        "search_candidate_customers": {},
        "send_message": {"allowed_execution_modes": ["create_pending_outbox"]},
    },
    "after_candidate_search": {
        "send_message": {"allowed_execution_modes": ["create_pending_outbox"]},
    },
    "organizer_followup_draft": {
        "send_message": {"allowed_execution_modes": ["create_pending_followup"]},
    },
}


def tool_specs_for_stage(stage: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for tool_name, stage_policy in (TOOL_STAGE_POLICY.get(stage) or {}).items():
        base = TOOL_REGISTRY.get(tool_name)
        if not base:
            continue
        spec = _clone_jsonable(base)
        spec["stage"] = stage
        spec["registry_version"] = TOOL_REGISTRY_VERSION
        allowed_modes = list(stage_policy.get("allowed_execution_modes") or [])
        if allowed_modes:
            spec["allowed_execution_modes"] = allowed_modes
            schema = spec.get("arguments_schema") if isinstance(spec.get("arguments_schema"), dict) else {}
            properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
            execution_mode = properties.get("execution_mode") if isinstance(properties.get("execution_mode"), dict) else {}
            execution_mode["enum"] = allowed_modes
            properties["execution_mode"] = execution_mode
            schema["properties"] = properties
            spec["arguments_schema"] = schema
        specs.append(spec)
    return specs


def tool_spec_for_stage(tool_name: str, stage: str) -> dict[str, Any] | None:
    for spec in tool_specs_for_stage(stage):
        if str(spec.get("name") or "") == tool_name:
            return spec
    return None


def _clone_jsonable(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, ensure_ascii=False))
