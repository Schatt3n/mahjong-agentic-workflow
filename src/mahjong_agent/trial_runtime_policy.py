from __future__ import annotations

import os
from typing import Any

from .trial_routing import env_bool


RUNTIME_POLICY_VERSION = "runtime_policy.v1"
DEFAULT_RUNTIME_POLICY: dict[str, Any] = {
    "policy_version": RUNTIME_POLICY_VERSION,
    "controlled_agent_mode": "trial",
    "read_only_mode": False,
    "state_writes_enabled": True,
    "delivery_enabled": True,
    "approval_enabled": True,
    "eval_writes_enabled": True,
    "llm_required_for_side_effect_tools": False,
    "llm_required_for_state_writes": False,
    "reason": "默认试用策略：允许人工审批后的受控写入和手动发送。",
}

STATE_WRITE_STAGES = {
    "candidate_feedback",
    "create_game",
    "manual_create_game",
    "manual_feedback",
    "profile_update",
    "approval_decision",
    "message_delivery",
    "clear_board",
}


def default_runtime_policy() -> dict[str, Any]:
    policy = dict(DEFAULT_RUNTIME_POLICY)
    mode = str(os.getenv("MAHJONG_CONTROLLED_AGENT_MODE") or policy["controlled_agent_mode"]).strip().lower()
    if mode in {"prod", "production", "controlled", "strict"}:
        policy["controlled_agent_mode"] = "production"
        policy["llm_required_for_side_effect_tools"] = True
        policy["llm_required_for_state_writes"] = True
        policy["reason"] = "生产受控策略：副作用工具和业务状态写入必须由 LLM 或人工明确提案。"
    else:
        policy["controlled_agent_mode"] = "trial"
    policy["llm_required_for_side_effect_tools"] = env_bool(
        "MAHJONG_LLM_REQUIRED_FOR_SIDE_EFFECT_TOOLS",
        bool(policy["llm_required_for_side_effect_tools"]),
    )
    policy["llm_required_for_state_writes"] = env_bool(
        "MAHJONG_LLM_REQUIRED_FOR_STATE_WRITES",
        bool(policy["llm_required_for_state_writes"]),
    )
    return policy


def trusted_action_proposer(*values: Any) -> bool:
    trusted = {"llm", "boss_manual", "human", "operator"}
    return any(str(value or "").strip().lower() in trusted for value in values)
