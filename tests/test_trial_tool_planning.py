from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from mahjong_agent.trial_tool_planning import (
    TrialToolActionProposalFactory,
    TrialToolActionValidator,
    TrialToolCallNormalizer,
    TrialToolPlanPromptBuilder,
    TrialToolPlanPromptInput,
)


TZ = ZoneInfo("Asia/Shanghai")


OPEN_GAMES_SPEC = {
    "name": "search_current_open_games",
    "arguments_schema": {"type": "object", "properties": {"window_minutes": {"type": "integer"}}},
}
SEARCH_CANDIDATES_SPEC = {
    "name": "search_candidate_customers",
    "arguments_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
}
SEND_MESSAGE_SPEC = {
    "name": "send_message",
    "allowed_execution_modes": ["create_pending_outbox"],
    "arguments_schema": {
        "type": "object",
        "properties": {
            "execution_mode": {"type": "string", "enum": ["create_pending_outbox"]},
            "audience": {"type": "string"},
        },
    },
}


def make_action_validator(
    *,
    runtime_policy: dict | None = None,
    runtime_override=None,
    trusted_proposer=None,
    specs_by_stage: dict[str, list[dict]] | None = None,
) -> TrialToolActionValidator:
    specs = specs_by_stage or {
        "before_open_game_search": [OPEN_GAMES_SPEC],
        "after_open_game_search": [SEARCH_CANDIDATES_SPEC, SEND_MESSAGE_SPEC],
        "after_candidate_search": [SEND_MESSAGE_SPEC],
        "organizer_followup_draft": [SEND_MESSAGE_SPEC],
    }

    def tool_spec_for_stage(tool_name: str, stage: str) -> dict | None:
        return next((item for item in specs.get(stage, []) if item.get("name") == tool_name), None)

    return TrialToolActionValidator(
        critical_fields={"start_time", "known_players", "stake", "smoke", "duration"},
        tool_spec_for_stage=tool_spec_for_stage,
        tool_specs_for_stage=lambda stage: list(specs.get(stage, [])),
        runtime_policy_getter=lambda: runtime_policy or {},
        runtime_policy_validation_override=runtime_override or (lambda **kwargs: None),
        trusted_action_proposer=trusted_proposer or (lambda proposer, source: proposer in {"llm", "human"}),
    )


def make_prompt_input() -> TrialToolPlanPromptInput:
    return TrialToolPlanPromptInput(
        stage="after_open_game_search",
        now=datetime(2026, 6, 28, 22, 55, tzinfo=TZ),
        sender_id="zhang",
        sender_name="张哥",
        customer_profile={"display_name": "张哥", "preferred_levels": ["0.5", "1"]},
        source_text="可以",
        effective_text="通宵0.5有人吗\n可以",
        workflow_followup_context={"previous_system_suggested_reply": "0.5的暂时没有诶。要组一个吗？"},
        text_normalization={"normalized_text": "通宵0.5有人吗\n可以", "changed": False},
        decision_action="ask_clarification",
        parsed_game={"level": "0.5", "missing_count": 3},
        missing_fields=["start_time", "known_players"],
        critical_fields={"start_time", "known_players", "stake", "smoke", "duration"},
        available_tools=[
            {"name": "search_candidate_customers", "risk_level": "low"},
            {"name": "send_message", "risk_level": "high", "allowed_execution_modes": ["create_pending_outbox"]},
        ],
        tool_registry_version="tool_registry.v1",
        existing_tool_results={"search_current_open_games": {"called": True, "result_count": 0}},
        active_skills=[{"id": "multi_turn_slot_filling", "instructions": ["结合上一轮回复"]}],
    )


def test_trial_tool_plan_prompt_builder_builds_payload_contract() -> None:
    builder = TrialToolPlanPromptBuilder()

    payload = builder.build_payload(
        make_prompt_input(),
        model="deepseek-v4-flash",
        temperature=0.1,
        max_tokens=260,
        thinking_enabled=False,
        response_format="json_object",
    )

    assert payload["model"] == "deepseek-v4-flash"
    assert payload["temperature"] == 0.1
    assert payload["max_tokens"] == 260
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}
    assert "工具规划器" in payload["messages"][0]["content"]

    prompt = json.loads(payload["messages"][1]["content"])
    assert prompt["stage"] == "after_open_game_search"
    assert prompt["now"] == "2026-06-28 22:55:00"
    assert prompt["sender"] == {"id": "zhang", "name": "张哥"}
    assert prompt["workflow_followup_context"]["previous_system_suggested_reply"].endswith("要组一个吗？")
    assert prompt["critical_missing_fields"] == ["known_players", "start_time"]
    assert prompt["available_tools"][1]["name"] == "send_message"
    assert prompt["existing_tool_results"]["search_current_open_games"]["result_count"] == 0
    assert any("ToolGateway" in item for item in prompt["rules"])


def test_trial_tool_plan_prompt_builder_omits_optional_response_controls() -> None:
    payload = TrialToolPlanPromptBuilder().build_payload(
        make_prompt_input(),
        model="test-model",
        temperature=0.2,
        max_tokens=128,
    )

    assert "thinking" not in payload
    assert "response_format" not in payload


def test_trial_tool_call_normalizer_filters_unknown_duplicates_and_normalizes_send_mode() -> None:
    raw_calls = [
        {"tool_name": "unknown_tool", "arguments": {}, "reason": "不要执行"},
        {"tool_name": "search_candidate_customers", "arguments": {"limit": 5}, "reason": "找候选人"},
        {"name": "search_candidate_customers", "arguments": {"limit": 99}, "reason": "重复"},
        {
            "tool_name": "send_message",
            "arguments": {"execution_mode": "direct_send", "extra": "keep"},
            "call_reason": "创建邀约草稿",
        },
        "bad-call",
    ]
    available_tools = [
        {"name": "search_candidate_customers"},
        {"name": "send_message", "allowed_execution_modes": ["create_pending_outbox"]},
    ]

    normalized = TrialToolCallNormalizer().normalize(raw_calls, available_tools)

    assert [item["tool_name"] for item in normalized] == ["search_candidate_customers", "send_message"]
    assert normalized[0] == {
        "tool_name": "search_candidate_customers",
        "arguments": {"limit": 5},
        "reason": "找候选人",
        "requested_by": "llm",
    }
    assert normalized[1]["arguments"] == {
        "execution_mode": "create_pending_outbox",
        "requested_execution_mode": "direct_send",
        "extra": "keep",
    }
    assert normalized[1]["reason"] == "创建邀约草稿"


def test_trial_tool_call_normalizer_handles_non_list_and_bad_arguments() -> None:
    normalizer = TrialToolCallNormalizer()

    assert normalizer.normalize({"tool_name": "send_message"}, [{"name": "send_message"}]) == []
    assert normalizer.normalize(
        [{"tool_name": "send_message", "arguments": "bad"}],
        [{"name": "send_message"}],
    ) == [
        {
            "tool_name": "send_message",
            "arguments": {"execution_mode": "create_pending_outbox"},
            "reason": "LLM 请求调用工具。",
            "requested_by": "llm",
        }
    ]


def test_trial_tool_action_proposal_factory_builds_stable_controlled_action() -> None:
    def policy(tool_name: str, stage: str) -> dict:
        assert stage == "after_open_game_search"
        return {
            "risk_level": "high" if tool_name == "send_message" else "low",
            "side_effect": tool_name == "send_message",
            "approval_required": tool_name == "send_message",
        }

    factory = TrialToolActionProposalFactory(protocol_version="controlled_agent.v1", tool_policy=policy)
    now = datetime(2026, 6, 28, 22, 55, tzinfo=TZ)
    call = {
        "tool_name": "send_message",
        "arguments": {"execution_mode": "create_pending_outbox"},
        "requested_by": "llm",
        "reason": "创建待审批邀约",
    }

    first = factory.build(
        call=call,
        index=0,
        stage="after_open_game_search",
        source="llm",
        trace_id="trace_tool",
        now=now,
    )
    second = factory.build(
        call=call,
        index=0,
        stage="after_open_game_search",
        source="llm",
        trace_id="trace_tool",
        now=now,
    )
    other_index = factory.build(
        call=call,
        index=1,
        stage="after_open_game_search",
        source="llm",
        trace_id="trace_tool",
        now=now,
    )

    assert first == second
    assert first["action_id"].startswith("act_")
    assert first["idempotency_key"].startswith("trace_tool:after_open_game_search:send_message:")
    assert first["protocol"] == "controlled_agent.v1"
    assert first["proposed_by"] == "llm"
    assert first["risk_level"] == "high"
    assert first["side_effect"] is True
    assert first["approval_required"] is True
    assert first["created_at"] == "2026-06-28T22:55:00+08:00"
    assert other_index["idempotency_key"] != first["idempotency_key"]


def test_trial_tool_action_proposal_factory_sanitizes_bad_arguments_and_defaults_reason() -> None:
    factory = TrialToolActionProposalFactory(
        protocol_version="controlled_agent.v1",
        tool_policy=lambda tool_name, stage: {},
    )

    action = factory.build(
        call={"tool_name": "search_current_open_games", "arguments": "bad"},
        index=0,
        stage="before_open_game_search",
        source="backend_fallback",
        trace_id="trace_tool",
        now=datetime(2026, 6, 28, 22, 55, tzinfo=TZ),
    )

    assert action["arguments"] == {}
    assert action["reason"] == "请求调用工具。"
    assert action["risk_level"] == "unknown"
    assert action["side_effect"] is False
    assert action["approval_required"] is False


def test_trial_tool_action_validator_rejects_unavailable_tool_for_stage() -> None:
    validator = make_action_validator()

    verdict = validator.validate(
        proposal={"tool_name": "send_message", "stage": "before_open_game_search"},
        game=object(),
        missing_fields=[],
        tool_results={},
    )

    assert verdict["allowed"] is False
    assert verdict["code"] == "tool_not_available_for_stage"
    assert verdict["effective_arguments"] == {}


def test_trial_tool_action_validator_rejects_missing_game_context_for_candidate_tools() -> None:
    validator = make_action_validator()

    verdict = validator.validate(
        proposal={"tool_name": "search_candidate_customers", "stage": "after_open_game_search"},
        game=None,
        missing_fields=[],
        tool_results={},
    )

    assert verdict["allowed"] is False
    assert verdict["code"] == "missing_game_context"
    assert verdict["effective_arguments"] == {}


def test_trial_tool_action_validator_rejects_candidate_tools_when_critical_slots_missing() -> None:
    validator = make_action_validator()

    verdict = validator.validate(
        proposal={"tool_name": "search_candidate_customers", "stage": "after_open_game_search"},
        game=object(),
        missing_fields=["start_time", "stake", "optional_note"],
        tool_results={},
    )

    assert verdict["allowed"] is False
    assert verdict["code"] == "critical_slots_missing"
    assert verdict["missing_fields"] == ["stake", "start_time"]
    assert verdict["effective_arguments"] == {}


def test_trial_tool_action_validator_runtime_policy_requires_trusted_side_effect_proposer() -> None:
    validator = make_action_validator(runtime_policy={"llm_required_for_side_effect_tools": True})

    backend_verdict = validator.validate(
        proposal={
            "tool_name": "send_message",
            "stage": "after_candidate_search",
            "side_effect": True,
            "proposed_by": "backend_fallback",
            "source": "backend_fallback",
        },
        game=object(),
        missing_fields=[],
        tool_results={"search_candidate_customers": {"result_count": 1}},
    )
    llm_verdict = validator.validate(
        proposal={
            "tool_name": "send_message",
            "stage": "after_candidate_search",
            "side_effect": True,
            "proposed_by": "llm",
            "source": "llm",
        },
        game=object(),
        missing_fields=[],
        tool_results={"search_candidate_customers": {"result_count": 1}},
    )

    assert backend_verdict["allowed"] is False
    assert backend_verdict["code"] == "runtime_policy_llm_required_for_side_effect_tool"
    assert llm_verdict["allowed"] is True
    assert llm_verdict["effective_arguments"]["execution_mode"] == "create_pending_outbox"


def test_trial_tool_action_validator_send_message_sanitizes_args_and_requires_candidates() -> None:
    validator = make_action_validator()

    rejected = validator.validate(
        proposal={
            "tool_name": "send_message",
            "stage": "after_candidate_search",
            "arguments": {
                "execution_mode": "direct_send",
                "audience": "candidates",
                "unknown_arg": "drop-me",
            },
        },
        game=object(),
        missing_fields=[],
        tool_results={"search_candidate_customers": {"result_count": 0}},
    )
    allowed = validator.validate(
        proposal={
            "tool_name": "send_message",
            "stage": "after_candidate_search",
            "arguments": {
                "execution_mode": "direct_send",
                "audience": "candidates",
                "unknown_arg": "drop-me",
            },
        },
        game=object(),
        missing_fields=[],
        tool_results={"search_candidate_customers": {"result_count": 2}},
    )

    assert rejected["allowed"] is False
    assert rejected["code"] == "no_candidate_result"
    assert rejected["effective_arguments"] == {
        "execution_mode": "create_pending_outbox",
        "audience": "candidates",
    }
    assert allowed["allowed"] is True
    assert allowed["effective_arguments"] == {
        "execution_mode": "create_pending_outbox",
        "audience": "candidates",
    }
    assert "已剔除未注册参数：unknown_arg。" in allowed["notes"]
    assert "模型请求 direct_send 已被降级为 create_pending_outbox。" in allowed["notes"]
    assert "send_message 是高风险动作，只允许创建待审批 outbox，禁止直接发送。" in allowed["notes"]


def test_trial_tool_action_validator_merges_runtime_policy_override_notes() -> None:
    def override(**kwargs) -> dict:
        assert kwargs["stage"] == "after_open_game_search"
        assert kwargs["action_name"] == "search_candidate_customers"
        return {"code": "allowed_by_trial_policy", "notes": ["试用策略允许只读搜索。"]}

    validator = make_action_validator(runtime_override=override)

    verdict = validator.validate(
        proposal={
            "tool_name": "search_candidate_customers",
            "stage": "after_open_game_search",
            "arguments": {"limit": 6, "unknown_arg": "drop-me"},
        },
        game=object(),
        missing_fields=[],
        tool_results={},
    )

    assert verdict["allowed"] is True
    assert verdict["code"] == "allowed_by_trial_policy"
    assert verdict["effective_arguments"] == {"limit": 6}
    assert verdict["notes"] == ["已剔除未注册参数：unknown_arg。", "试用策略允许只读搜索。"]
