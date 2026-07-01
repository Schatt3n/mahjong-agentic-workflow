from __future__ import annotations

import json
import sqlite3
from typing import Any

from .trial_labels import gender_label, normalize_gender


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def customer_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "display_name": row["display_name"],
        "contact": row["contact"],
        "preferred_games": _json_loads(row["preferred_games"], []),
        "preferred_levels": _json_loads(row["preferred_levels"], []),
        "usual_start_hours": _json_loads(row["usual_start_hours"], []),
        "gender": normalize_gender(row["gender"]),
        "gender_label": gender_label(row["gender"]),
        "smoke_preference": row["smoke_preference"],
        "response_speed": row["response_speed"],
        "response_rate": row["response_rate"],
        "last_invited_at": row["last_invited_at"],
        "last_arrived_at": row["last_arrived_at"],
        "invite_count": row["invite_count"],
        "response_count": row["response_count"],
        "arrival_count": row["arrival_count"],
        "fatigue_score": row["fatigue_score"],
        "no_contact": bool(row["no_contact"]),
        "notes": row["notes"],
        "usual_party_size": row["usual_party_size"],
        "usual_party_size_confidence": row["usual_party_size_confidence"],
    }


def approval_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "target_type": row["target_type"],
        "target_id": row["target_id"],
        "action_id": row["action_id"],
        "idempotency_key": row["idempotency_key"],
        "risk_level": row["risk_level"],
        "status": row["status"],
        "reviewer_id": row["reviewer_id"],
        "reviewer_name": row["reviewer_name"],
        "decision_reason": row["decision_reason"],
        "original_message_text": row["original_message_text"],
        "final_message_text": row["final_message_text"],
        "metadata": _json_loads(row["metadata_json"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "decided_at": row["decided_at"],
    }


def trace_event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "trace_id": row["trace_id"],
        "created_at": row["created_at"],
        "level": row["level"],
        "direction": row["direction"],
        "event": row["event"],
        "stage": row["stage"],
        "schema_version": row["schema_version"],
        "payload": _json_loads(row["payload_json"], {}),
        "content": row["content"],
    }


def state_transition_event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": row["created_at"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "from_status": row["from_status"],
        "to_status": row["to_status"],
        "event": row["event"],
        "allowed": bool(row["allowed"]),
        "reason": row["reason"],
        "trace_id": row["trace_id"],
        "action_id": row["action_id"],
        "state_machine_version": row["state_machine_version"],
        "schema_version": row["schema_version"],
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def delivery_attempt_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "outbox_id": row["outbox_id"],
        "approval_id": row["approval_id"],
        "channel": row["channel"],
        "recipient_id": row["recipient_id"],
        "recipient_name": row["recipient_name"],
        "message_text": row["message_text"],
        "status": row["status"],
        "idempotency_key": row["idempotency_key"],
        "action_id": row["action_id"],
        "trace_id": row["trace_id"],
        "error": row["error"],
        "metadata": _json_loads(row["metadata_json"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "delivered_at": row["delivered_at"],
    }
