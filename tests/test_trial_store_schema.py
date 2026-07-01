import sqlite3

from mahjong_agent import TRIAL_STORE_SCHEMA_SQL, ensure_trial_store_schema


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def index_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA index_list({table})").fetchall()}


def test_trial_store_schema_creates_core_tables_and_indexes() -> None:
    conn = sqlite3.connect(":memory:")

    ensure_trial_store_schema(conn)

    tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    assert {
        "customers",
        "trial_games",
        "outbox",
        "feedback",
        "followup_messages",
        "controlled_actions",
        "approval_requests",
        "trace_events",
        "state_transition_events",
        "message_delivery_attempts",
        "runtime_policies",
    } <= tables
    assert {
        "display_name",
        "preferred_games",
        "gender",
        "usual_party_size",
        "usual_party_size_confidence",
    } <= table_columns(conn, "customers")
    assert {"archived_at", "final_reason"} <= table_columns(conn, "trial_games")
    assert "idx_controlled_actions_trace" in index_names(conn, "controlled_actions")
    assert "idx_trace_events_trace" in index_names(conn, "trace_events")
    assert "idx_state_transition_events_entity" in index_names(conn, "state_transition_events")
    assert "idx_message_delivery_attempts_outbox" in index_names(conn, "message_delivery_attempts")
    assert "CREATE TABLE IF NOT EXISTS customers" in TRIAL_STORE_SCHEMA_SQL


def test_trial_store_schema_backfills_legacy_columns() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE customers (id TEXT PRIMARY KEY, display_name TEXT NOT NULL)")
    conn.execute(
        """
        CREATE TABLE trial_games (
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
        )
        """
    )

    ensure_trial_store_schema(conn)
    ensure_trial_store_schema(conn)

    assert "gender" in table_columns(conn, "customers")
    assert {"archived_at", "final_reason"} <= table_columns(conn, "trial_games")
