from __future__ import annotations

from mahjong_agent.trial_runtime_policy import (
    DEFAULT_RUNTIME_POLICY,
    RUNTIME_POLICY_VERSION,
    STATE_WRITE_STAGES,
    default_runtime_policy,
    trusted_action_proposer,
)


def test_default_runtime_policy_is_trial_mode(monkeypatch) -> None:
    monkeypatch.delenv("MAHJONG_CONTROLLED_AGENT_MODE", raising=False)
    monkeypatch.delenv("MAHJONG_LLM_REQUIRED_FOR_SIDE_EFFECT_TOOLS", raising=False)
    monkeypatch.delenv("MAHJONG_LLM_REQUIRED_FOR_STATE_WRITES", raising=False)

    policy = default_runtime_policy()

    assert policy["policy_version"] == RUNTIME_POLICY_VERSION
    assert policy["controlled_agent_mode"] == "trial"
    assert policy["llm_required_for_side_effect_tools"] is False
    assert policy["llm_required_for_state_writes"] is False
    assert DEFAULT_RUNTIME_POLICY["controlled_agent_mode"] == "trial"
    assert {"candidate_feedback", "message_delivery", "clear_board"}.issubset(STATE_WRITE_STAGES)


def test_default_runtime_policy_production_requires_llm_for_side_effects(monkeypatch) -> None:
    monkeypatch.setenv("MAHJONG_CONTROLLED_AGENT_MODE", "production")
    monkeypatch.delenv("MAHJONG_LLM_REQUIRED_FOR_SIDE_EFFECT_TOOLS", raising=False)
    monkeypatch.delenv("MAHJONG_LLM_REQUIRED_FOR_STATE_WRITES", raising=False)

    policy = default_runtime_policy()

    assert policy["controlled_agent_mode"] == "production"
    assert policy["llm_required_for_side_effect_tools"] is True
    assert policy["llm_required_for_state_writes"] is True
    assert "生产受控策略" in policy["reason"]


def test_default_runtime_policy_env_can_override_llm_requirements(monkeypatch) -> None:
    monkeypatch.setenv("MAHJONG_CONTROLLED_AGENT_MODE", "production")
    monkeypatch.setenv("MAHJONG_LLM_REQUIRED_FOR_SIDE_EFFECT_TOOLS", "0")
    monkeypatch.setenv("MAHJONG_LLM_REQUIRED_FOR_STATE_WRITES", "false")

    policy = default_runtime_policy()

    assert policy["controlled_agent_mode"] == "production"
    assert policy["llm_required_for_side_effect_tools"] is False
    assert policy["llm_required_for_state_writes"] is False


def test_trusted_action_proposer_accepts_only_explicit_trusted_sources() -> None:
    assert trusted_action_proposer("llm") is True
    assert trusted_action_proposer("rules", "human") is True
    assert trusted_action_proposer("boss_manual") is True
    assert trusted_action_proposer("rules", "backend_fallback") is False
    assert trusted_action_proposer("", None) is False
