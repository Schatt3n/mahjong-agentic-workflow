import sqlite3
from typing import Any

from mahjong_agent import (
    approval_from_row,
    customer_from_row,
    delivery_attempt_from_row,
    state_transition_event_from_row,
    trace_event_from_row,
)


def row_from_values(values: dict[str, Any]) -> sqlite3.Row:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    conn.execute(f"CREATE TABLE row_test ({columns})")
    conn.execute(f"INSERT INTO row_test VALUES ({placeholders})", tuple(values.values()))
    return conn.execute("SELECT * FROM row_test").fetchone()


def test_customer_from_row_decodes_profile_json_and_labels_gender() -> None:
    row = row_from_values(
        {
            "id": "zhang",
            "display_name": "张哥",
            "contact": "wx_zhang",
            "preferred_games": '["杭麻","川麻"]',
            "preferred_levels": '["0.5","1"]',
            "usual_start_hours": "[14,20]",
            "gender": "男",
            "smoke_preference": "any",
            "response_speed": "fast",
            "response_rate": 0.8,
            "last_invited_at": "2026-06-28T14:00:00+08:00",
            "last_arrived_at": None,
            "invite_count": 3,
            "response_count": 2,
            "arrival_count": 1,
            "fatigue_score": 0.2,
            "no_contact": 0,
            "notes": "常打杭麻",
            "usual_party_size": 1,
            "usual_party_size_confidence": 0.9,
        }
    )

    customer = customer_from_row(row)

    assert customer["preferred_games"] == ["杭麻", "川麻"]
    assert customer["preferred_levels"] == ["0.5", "1"]
    assert customer["usual_start_hours"] == [14, 20]
    assert customer["gender"] == "male"
    assert customer["gender_label"] == "男"
    assert customer["no_contact"] is False


def test_customer_from_row_falls_back_on_invalid_json() -> None:
    row = row_from_values(
        {
            "id": "unknown",
            "display_name": "新客",
            "contact": "",
            "preferred_games": "{bad",
            "preferred_levels": "",
            "usual_start_hours": "",
            "gender": "",
            "smoke_preference": "any",
            "response_speed": "medium",
            "response_rate": 0.5,
            "last_invited_at": None,
            "last_arrived_at": None,
            "invite_count": 0,
            "response_count": 0,
            "arrival_count": 0,
            "fatigue_score": 0,
            "no_contact": 1,
            "notes": "",
            "usual_party_size": None,
            "usual_party_size_confidence": 0,
        }
    )

    customer = customer_from_row(row)

    assert customer["preferred_games"] == []
    assert customer["preferred_levels"] == []
    assert customer["usual_start_hours"] == []
    assert customer["gender"] == "unknown"
    assert customer["no_contact"] is True


def test_approval_from_row_decodes_metadata() -> None:
    row = row_from_values(
        {
            "id": "approval_1",
            "target_type": "outbox",
            "target_id": "outbox_1",
            "action_id": "action_1",
            "idempotency_key": "idem_1",
            "risk_level": "medium",
            "status": "pending",
            "reviewer_id": None,
            "reviewer_name": None,
            "decision_reason": "",
            "original_message_text": "张哥，打吗？",
            "final_message_text": "张哥，打吗？",
            "metadata_json": '{"trace_id":"trace_1"}',
            "created_at": "2026-06-28T14:00:00+08:00",
            "updated_at": "2026-06-28T14:00:00+08:00",
            "decided_at": None,
        }
    )

    approval = approval_from_row(row)

    assert approval["metadata"] == {"trace_id": "trace_1"}
    assert approval["status"] == "pending"


def test_trace_and_state_rows_decode_json_and_booleans() -> None:
    trace = trace_event_from_row(
        row_from_values(
            {
                "id": 7,
                "trace_id": "trace_1",
                "created_at": "2026-06-28T14:00:00+08:00",
                "level": "INFO",
                "direction": "llm",
                "event": "semantic_resolution",
                "stage": "semantic",
                "schema_version": "trace.v1",
                "payload_json": '{"action":"create_game"}',
                "content": "content",
            }
        )
    )
    transition = state_transition_event_from_row(
        row_from_values(
            {
                "id": 8,
                "created_at": "2026-06-28T14:01:00+08:00",
                "entity_type": "game",
                "entity_id": "game_1",
                "from_status": "待组局",
                "to_status": "邀约中",
                "event": "candidate_invited",
                "allowed": 1,
                "reason": "ok",
                "trace_id": "trace_1",
                "action_id": "action_1",
                "state_machine_version": "state_machine.v1",
                "schema_version": "state_transition_event.v1",
                "metadata_json": '{"outbox_id":"outbox_1"}',
            }
        )
    )

    assert trace["id"] == 7
    assert trace["payload"] == {"action": "create_game"}
    assert transition["allowed"] is True
    assert transition["metadata"] == {"outbox_id": "outbox_1"}


def test_delivery_attempt_from_row_decodes_metadata() -> None:
    row = row_from_values(
        {
            "id": "delivery_1",
            "outbox_id": "outbox_1",
            "approval_id": "approval_1",
            "channel": "manual",
            "recipient_id": "zhang",
            "recipient_name": "张哥",
            "message_text": "张哥，打吗？",
            "status": "created",
            "idempotency_key": "idem_1",
            "action_id": "action_1",
            "trace_id": "trace_1",
            "error": "",
            "metadata_json": '{"operator":"boss"}',
            "created_at": "2026-06-28T14:00:00+08:00",
            "updated_at": "2026-06-28T14:00:00+08:00",
            "delivered_at": None,
        }
    )

    attempt = delivery_attempt_from_row(row)

    assert attempt["metadata"] == {"operator": "boss"}
    assert attempt["recipient_name"] == "张哥"
