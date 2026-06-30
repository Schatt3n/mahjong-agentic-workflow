from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from .workflow_models import ToolName


GAME_TYPE_LABELS = {
    "mahjong": "麻将",
    "hangzhou_mahjong": "杭麻",
    "sichuan_mahjong": "川麻",
    "hongzhong_mahjong": "红中",
    "zhuoji_mahjong": "捉鸡",
    "hunan_mahjong": "湖南麻将",
    "chongqing_mahjong": "重庆麻将",
}

VARIANT_LABELS = {
    "caiqiao": "财敲",
    "yaoji": "幺鸡",
    "suji": "素鸡",
    "yaoji_47": "幺鸡47",
    "shayu": "鲨鱼",
}

ActionRecordFactory = Callable[..., dict[str, Any]]
ActionExecutor = Callable[[dict[str, Any], Callable[[], dict[str, Any]]], dict[str, Any]]
ActionPlanProjector = Callable[..., dict[str, Any]]
GameLookup = Callable[[str], dict[str, Any] | None]
ApprovalStatusLabeler = Callable[[str | None], str]


@dataclass
class TrialControlledPersistenceAdapter:
    """Persist controlled workflow results into the current boss-trial store.

    This is a migration adapter for the existing trial console. It does not
    parse user text, choose actions, or rewrite replies; it only materializes a
    validated controlled-workflow result into the SQLite schema that the current
    web page already understands.
    """

    store: Any
    action_record_factory: ActionRecordFactory
    action_executor: ActionExecutor
    action_plan_projector: ActionPlanProjector
    game_lookup: GameLookup
    approval_status_labeler: ApprovalStatusLabeler

    def persist(
        self,
        *,
        workflow_result: Any,
        projected: dict[str, Any],
        source_text: str,
        sender_id: str,
        sender_name: str,
        trace_id: str,
        now: datetime,
    ) -> dict[str, Any]:
        run = workflow_result.run
        semantic = run.semantic_resolution
        validated = run.validated_action
        if not semantic or not validated:
            return {"persisted": False, "reason": "missing_workflow_contract"}
        if not validated.allowed:
            return {
                "persisted": False,
                "reason": "validated_action_not_allowed",
                "code": validated.code,
            }
        if validated.effective_action.value != "queue_invites":
            return {
                "persisted": False,
                "reason": "no_state_write_for_action",
                "effective_action": validated.effective_action.value,
            }
        if run.state_transitions and not all(item.allowed for item in run.state_transitions):
            return {"persisted": False, "reason": "state_transition_rejected"}

        game_id = self._controlled_game_id(validated.idempotency_key or trace_id)
        parsed = self._parsed_for_store(
            projected=projected,
            game_id=game_id,
            sender_id=sender_id,
            sender_name=sender_name,
        )
        projected_outbox = list(projected.get("outbox") or [])
        status = "邀约中" if projected_outbox else "待组局"
        create_game_action = self.action_record_factory(
            trace_id=trace_id,
            stage="create_game",
            action_name="create_game",
            arguments={
                "game_id": game_id,
                "status": status,
                "organizer_id": sender_id,
                "organizer_name": sender_name,
                "source": "controlled_workflow",
                "effective_action": validated.effective_action.value,
            },
            proposed_by=validated.proposed_action.source.value,
            source=validated.proposed_action.source.value,
            risk_level=validated.risk_level.value,
            approval_required=False,
            reason=validated.reason,
            now=now,
            idempotency_key=f"{validated.idempotency_key}:trial_create_game" if validated.idempotency_key else None,
            validation={
                "allowed": True,
                "code": validated.code,
                "reason": validated.reason,
                "notes": [
                    "受控工作流动作已通过 ActionValidator 和 StateMachine。",
                    "这里只做 SQLite 状态落库，不生成新的业务判断。",
                ],
            },
        )
        create_result = self.action_executor(
            create_game_action,
            lambda: self._create_game_state_write(
                game_id=game_id,
                status=status,
                organizer_id=sender_id,
                organizer_name=sender_name,
                source_text=source_text,
                parsed=parsed,
                reply_text=str((projected.get("suggested_reply") or {}).get("text") or ""),
                missing_fields=list((projected.get("parsed") or {}).get("missing_fields") or []),
                notes=[
                    {
                        "kind": "controlled_workflow",
                        "trace_id": trace_id,
                        "semantic_reasoning": semantic.reasoning_summary,
                        "validation_code": validated.code,
                    }
                ],
            ),
        )

        outbox_action = None
        outbox_result: dict[str, Any] = {"ok": True, "outbox": [], "result_count": 0}
        outbox_tool = workflow_result.tool_orchestration.result_for(ToolName.CREATE_PENDING_OUTBOX)
        if outbox_tool and outbox_tool.called and outbox_tool.allowed and projected_outbox:
            outbox_action = self.action_record_factory(
                trace_id=trace_id,
                stage="after_candidate_search",
                action_name="send_message",
                arguments={
                    "game_id": game_id,
                    "execution_mode": "create_pending_outbox",
                    "draft_count": len(projected_outbox),
                },
                proposed_by=validated.proposed_action.source.value,
                source=validated.proposed_action.source.value,
                risk_level="high",
                approval_required=True,
                reason="受控工作流已创建待审批邀约草稿，SQLite 仅持久化 outbox 和审批记录。",
                now=now,
                idempotency_key=f"{validated.idempotency_key}:trial_outbox" if validated.idempotency_key else None,
                validation={
                    "allowed": True,
                    "code": "create_pending_outbox_allowed",
                    "reason": "只创建待审批 outbox，不直接发送。",
                    "notes": ["外发消息仍需老板审批或手动复制。"],
                },
            )
            outbox_result = self.action_executor(
                outbox_action,
                lambda: self._create_outbox_state_write(
                    action=outbox_action,
                    game_id=game_id,
                    projected_outbox=projected_outbox,
                ),
            )

        persisted_game = self.game_lookup(game_id)
        agent_actions = [
            self.action_plan_projector(
                stage="create_game",
                source=validated.proposed_action.source.value,
                action=create_game_action,
            )
        ]
        if outbox_action:
            agent_actions.append(
                self.action_plan_projector(
                    stage="after_candidate_search",
                    source=validated.proposed_action.source.value,
                    action=outbox_action,
                )
            )
        return {
            "persisted": bool(create_result.get("ok")),
            "game_id": game_id,
            "game": persisted_game,
            "outbox": outbox_result.get("outbox") or [],
            "outbox_count": len(outbox_result.get("outbox") or []),
            "agent_actions": agent_actions,
            "create_result": create_result,
            "outbox_result": outbox_result,
        }

    def _create_game_state_write(
        self,
        *,
        game_id: str,
        status: str,
        organizer_id: str,
        organizer_name: str,
        source_text: str,
        parsed: dict[str, Any],
        reply_text: str,
        missing_fields: list[str],
        notes: list[Any],
    ) -> dict[str, Any]:
        self.store.create_game(
            game_id=game_id,
            status=status,
            organizer_id=organizer_id,
            organizer_name=organizer_name,
            source_text=source_text,
            parsed=parsed,
            reply_text=reply_text,
            missing_fields=missing_fields,
            notes=notes,
        )
        return {"ok": True, "game_id": game_id, "status": status}

    def _create_outbox_state_write(
        self,
        *,
        action: dict[str, Any],
        game_id: str,
        projected_outbox: list[dict[str, Any]],
    ) -> dict[str, Any]:
        outbox: list[dict[str, Any]] = []
        for item in projected_outbox:
            customer_id = str(item.get("customer_id") or "").strip()
            customer_name = str(item.get("customer_name") or customer_id or "牌友").strip()
            message_text = str(item.get("message_text") or "").strip()
            if not customer_id or not message_text:
                continue
            outbox_id = self.store.create_outbox(
                game_id=game_id,
                customer_id=customer_id,
                customer_name=customer_name,
                message_text=message_text,
                score=float(item.get("score") or 0),
                reasons=[str(value) for value in item.get("reasons") or []],
                warnings=[str(value) for value in item.get("warnings") or []],
            )
            approval = self.store.create_approval_request(
                target_type="outbox",
                target_id=outbox_id,
                action_id=str(action.get("action_id") or ""),
                idempotency_key=str(action.get("idempotency_key") or ""),
                risk_level=str(action.get("risk_level") or "high"),
                original_message_text=message_text,
                metadata={
                    "game_id": game_id,
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "draft_source": item.get("draft_source") or "controlled_workflow",
                    "tool_name": "send_message",
                    "execution_mode": "create_pending_outbox",
                    "controlled_workflow": True,
                },
            )
            persisted = self.store.outbox_item(outbox_id) or {}
            outbox.append(
                {
                    **persisted,
                    "approval": approval,
                    "approval_status": self.approval_status_labeler(approval.get("status")),
                    "approval_required": True,
                    "direct_send_executed": False,
                }
            )
        return {
            "ok": True,
            "called": True,
            "result_count": len(outbox),
            "direct_send_executed": False,
            "outbox": outbox,
        }

    def _controlled_game_id(self, key: str) -> str:
        digest = hashlib.sha256(f"controlled-workflow-game:{key}".encode("utf-8")).hexdigest()[:12]
        return f"cw_{digest}"

    def _parsed_for_store(
        self,
        *,
        projected: dict[str, Any],
        game_id: str,
        sender_id: str,
        sender_name: str,
    ) -> dict[str, Any]:
        parsed = dict(projected.get("parsed") or {})
        game_type = str(parsed.get("game_type") or "hangzhou_mahjong")
        variant = str(parsed.get("variant") or "").strip() or None
        game_label = " ".join(
            part
            for part in [
                GAME_TYPE_LABELS.get(game_type, "杭麻"),
                VARIANT_LABELS.get(variant or "", variant or ""),
            ]
            if part
        )
        missing_count = self._safe_int(parsed.get("missing_count"))
        current_count = self._safe_int(parsed.get("current_player_count"))
        if current_count is None and missing_count is not None:
            current_count = max(0, 4 - missing_count)
        rules = self._rules_for_store(parsed, game_label)
        start_time = self._start_time_for_store(parsed)
        duration_hours = self._safe_float(parsed.get("duration_hours"))
        return {
            **parsed,
            "id": game_id,
            "status": "open",
            "organizer_id": sender_id,
            "organizer_name": sender_name,
            "game_type": game_type,
            "game_label": game_label,
            "ruleset": game_type,
            "variant": variant,
            "variant_label": VARIANT_LABELS.get(variant or "", variant or ""),
            "level": str(parsed.get("level") or parsed.get("stake") or "").strip(),
            "start_time": start_time,
            "duration_hours": duration_hours,
            "current_player_count": current_count,
            "missing_count": missing_count,
            "rules": rules,
            "play_options": [VARIANT_LABELS.get(variant or "", variant or "")] if variant else [],
            "summary": str(parsed.get("summary") or "").strip()
            or " ".join(
                str(part)
                for part in [
                    game_label,
                    str(parsed.get("level") or parsed.get("stake") or "").strip(),
                    start_time,
                    f"缺{missing_count}" if missing_count is not None else "",
                    "、".join(rule for rule in rules if rule not in {game_label, "杭麻", "川麻"}),
                ]
                if part
            ),
        }

    def _rules_for_store(self, parsed: dict[str, Any], game_label: str) -> list[str]:
        rules = [game_label] if game_label else []
        smoke = str(parsed.get("smoke") or "").strip()
        smoke_labels = {
            "no_smoke": "无烟",
            "smoke_ok": "可吸烟",
            "any": "烟况都可",
        }
        if smoke:
            rules.append(smoke_labels.get(smoke, smoke))
        duration_mode = str(parsed.get("duration_mode") or "").strip()
        if duration_mode == "overnight":
            rules.append("通宵")
        for item in parsed.get("rules") or []:
            text = str(item).strip()
            if text:
                rules.append(text)
        return list(dict.fromkeys(rules))

    def _start_time_for_store(self, parsed: dict[str, Any]) -> str:
        start_time = str(parsed.get("start_time") or "").strip()
        if start_time == "people_ready":
            return "人齐开"
        if start_time:
            return start_time
        if str(parsed.get("start_time_mode") or "") == "people_ready":
            return "人齐开"
        return ""

    def _safe_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _safe_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
