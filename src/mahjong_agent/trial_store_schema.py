from __future__ import annotations

import sqlite3


TRIAL_STORE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    contact TEXT NOT NULL DEFAULT '',
    preferred_games TEXT NOT NULL DEFAULT '[]',
    preferred_levels TEXT NOT NULL DEFAULT '[]',
    usual_start_hours TEXT NOT NULL DEFAULT '[]',
    gender TEXT NOT NULL DEFAULT 'unknown',
    smoke_preference TEXT NOT NULL DEFAULT 'any',
    response_speed TEXT NOT NULL DEFAULT 'medium',
    response_rate REAL NOT NULL DEFAULT 0.5,
    last_invited_at TEXT,
    last_arrived_at TEXT,
    invite_count INTEGER NOT NULL DEFAULT 0,
    response_count INTEGER NOT NULL DEFAULT 0,
    arrival_count INTEGER NOT NULL DEFAULT 0,
    fatigue_score REAL NOT NULL DEFAULT 0,
    no_contact INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    usual_party_size INTEGER,
    usual_party_size_confidence REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS trial_games (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    organizer_id TEXT NOT NULL,
    organizer_name TEXT NOT NULL,
    source_text TEXT NOT NULL,
    parsed_json TEXT NOT NULL,
    reply_text TEXT NOT NULL DEFAULT '',
    missing_fields TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS outbox (
    id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    message_text TEXT NOT NULL,
    status TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0,
    reasons TEXT NOT NULL DEFAULT '[]',
    warnings TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    game_id TEXT,
    outbox_id TEXT,
    customer_id TEXT,
    feedback_type TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS followup_messages (
    id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL,
    related_outbox_id TEXT,
    recipient_id TEXT NOT NULL,
    recipient_name TEXT NOT NULL,
    message_text TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS controlled_actions (
    action_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    trace_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    proposed_by TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    risk_level TEXT NOT NULL DEFAULT 'unknown',
    side_effect INTEGER NOT NULL DEFAULT 1,
    approval_required INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    arguments_json TEXT NOT NULL DEFAULT '{}',
    validation_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    executed_at TEXT,
    error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_controlled_actions_trace
    ON controlled_actions(trace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_controlled_actions_stage
    ON controlled_actions(stage, status, created_at);
CREATE TABLE IF NOT EXISTS approval_requests (
    id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    action_id TEXT,
    idempotency_key TEXT,
    risk_level TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'pending',
    reviewer_id TEXT,
    reviewer_name TEXT,
    decision_reason TEXT NOT NULL DEFAULT '',
    original_message_text TEXT NOT NULL DEFAULT '',
    final_message_text TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    decided_at TEXT,
    UNIQUE(target_type, target_id)
);
CREATE INDEX IF NOT EXISTS idx_approval_requests_status
    ON approval_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_approval_requests_action
    ON approval_requests(action_id);
CREATE TABLE IF NOT EXISTS trace_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    level TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'log',
    event TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT '',
    schema_version TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    content TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_trace_events_trace
    ON trace_events(trace_id, id);
CREATE INDEX IF NOT EXISTS idx_trace_events_kind
    ON trace_events(direction, event, created_at);
CREATE TABLE IF NOT EXISTS state_transition_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    event TEXT NOT NULL,
    allowed INTEGER NOT NULL DEFAULT 1,
    reason TEXT NOT NULL DEFAULT '',
    trace_id TEXT NOT NULL DEFAULT '',
    action_id TEXT NOT NULL DEFAULT '',
    state_machine_version TEXT NOT NULL DEFAULT '',
    schema_version TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_state_transition_events_entity
    ON state_transition_events(entity_type, entity_id, id);
CREATE INDEX IF NOT EXISTS idx_state_transition_events_trace
    ON state_transition_events(trace_id, id);
CREATE INDEX IF NOT EXISTS idx_state_transition_events_event
    ON state_transition_events(event, created_at);
CREATE TABLE IF NOT EXISTS message_delivery_attempts (
    id TEXT PRIMARY KEY,
    outbox_id TEXT NOT NULL,
    approval_id TEXT,
    channel TEXT NOT NULL DEFAULT 'manual',
    recipient_id TEXT NOT NULL DEFAULT '',
    recipient_name TEXT NOT NULL DEFAULT '',
    message_text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'sent',
    idempotency_key TEXT NOT NULL UNIQUE,
    action_id TEXT NOT NULL DEFAULT '',
    trace_id TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    delivered_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_message_delivery_attempts_outbox
    ON message_delivery_attempts(outbox_id, created_at);
CREATE INDEX IF NOT EXISTS idx_message_delivery_attempts_trace
    ON message_delivery_attempts(trace_id, created_at);
CREATE TABLE IF NOT EXISTS runtime_policies (
    id TEXT PRIMARY KEY,
    policy_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT ''
);
"""


def ensure_trial_store_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(TRIAL_STORE_SCHEMA_SQL)
    ensure_column(conn, "customers", "gender", "TEXT NOT NULL DEFAULT 'unknown'")
    ensure_column(conn, "trial_games", "archived_at", "TEXT")
    ensure_column(conn, "trial_games", "final_reason", "TEXT NOT NULL DEFAULT ''")
    conn.commit()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {_pragma_column_name(row) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column in columns:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _pragma_column_name(row: sqlite3.Row | tuple) -> str:
    try:
        return str(row["name"])
    except (TypeError, IndexError):
        return str(row[1])
