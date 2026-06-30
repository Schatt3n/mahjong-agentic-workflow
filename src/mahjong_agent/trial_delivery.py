from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from .trial_persistence import ActionExecutor, ActionPlanProjector, ActionRecordFactory


TraceIdFactory = Callable[[], str]
NowFactory = Callable[[], datetime]
DateTimeParser = Callable[[Any], datetime | None]
OutboxLookup = Callable[[str], dict[str, Any] | None]
DeliveryExecutor = Callable[[dict[str, Any]], dict[str, Any]]
StateLoader = Callable[[datetime], dict[str, Any]]
CustomerReloader = Callable[[], None]
GameCacheUpdater = Callable[[str], None]


@dataclass
class TrialOutboxDeliveryAdapter:
    """Controlled adapter for boss-trial outbox delivery.

    This adapter performs the send-gateway checks and action projection for the
    trial UI. The actual delivery side effect remains delegated to the supplied
    executor, so current SQLite trial tables keep working during migration.
    """

    outbox_lookup: OutboxLookup
    delivery_executor: DeliveryExecutor
    action_record_factory: ActionRecordFactory
    action_executor: ActionExecutor
    action_plan_projector: ActionPlanProjector
    state_loader: StateLoader
    trace_id_factory: TraceIdFactory
    now_factory: NowFactory
    parse_datetime: DateTimeParser
    customer_reloader: CustomerReloader | None = None
    game_cache_updater: GameCacheUpdater | None = None

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        trace_id = str(payload.get("trace_id") or self.trace_id_factory())
        now = self.parse_datetime(payload.get("now")) or self.now_factory()
        outbox_id = str(payload.get("outbox_id") or "").strip()
        channel = str(payload.get("channel") or "manual").strip() or "manual"
        item = self.outbox_lookup(outbox_id) if outbox_id else None
        approval = item.get("approval") if isinstance(item, dict) and isinstance(item.get("approval"), dict) else {}
        final_message = str(
            payload.get("message_text")
            or approval.get("final_message_text")
            or (item or {}).get("message_text")
            or ""
        )
        delivery_hash = delivery_message_hash(
            outbox_id=outbox_id,
            channel=channel,
            message_text=final_message,
        )
        delivery_idempotency_key = f"delivery:{outbox_id}:{channel}:{delivery_hash}"
        delivery_action_id = "act_" + hashlib.sha256(delivery_idempotency_key.encode("utf-8")).hexdigest()[:16]
        allowed, notes = self._delivery_gate(outbox_id=outbox_id, item=item, approval=approval)
        action = self.action_record_factory(
            trace_id=trace_id,
            stage="message_delivery",
            action_name="execute_outbox_delivery",
            arguments={
                "outbox_id": outbox_id,
                "channel": channel,
                "message_hash": delivery_hash,
            },
            proposed_by="boss_manual",
            source="delivery_gateway",
            risk_level="high",
            approval_required=True,
            reason="审批通过后的外发动作必须经过发送网关、幂等和 delivery 账本。",
            now=now,
            validation={
                "allowed": allowed,
                "code": "delivery_allowed" if allowed else "delivery_rejected",
                "reason": "审批已通过，允许执行受控发送。" if allowed else "发送动作未满足审批或状态条件。",
                "notes": notes or ["发送动作会写入 message_delivery_attempts，并把 outbox 推进为已发送。"],
            },
            action_id=delivery_action_id,
            idempotency_key=delivery_idempotency_key,
        )
        execution_payload = {
            **payload,
            "trace_id": trace_id,
            "outbox_id": outbox_id,
            "channel": channel,
            "message_text": final_message,
            "idempotency_key": delivery_idempotency_key,
            "action_id": action["action_id"],
            "now": now.isoformat(),
        }
        result = self.action_executor(action, lambda: self.delivery_executor(execution_payload))
        if result.get("ok") and not result.get("deduplicated") and self.customer_reloader:
            self.customer_reloader()
        game_id = _game_id_from_delivery_result(result) or ((item or {}).get("game_id") if isinstance(item, dict) else None)
        if game_id and self.game_cache_updater:
            self.game_cache_updater(str(game_id))
        result["agent_actions"] = [
            self.action_plan_projector(stage="message_delivery", source="delivery_gateway", action=action)
        ]
        result["state"] = self.state_loader(now)
        return result

    def _delivery_gate(
        self,
        *,
        outbox_id: str,
        item: dict[str, Any] | None,
        approval: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        allowed = bool(
            item
            and approval
            and approval.get("status") == "approved"
            and str(item.get("status") or "") in {"已审批", "已复制", "已发送"}
        )
        notes: list[str] = []
        if not outbox_id:
            notes.append("缺少 outbox_id。")
        if not item:
            notes.append("找不到 outbox。")
        elif not approval or approval.get("status") != "approved":
            notes.append("草稿尚未审批通过。")
        elif str(item.get("status") or "") not in {"已审批", "已复制", "已发送"}:
            notes.append(f"当前状态 {item.get('status')} 不能发送。")
        return allowed, notes


def delivery_message_hash(*, outbox_id: str, channel: str, message_text: str) -> str:
    return hashlib.sha256(
        json.dumps(
            {"outbox_id": outbox_id, "channel": channel, "message_text": message_text},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]


def _game_id_from_delivery_result(result: dict[str, Any]) -> str | None:
    outbox_item = result.get("outbox_item") if isinstance(result.get("outbox_item"), dict) else {}
    game_id = outbox_item.get("game_id")
    return str(game_id) if game_id else None
