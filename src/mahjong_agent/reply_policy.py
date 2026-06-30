from __future__ import annotations

from dataclasses import dataclass, field

from .tool_orchestrator import ToolOrchestrationResult
from .workflow_models import (
    ActionName,
    ActionSource,
    ConversationContext,
    ReplyDraft,
    ReplyStatus,
    RiskLevel,
    SemanticResolution,
    StateTransition,
    ToolName,
    ValidatedAction,
)


MISSING_SLOT_QUESTIONS: dict[str, str] = {
    "game_type": "打杭麻吗？",
    "stake": "打多大？",
    "start_time_mode": "大概什么时候开？",
    "party_size": "你这边几个人？",
    "smoke": "烟况有要求吗？",
    "duration_mode": "大概要打多久？",
    "duration_hours": "大概要打几个小时？",
}


@dataclass(slots=True)
class ReplyPolicyInput:
    context: ConversationContext
    semantic_resolution: SemanticResolution
    validated_action: ValidatedAction
    tool_result: ToolOrchestrationResult
    state_transitions: list[StateTransition] = field(default_factory=list)


class ReplyPolicy:
    """Generate boss-facing drafts from final action results.

    This layer intentionally uses ValidatedAction and ToolResult only. It does
    not re-parse the user message, call tools, or mutate state.
    """

    def draft(
        self,
        *,
        context: ConversationContext,
        semantic_resolution: SemanticResolution,
        validated_action: ValidatedAction,
        tool_result: ToolOrchestrationResult,
        state_transitions: list[StateTransition] | None = None,
    ) -> ReplyDraft:
        data = ReplyPolicyInput(
            context=context,
            semantic_resolution=semantic_resolution,
            validated_action=validated_action,
            tool_result=tool_result,
            state_transitions=state_transitions or [],
        )
        action = validated_action.effective_action
        if action == ActionName.HUMAN_REVIEW:
            return self._draft("这个我先转人工确认一下。", data, "高风险或不确定，转人工。", risk=RiskLevel.HIGH)
        if action == ActionName.IGNORE:
            return self._draft("", data, "无需回复。", status=ReplyStatus.DRAFT)
        if action == ActionName.ASK_CLARIFICATION:
            return self._draft(self._clarification_text(validated_action.missing_slots), data, validated_action.reason)
        if action == ActionName.ASK_CREATE_CONFIRMATION:
            return self._draft("现在没有合适的，要组一个吗？", data, validated_action.reason)
        if action == ActionName.MATCH_EXISTING_GAME:
            return self._draft(self._existing_game_text(tool_result), data, validated_action.reason)
        if action == ActionName.QUEUE_INVITES:
            return self._draft(self._queue_invites_text(tool_result), data, validated_action.reason)
        if action == ActionName.ACCEPT_SEAT:
            return self._draft("好的，先帮你确认这桌。", data, validated_action.reason)
        if action == ActionName.CLOSE_GAME:
            return self._draft("收到，我先标记这桌需要处理。", data, validated_action.reason)
        return self._draft("我先确认一下。", data, f"未覆盖的有效动作：{action.value}")

    def _draft(
        self,
        text: str,
        data: ReplyPolicyInput,
        reasoning_summary: str,
        *,
        status: ReplyStatus = ReplyStatus.NEEDS_APPROVAL,
        risk: RiskLevel | None = None,
    ) -> ReplyDraft:
        return ReplyDraft(
            text=text,
            status=status,
            reasoning_summary=reasoning_summary,
            source=ActionSource.RULES,
            risk_level=risk or data.validated_action.risk_level,
            metadata={
                "effective_action": data.validated_action.effective_action.value,
                "validation_code": data.validated_action.code,
                "tool_results": [
                    {
                        "tool_name": item.request.tool_name.value,
                        "called": item.called,
                        "allowed": item.allowed,
                        "error": item.error,
                    }
                    for item in data.tool_result.tool_results
                ],
                "state_transitions": [
                    {
                        "entity_type": item.entity_type,
                        "entity_id": item.entity_id,
                        "from_status": item.from_status,
                        "to_status": item.to_status,
                        "allowed": item.allowed,
                    }
                    for item in data.state_transitions
                ],
            },
        )

    def _clarification_text(self, missing_slots: list[str]) -> str:
        questions = [MISSING_SLOT_QUESTIONS.get(slot, f"{slot} 再确认一下？") for slot in missing_slots[:3]]
        if not questions:
            return "我再确认一下。"
        return " ".join(questions)

    def _existing_game_text(self, tool_result: ToolOrchestrationResult) -> str:
        result = tool_result.result_for(ToolName.SEARCH_CURRENT_OPEN_GAMES)
        matches = (result.result.get("matches") if result and result.called and result.allowed else []) or []
        if not matches:
            return "我先看一下有没有合适的。"
        summary = str(matches[0].get("summary") or "有一桌合适的")
        return f"{summary}，要不要加？"

    def _queue_invites_text(self, tool_result: ToolOrchestrationResult) -> str:
        outbox = tool_result.result_for(ToolName.CREATE_PENDING_OUTBOX)
        drafts = (outbox.result.get("drafts") if outbox and outbox.called and outbox.allowed else []) or []
        if drafts:
            return "好的，我帮你问问。"
        candidate_result = tool_result.result_for(ToolName.SEARCH_CANDIDATE_CUSTOMERS)
        if candidate_result and candidate_result.called and candidate_result.allowed:
            return "我先看下合适的人选。"
        return "我先确认一下。"
