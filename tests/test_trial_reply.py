from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from mahjong_agent.models import CandidateRecommendation, GameRequest
from mahjong_agent.trial_reply import (
    TrialReplyDraftAdapter,
    TrialReplyDraftCallbacks,
    TrialReplyDraftInput,
    TrialReplyRulePolicy,
    TrialReplyRulePolicyCallbacks,
    TrialReplyRulePolicyInput,
)


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 7, 1, 16, 0, tzinfo=TZ)


def make_rule_policy() -> TrialReplyRulePolicy:
    return TrialReplyRulePolicy(
        TrialReplyRulePolicyCallbacks(
            pool_match_reply=lambda match: f"有的，{match['summary']}。要我帮你确认吗？",
            follow_up_text=lambda missing_fields, fallback, **kwargs: "你一个人吗？"
            if "known_players" in missing_fields
            else "",
            should_search_existing_pool=lambda source_text, effective_text, game: "有人" in source_text,
            is_explicit_grouping_request=lambda source_text, effective_text, game: "组" in source_text,
            pool_no_match_reply=lambda source_text, effective_text, sender_id: "0.5的暂时没有诶。要组一个吗？",
            brief_ack_reply=lambda: "好的，我帮你问问。",
        )
    )


def make_rule_input(**overrides) -> TrialReplyRulePolicyInput:
    data = {
        "source_text": "现在0.5有人吗",
        "effective_text": "现在0.5有人吗",
        "sender_id": "zhang",
        "sender_name": "张哥",
        "game": None,
        "workflow_followup_context": None,
        "missing_fields": [],
        "decision_reply": "收到",
        "recommendations": [],
        "outbox": [],
        "pool_matches": [],
        "tool_results": {},
    }
    data.update(overrides)
    return TrialReplyRulePolicyInput(**data)


def test_trial_reply_rule_policy_prefers_existing_pool_match() -> None:
    decision = make_rule_policy().decide(
        make_rule_input(pool_matches=[{"game_id": "pool_1", "summary": "18:00 0.5无烟，371"}])
    )

    assert decision.skip_llm is False
    assert decision.fallback["text"] == "有的，18:00 0.5无烟，371。要我帮你确认吗？"
    assert decision.fallback["selected_pool_game_id"] == "pool_1"


def test_trial_reply_rule_policy_asks_missing_field_before_pool_no_match_reply() -> None:
    decision = make_rule_policy().decide(
        make_rule_input(
            missing_fields=["known_players"],
            tool_results={"search_current_open_games": {"called": True, "result_count": 0}},
        )
    )

    assert decision.skip_llm is True
    assert decision.fallback["text"] == "你一个人吗？"
    assert decision.fallback["reasoning_summary"] == "强规则命中当前局池查询且没有匹配局，使用确定性回复，跳过 LLM。"


def test_trial_reply_rule_policy_skips_llm_for_pool_no_match_inquiry() -> None:
    decision = make_rule_policy().decide(
        make_rule_input(tool_results={"search_current_open_games": {"called": True, "result_count": 0}})
    )

    assert decision.skip_llm is True
    assert decision.fallback["text"] == "0.5的暂时没有诶。要组一个吗？"


def test_trial_reply_rule_policy_uses_brief_ack_when_outbox_exists() -> None:
    game = GameRequest(
        id="game_1",
        organizer_id="zhang",
        organizer_name="张哥",
        channel_id="boss_trial",
    )

    decision = make_rule_policy().decide(
        make_rule_input(
            source_text="帮我组一桌",
            game=game,
            outbox=[{"id": "out_1"}],
            tool_results={"send_message": {"called": True, "result_count": 1}},
        )
    )

    assert decision.skip_llm is False
    assert decision.fallback["text"] == "好的，我帮你问问。"


def test_trial_reply_draft_adapter_generates_reply_and_updates_memory() -> None:
    suggested_calls: list[dict] = []
    memory_calls: list[dict] = []
    game = GameRequest(
        id="game_1",
        organizer_id="zhang",
        organizer_name="张哥",
        channel_id="boss_trial",
    )
    recommendations = [CandidateRecommendation(customer_id="ran", display_name="冉姐", score=100)]
    outbox = [{"id": "out_1", "customer_id": "ran"}]
    pool_matches = [{"game_id": "pool_1"}]
    tool_results = {"send_message": {"called": True, "outbox": outbox}}

    def suggested_reply(**kwargs):
        suggested_calls.append(kwargs)
        return {"text": "好的，我帮你问问。", "source": "llm", "status": "待审批"}

    def update_sender_memory_after_reply(**kwargs) -> None:
        memory_calls.append(kwargs)

    adapter = TrialReplyDraftAdapter(
        TrialReplyDraftCallbacks(
            suggested_reply=suggested_reply,
            update_sender_memory_after_reply=update_sender_memory_after_reply,
        )
    )

    result = adapter.draft(
        TrialReplyDraftInput(
            conversation_id="boss_trial",
            sender_id="zhang",
            sender_name="张哥",
            source_text="帮我组一桌",
            effective_text="帮我组一桌",
            trace_id="trace_reply",
            game=game,
            workflow_followup_context={"previous_system_suggested_reply": "要组一个吗？"},
            missing_fields=[],
            decision_reply="收到",
            parsed={"intent_action": "find_players"},
            recommendations=recommendations,
            outbox=outbox,
            pool_matches=pool_matches,
            tool_results=tool_results,
            now=NOW,
        )
    )

    assert result.suggested_reply == {"text": "好的，我帮你问问。", "source": "llm", "status": "待审批"}
    assert suggested_calls[0]["tool_results"] is tool_results
    assert suggested_calls[0]["pool_matches"] is pool_matches
    assert suggested_calls[0]["recommendations"] is recommendations
    assert suggested_calls[0]["outbox"] is outbox
    assert suggested_calls[0]["game"] is game
    assert memory_calls == [
        {
            "conversation_id": "boss_trial",
            "sender_id": "zhang",
            "trace_id": "trace_reply",
            "suggested_reply": result.suggested_reply,
            "parsed": {"intent_action": "find_players"},
            "tool_results": tool_results,
            "pool_matches": pool_matches,
            "now": NOW,
        }
    ]
