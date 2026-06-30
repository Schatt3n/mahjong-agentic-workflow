from __future__ import annotations

import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from mahjong_agent.trial_delivery import TrialOutboxDeliveryAdapter, delivery_message_hash


TZ = ZoneInfo("Asia/Shanghai")


def approved_outbox() -> dict:
    return {
        "id": "outbox_001",
        "game_id": "game_001",
        "customer_id": "ran",
        "customer_name": "冉姐",
        "message_text": "冉姐，14:00，0.5无烟，打吗？",
        "status": "已审批",
        "approval": {
            "id": "approval_outbox_001",
            "status": "approved",
            "final_message_text": "冉姐，14:00，0.5无烟，打吗？",
        },
    }


def action_record_factory(**kwargs):
    return {
        "action_id": kwargs.get("action_id") or "action_generated",
        "tool_name": kwargs["action_name"],
        "idempotency_key": kwargs.get("idempotency_key"),
        **kwargs,
    }


def action_plan_projector(**kwargs):
    validation = kwargs["action"].get("validation") or {}
    key = "validated_actions" if validation.get("allowed") else "rejected_actions"
    return {"stage": kwargs["stage"], key: [{"tool_name": kwargs["action"]["tool_name"], "code": validation["code"]}]}


def test_trial_outbox_delivery_adapter_allows_approved_outbox() -> None:
    calls: dict[str, object] = {}
    reloaded: list[bool] = []
    cached: list[str] = []
    now = datetime(2026, 7, 1, 17, 0, tzinfo=TZ)

    def action_executor(action, fn):
        calls["action"] = action
        return fn()

    def delivery_executor(payload):
        calls["delivery_payload"] = payload
        return {
            "ok": True,
            "deduplicated": False,
            "delivery": {"status": "sent", "id": "delivery_001"},
            "outbox_item": {**approved_outbox(), "status": "已发送"},
        }

    adapter = TrialOutboxDeliveryAdapter(
        outbox_lookup=lambda outbox_id: approved_outbox() if outbox_id == "outbox_001" else None,
        delivery_executor=delivery_executor,
        action_record_factory=action_record_factory,
        action_executor=action_executor,
        action_plan_projector=action_plan_projector,
        state_loader=lambda current: {"now": current.isoformat()},
        trace_id_factory=lambda: "trace_generated",
        now_factory=lambda: now,
        parse_datetime=lambda value: None,
        customer_reloader=lambda: reloaded.append(True),
        game_cache_updater=cached.append,
    )

    result = adapter.send({"outbox_id": "outbox_001", "channel": "manual"})
    expected_hash = delivery_message_hash(
        outbox_id="outbox_001",
        channel="manual",
        message_text="冉姐，14:00，0.5无烟，打吗？",
    )
    expected_key = f"delivery:outbox_001:manual:{expected_hash}"
    expected_action_id = "act_" + hashlib.sha256(expected_key.encode("utf-8")).hexdigest()[:16]

    assert result["ok"] is True
    assert result["agent_actions"][0]["validated_actions"][0]["tool_name"] == "execute_outbox_delivery"
    assert calls["action"]["validation"]["allowed"] is True
    assert calls["action"]["idempotency_key"] == expected_key
    assert calls["action"]["action_id"] == expected_action_id
    assert calls["delivery_payload"]["idempotency_key"] == expected_key
    assert calls["delivery_payload"]["action_id"] == expected_action_id
    assert calls["delivery_payload"]["trace_id"] == "trace_generated"
    assert reloaded == [True]
    assert cached == ["game_001"]


def test_trial_outbox_delivery_adapter_rejects_unapproved_outbox_without_calling_delivery() -> None:
    called_delivery: list[bool] = []
    item = {
        **approved_outbox(),
        "status": "待审批",
        "approval": {"id": "approval_outbox_001", "status": "pending"},
    }

    def action_executor(action, fn):
        if not action["validation"]["allowed"]:
            return {"ok": False, "rejected": True, "reason": action["validation"]["reason"]}
        return fn()

    adapter = TrialOutboxDeliveryAdapter(
        outbox_lookup=lambda outbox_id: item,
        delivery_executor=lambda payload: called_delivery.append(True) or {"ok": True},
        action_record_factory=action_record_factory,
        action_executor=action_executor,
        action_plan_projector=action_plan_projector,
        state_loader=lambda current: {"loaded": True},
        trace_id_factory=lambda: "trace_generated",
        now_factory=lambda: datetime(2026, 7, 1, 17, 0, tzinfo=TZ),
        parse_datetime=lambda value: None,
    )

    result = adapter.send({"outbox_id": "outbox_001", "channel": "manual"})

    assert result["ok"] is False
    assert result["rejected"] is True
    assert result["agent_actions"][0]["rejected_actions"][0]["code"] == "delivery_rejected"
    assert called_delivery == []


def test_delivery_message_hash_is_stable() -> None:
    first = delivery_message_hash(outbox_id="outbox_001", channel="manual", message_text="hello")
    second = delivery_message_hash(outbox_id="outbox_001", channel="manual", message_text="hello")

    assert first == second
    assert len(first) == 16
