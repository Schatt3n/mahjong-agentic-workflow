from __future__ import annotations

from mahjong_agent.trial_tool_registry import (
    TOOL_REGISTRY,
    TOOL_REGISTRY_VERSION,
    tool_spec_for_stage,
    tool_specs_for_stage,
)


def test_tool_specs_for_stage_returns_expected_stage_tools() -> None:
    before_tools = tool_specs_for_stage("before_open_game_search")
    after_open_tools = tool_specs_for_stage("after_open_game_search")
    after_candidate_tools = tool_specs_for_stage("after_candidate_search")
    followup_tools = tool_specs_for_stage("organizer_followup_draft")

    assert [item["name"] for item in before_tools] == ["search_current_open_games"]
    assert [item["name"] for item in after_open_tools] == ["search_candidate_customers", "send_message"]
    assert [item["name"] for item in after_candidate_tools] == ["send_message"]
    assert [item["name"] for item in followup_tools] == ["send_message"]
    assert all(item["registry_version"] == TOOL_REGISTRY_VERSION for item in before_tools + after_open_tools)


def test_send_message_execution_modes_are_scoped_by_stage() -> None:
    after_candidate = tool_spec_for_stage("send_message", "after_candidate_search")
    followup = tool_spec_for_stage("send_message", "organizer_followup_draft")

    assert after_candidate is not None
    assert after_candidate["allowed_execution_modes"] == ["create_pending_outbox"]
    assert after_candidate["arguments_schema"]["properties"]["execution_mode"]["enum"] == [
        "create_pending_outbox"
    ]
    assert followup is not None
    assert followup["allowed_execution_modes"] == ["create_pending_followup"]
    assert followup["arguments_schema"]["properties"]["execution_mode"]["enum"] == [
        "create_pending_followup"
    ]


def test_stage_tool_specs_do_not_mutate_global_registry() -> None:
    spec = tool_spec_for_stage("send_message", "after_candidate_search")
    assert spec is not None

    spec["arguments_schema"]["properties"]["execution_mode"]["enum"].append("direct_send")

    assert TOOL_REGISTRY["send_message"]["arguments_schema"]["properties"]["execution_mode"]["enum"] == []
    fresh_spec = tool_spec_for_stage("send_message", "after_candidate_search")
    assert fresh_spec is not None
    assert fresh_spec["arguments_schema"]["properties"]["execution_mode"]["enum"] == [
        "create_pending_outbox"
    ]


def test_unknown_stage_or_tool_returns_empty_result() -> None:
    assert tool_specs_for_stage("unknown_stage") == []
    assert tool_spec_for_stage("send_message", "unknown_stage") is None
    assert tool_spec_for_stage("unknown_tool", "after_candidate_search") is None
