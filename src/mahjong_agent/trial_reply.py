from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from .models import CandidateRecommendation, GameRequest


@dataclass(slots=True)
class TrialReplyDraftInput:
    conversation_id: str
    sender_id: str
    sender_name: str
    source_text: str
    effective_text: str
    trace_id: str
    game: GameRequest | None
    workflow_followup_context: dict[str, Any]
    missing_fields: list[str]
    decision_reply: str
    parsed: dict[str, Any]
    recommendations: list[CandidateRecommendation]
    outbox: list[dict[str, Any]]
    pool_matches: list[dict[str, Any]]
    tool_results: dict[str, Any]
    now: datetime


@dataclass(slots=True)
class TrialReplyDraftResult:
    suggested_reply: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TrialReplyRulePolicyInput:
    source_text: str
    effective_text: str
    sender_id: str
    sender_name: str
    game: GameRequest | None
    workflow_followup_context: dict[str, Any] | None
    missing_fields: list[str]
    decision_reply: str
    recommendations: list[CandidateRecommendation]
    outbox: list[dict[str, Any]]
    pool_matches: list[dict[str, Any]]
    tool_results: dict[str, Any]


@dataclass(slots=True)
class TrialReplyRuleDecision:
    fallback: dict[str, Any]
    skip_llm: bool = False
    skip_reasoning_summary: str = ""


@dataclass(slots=True)
class TrialReplyRulePolicyCallbacks:
    pool_match_reply: Callable[[dict[str, Any]], str]
    follow_up_text: Callable[..., str]
    should_search_existing_pool: Callable[[str, str, GameRequest | None], bool]
    is_explicit_grouping_request: Callable[[str, str, GameRequest | None], bool]
    pool_no_match_reply: Callable[[str, str, str], str]
    brief_ack_reply: Callable[[], str]


@dataclass(slots=True)
class TrialReplyRulePolicy:
    """Builds deterministic fallback replies before optional LLM drafting."""

    callbacks: TrialReplyRulePolicyCallbacks

    def decide(self, data: TrialReplyRulePolicyInput) -> TrialReplyRuleDecision:
        fallback_text = self.fallback_text(data)
        fallback = {
            "text": fallback_text,
            "source": "rules",
            "model": None,
            "needs_approval": True,
            "status": "待审批",
            "selected_pool_game_id": data.pool_matches[0]["game_id"] if data.pool_matches else None,
            "notes": ["规则兜底生成，老板确认后再复制发送。"],
        }
        if self.should_skip_llm_for_pool_no_match(data):
            return TrialReplyRuleDecision(
                fallback={
                    **fallback,
                    "reasoning_summary": "强规则命中当前局池查询且没有匹配局，使用确定性回复，跳过 LLM。",
                },
                skip_llm=True,
                skip_reasoning_summary="强规则命中当前局池查询且没有匹配局，使用确定性回复，跳过 LLM。",
            )
        return TrialReplyRuleDecision(fallback=fallback)

    def fallback_text(self, data: TrialReplyRulePolicyInput) -> str:
        if data.pool_matches:
            return self.callbacks.pool_match_reply(data.pool_matches[0])
        follow_up = self.callbacks.follow_up_text(
            data.missing_fields,
            data.decision_reply,
            sender_id=data.sender_id,
            game=data.game,
        )
        if follow_up:
            return follow_up
        pool_result = data.tool_results.get("search_current_open_games") if isinstance(data.tool_results, dict) else {}
        if (
            isinstance(pool_result, dict)
            and pool_result.get("called") is True
            and int(pool_result.get("result_count") or 0) == 0
            and self.callbacks.should_search_existing_pool(data.source_text, data.effective_text, data.game)
        ):
            return self.callbacks.pool_no_match_reply(data.source_text, data.effective_text, data.sender_id)
        if data.game and data.outbox:
            return self.callbacks.brief_ack_reply()
        if data.game and data.recommendations:
            return self.callbacks.brief_ack_reply()
        if data.game:
            return "好的，我先帮你留意下。"
        return data.decision_reply or f"{data.sender_name}，我可以帮你组局。你把时间、玩法、档位和现在几个人发我一下。"

    def should_skip_llm_for_pool_no_match(self, data: TrialReplyRulePolicyInput) -> bool:
        if data.workflow_followup_context:
            return False
        pool_result = data.tool_results.get("search_current_open_games") if isinstance(data.tool_results, dict) else {}
        return (
            isinstance(pool_result, dict)
            and pool_result.get("called") is True
            and int(pool_result.get("result_count") or 0) == 0
            and self.callbacks.should_search_existing_pool(data.source_text, data.effective_text, data.game)
            and not self.callbacks.is_explicit_grouping_request(data.source_text, data.effective_text, data.game)
        )


@dataclass(slots=True)
class TrialReplyDraftCallbacks:
    suggested_reply: Callable[..., dict[str, Any]]
    update_sender_memory_after_reply: Callable[..., None]


@dataclass(slots=True)
class TrialReplyDraftAdapter:
    """Runs the legacy trial-page reply stage after tools and state context exist."""

    callbacks: TrialReplyDraftCallbacks

    def draft(self, data: TrialReplyDraftInput) -> TrialReplyDraftResult:
        suggested = self.callbacks.suggested_reply(
            source_text=data.source_text,
            effective_text=data.effective_text,
            trace_id=data.trace_id,
            sender_id=data.sender_id,
            sender_name=data.sender_name,
            game=data.game,
            workflow_followup_context=data.workflow_followup_context,
            missing_fields=data.missing_fields,
            decision_reply=data.decision_reply,
            recommendations=data.recommendations,
            outbox=data.outbox,
            pool_matches=data.pool_matches,
            tool_results=data.tool_results,
            now=data.now,
        )
        self.callbacks.update_sender_memory_after_reply(
            conversation_id=data.conversation_id,
            sender_id=data.sender_id,
            trace_id=data.trace_id,
            suggested_reply=suggested,
            parsed=data.parsed,
            tool_results=data.tool_results,
            pool_matches=data.pool_matches,
            now=data.now,
        )
        return TrialReplyDraftResult(suggested_reply=suggested)
