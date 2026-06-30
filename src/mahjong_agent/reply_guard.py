from __future__ import annotations

import re

from .tool_orchestrator import ToolOrchestrationResult
from .workflow_models import ActionName, GuardedReply, ReplyDraft, ReplyStatus, RiskLevel, ToolName, ValidatedAction


INVITE_PROMISE_PATTERN = re.compile(r"帮你问|问问|问人|摇人|帮你摇")
ROOM_PROMISE_PATTERN = re.compile(r"房间.*(确认|留|定|安排)|留着|留座")


class ReplyGuard:
    """Safety consistency guard for reply drafts.

    Guard only checks contradictions and unsafe promises. It does not own the
    business flow and should not replace ReplyPolicy decisions.
    """

    def guard(
        self,
        *,
        draft: ReplyDraft,
        validated_action: ValidatedAction,
        tool_result: ToolOrchestrationResult,
    ) -> GuardedReply:
        text = draft.text
        reasons: list[str] = []

        if draft.risk_level == RiskLevel.HIGH or validated_action.effective_action == ActionName.HUMAN_REVIEW:
            if text != "这个我先转人工确认一下。":
                text = "这个我先转人工确认一下。"
                reasons.append("高风险或人工审核动作必须转人工。")

        if INVITE_PROMISE_PATTERN.search(text) and not self._has_pending_outbox(tool_result):
            text = "我先确认一下。"
            reasons.append("没有待审批邀约草稿，不能承诺已经帮用户问人。")

        if ROOM_PROMISE_PATTERN.search(text):
            text = "我先确认一下房间情况。"
            reasons.append("没有房态确认结果，不能承诺留座或确认房间。")

        if validated_action.missing_slots and validated_action.effective_action == ActionName.ASK_CLARIFICATION:
            if "要组一个吗" in text:
                text = " ".join(_question_for_missing(slot) for slot in validated_action.missing_slots[:3])
                reasons.append("缺关键字段时不能回复无匹配局建局确认。")

        return GuardedReply(
            draft=draft,
            final_text=text,
            changed=bool(reasons),
            guard_reasons=reasons,
            status=ReplyStatus.GUARDED if reasons else draft.status,
        )

    def _has_pending_outbox(self, tool_result: ToolOrchestrationResult) -> bool:
        result = tool_result.result_for(ToolName.CREATE_PENDING_OUTBOX)
        if not result or not result.called or not result.allowed:
            return False
        drafts = result.result.get("drafts")
        return isinstance(drafts, list) and bool(drafts)


def _question_for_missing(slot: str) -> str:
    mapping = {
        "game_type": "打杭麻吗？",
        "stake": "打多大？",
        "start_time_mode": "大概什么时候开？",
        "party_size": "你这边几个人？",
        "smoke": "烟况有要求吗？",
        "duration_mode": "大概要打多久？",
    }
    return mapping.get(slot, "我再确认一下？")
