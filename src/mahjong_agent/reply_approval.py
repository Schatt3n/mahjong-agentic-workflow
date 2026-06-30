from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .models import DEFAULT_TZ
from .tools import OUTBOX_PENDING_APPROVAL, PendingOutboxStore
from .workflow_models import ConversationContext, GuardedReply, ReplyDraft, ValidatedAction


@dataclass(slots=True)
class ReplyApprovalQueueResult:
    queued: bool
    reason: str
    outbox_items: list[dict[str, Any]] = field(default_factory=list)
    policy: str = "最终回复只进入待老板审批队列，不自动发送。"

    def to_dict(self) -> dict[str, Any]:
        return {
            "queued": self.queued,
            "reason": self.reason,
            "outbox_items": list(self.outbox_items),
            "result_count": len(self.outbox_items),
            "policy": self.policy,
        }


class ReplyApprovalQueue:
    """Persists the final guarded reply as a pending boss approval draft.

    This queue is deliberately after ReplyGuard: it does not generate text,
    validate business actions, mutate game state, or send anything.
    """

    def __init__(self, store: PendingOutboxStore | None) -> None:
        self.store = store

    def enqueue(
        self,
        *,
        context: ConversationContext,
        reply_draft: ReplyDraft,
        guarded_reply: GuardedReply,
        validated_action: ValidatedAction,
        now: datetime | None = None,
    ) -> ReplyApprovalQueueResult:
        if self.store is None:
            return ReplyApprovalQueueResult(queued=False, reason="reply_approval_store_not_configured")

        final_text = str(guarded_reply.final_text or "").strip()
        if not final_text:
            return ReplyApprovalQueueResult(queued=False, reason="empty_reply_does_not_require_approval")

        created_at = (now or datetime.now(DEFAULT_TZ)).isoformat()
        draft = {
            "id": _reply_outbox_id(
                trace_id=context.current_message.trace_id,
                message_id=context.current_message.message_id,
                final_text=final_text,
            ),
            "trace_id": context.current_message.trace_id,
            "conversation_id": context.current_message.conversation_id,
            "target_customer_id": context.current_message.sender_id,
            "target_display_name": context.current_message.sender_name,
            "message_text": final_text,
            "status": OUTBOX_PENDING_APPROVAL,
            "source": "controlled_reply",
            "created_at": created_at,
            "updated_at": created_at,
            "metadata": {
                "kind": "boss_reply",
                "approval_status": OUTBOX_PENDING_APPROVAL,
                "workflow": "controlled_workflow.v1",
                "effective_action": validated_action.effective_action.value,
                "validation_code": validated_action.code,
                "approval_required": validated_action.approval_required,
                "risk_level": validated_action.risk_level.value,
                "reply_status": guarded_reply.status.value,
                "reply_draft_source": reply_draft.source.value,
                "reply_draft_status": reply_draft.status.value,
                "guard_changed": guarded_reply.changed,
                "guard_reasons": list(guarded_reply.guard_reasons),
                "source_message_id": context.current_message.message_id,
                "reply_idempotency_key": _reply_idempotency_key(
                    trace_id=context.current_message.trace_id,
                    message_id=context.current_message.message_id,
                    final_text=final_text,
                ),
            },
        }
        stored = self.store.create_many([draft])
        return ReplyApprovalQueueResult(
            queued=bool(stored),
            reason="queued_for_owner_approval" if stored else "store_returned_no_items",
            outbox_items=stored,
        )


def _reply_idempotency_key(*, trace_id: str, message_id: str, final_text: str) -> str:
    digest = hashlib.sha256(f"{trace_id}:{message_id}:{final_text}".encode("utf-8")).hexdigest()[:24]
    return f"reply_approval:{digest}"


def _reply_outbox_id(*, trace_id: str, message_id: str, final_text: str) -> str:
    digest = hashlib.sha256(_reply_idempotency_key(trace_id=trace_id, message_id=message_id, final_text=final_text).encode("utf-8")).hexdigest()[:24]
    return f"reply_{digest}"
