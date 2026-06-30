from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from .models import GameRequest


@dataclass(slots=True)
class TrialCreateGameStateInput:
    trace_id: str
    game: GameRequest
    sender_id: str
    sender_name: str
    source_text: str
    parsed: dict[str, Any]
    suggested_reply: dict[str, Any]
    fallback_reply_text: str
    missing_fields: list[str]
    decision_notes: list[Any]
    user_action_record: dict[str, Any]
    effective_user_action: str
    outbox: list[dict[str, Any]]
    now: datetime


@dataclass(slots=True)
class TrialCreateGameStateResult:
    status: str = ""
    action: dict[str, Any] = field(default_factory=dict)
    create_result: dict[str, Any] = field(default_factory=dict)
    action_plan: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TrialGameStateCreationCallbacks:
    game_status_label: Callable[[GameRequest, list[str], bool], str]
    workflow_state_action_record: Callable[..., dict[str, Any]]
    execute_controlled_action: Callable[[dict[str, Any], Callable[[], dict[str, Any]]], dict[str, Any]]
    create_game_state_write: Callable[..., dict[str, Any]]
    compact_action_record: Callable[[dict[str, Any]], dict[str, Any]]
    cache_game: Callable[..., None]
    single_action_plan_view: Callable[..., dict[str, Any]]


@dataclass(slots=True)
class TrialGameStateCreationAdapter:
    """Creates the legacy trial-page game state write through controlled action."""

    callbacks: TrialGameStateCreationCallbacks

    def create(self, data: TrialCreateGameStateInput) -> TrialCreateGameStateResult:
        source = str(data.user_action_record.get("source") or "orchestrator")
        status = self.callbacks.game_status_label(data.game, data.missing_fields, bool(data.outbox))
        action = self.callbacks.workflow_state_action_record(
            trace_id=data.trace_id,
            stage="create_game",
            action_name="create_game",
            arguments={
                "game_id": data.game.id,
                "status": status,
                "organizer_id": data.sender_id,
                "organizer_name": data.sender_name,
                "missing_fields": list(data.missing_fields),
                "missing_count": data.parsed.get("missing_count"),
                "start_at": data.parsed.get("start_at"),
                "level": data.parsed.get("level"),
                "rules": data.parsed.get("rules") or [],
                "source": "analyze",
            },
            proposed_by=source,
            source=source,
            risk_level="medium",
            approval_required=False,
            reason=str(
                data.user_action_record.get("reason")
                or "用户已明确要求组局且关键信息足够，后端准备创建当前局看板记录。"
            ),
            now=data.now,
            validation={
                "allowed": True,
                "code": "state_transition_allowed",
                "reason": "创建局动作通过状态机、语义动作提案和关键信息校验。",
                "notes": [
                    "这是内部状态写入，不会自动外发消息。",
                    f"semantic_action_source={data.user_action_record.get('source')}",
                    f"semantic_effective_action={data.effective_user_action}",
                ],
            },
        )
        create_result = self.callbacks.execute_controlled_action(
            action,
            lambda: self.callbacks.create_game_state_write(
                game=data.game,
                status=status,
                organizer_id=data.sender_id,
                organizer_name=data.sender_name,
                source_text=data.source_text,
                parsed=data.parsed,
                reply_text=str(data.suggested_reply.get("text") or data.fallback_reply_text),
                missing_fields=data.missing_fields,
                notes=[
                    *data.decision_notes,
                    {
                        "kind": "controlled_action",
                        "action": self.callbacks.compact_action_record(action),
                    },
                ],
                outbox=data.outbox,
            ),
        )
        if create_result.get("ok"):
            self.callbacks.cache_game(data.game, data.outbox, status=status, source_text=data.source_text)
        action_plan = self.callbacks.single_action_plan_view(
            stage="create_game",
            source=source,
            action=action,
        )
        return TrialCreateGameStateResult(
            status=status,
            action=action,
            create_result=create_result,
            action_plan=action_plan,
        )
