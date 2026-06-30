from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from mahjong_agent.reply_approval import ReplyApprovalQueue
from mahjong_agent.tools import InMemoryPendingOutboxStore, OUTBOX_PENDING_APPROVAL
from mahjong_agent.workflow_models import (
    ActionName,
    ActionSource,
    ConversationContext,
    GuardedReply,
    ProposedAction,
    ReplyDraft,
    ReplyStatus,
    RiskLevel,
    UserMessage,
    ValidatedAction,
)


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 6, 30, 17, 0, tzinfo=TZ)


def make_context() -> ConversationContext:
    return ConversationContext(
        current_message=UserMessage(
            text="现在有0.5的吗",
            sender_id="zhang",
            sender_name="张哥",
            conversation_id="boss_trial",
            trace_id="trace_reply_approval",
            message_id="msg_reply_approval",
        )
    )


def make_validated() -> ValidatedAction:
    return ValidatedAction(
        proposed_action=ProposedAction(
            name=ActionName.ASK_CREATE_CONFIRMATION,
            source=ActionSource.LLM,
            confidence=0.9,
            reason="用户咨询现有局",
        ),
        effective_action=ActionName.ASK_CREATE_CONFIRMATION,
        allowed=True,
        code="no_existing_match_ask_create",
        reason="未找到匹配现有局，询问是否新组。",
        risk_level=RiskLevel.LOW,
        approval_required=False,
    )


def test_reply_approval_queue_stores_guarded_reply_as_pending_outbox() -> None:
    store = InMemoryPendingOutboxStore()
    reply_draft = ReplyDraft(
        text="现在没有合适的，要组一个吗？",
        status=ReplyStatus.NEEDS_APPROVAL,
        source=ActionSource.RULES,
        risk_level=RiskLevel.LOW,
    )
    guarded = GuardedReply(draft=reply_draft, final_text="现在没有合适的，要组一个吗？")

    result = ReplyApprovalQueue(store).enqueue(
        context=make_context(),
        reply_draft=reply_draft,
        guarded_reply=guarded,
        validated_action=make_validated(),
        now=NOW,
    )

    assert result.queued is True
    assert result.reason == "queued_for_owner_approval"
    assert len(result.outbox_items) == 1
    item = result.outbox_items[0]
    assert item["source"] == "controlled_reply"
    assert item["status"] == OUTBOX_PENDING_APPROVAL
    assert item["target_customer_id"] == "zhang"
    assert item["message_text"] == "现在没有合适的，要组一个吗？"
    assert item["metadata"]["kind"] == "boss_reply"
    assert item["metadata"]["effective_action"] == "ask_create_confirmation"
    assert item["metadata"]["guard_changed"] is False


def test_reply_approval_queue_skips_empty_reply() -> None:
    store = InMemoryPendingOutboxStore()
    reply_draft = ReplyDraft(text="", status=ReplyStatus.DRAFT)
    guarded = GuardedReply(draft=reply_draft, final_text="", status=ReplyStatus.DRAFT)

    result = ReplyApprovalQueue(store).enqueue(
        context=make_context(),
        reply_draft=reply_draft,
        guarded_reply=guarded,
        validated_action=make_validated(),
        now=NOW,
    )

    assert result.queued is False
    assert result.reason == "empty_reply_does_not_require_approval"
    assert store.list_pending() == []
