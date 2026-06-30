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
