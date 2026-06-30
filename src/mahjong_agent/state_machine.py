from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .models import DEFAULT_TZ
from .workflow_models import EntityType, GameWorkflowStatus, StateTransition


STATE_MACHINE_VERSION = "controlled_state_machine.v1"


GAME_ALLOWED_TRANSITIONS: dict[GameWorkflowStatus, set[GameWorkflowStatus]] = {
    GameWorkflowStatus.NEED_CLARIFICATION: {
        GameWorkflowStatus.OPEN,
        GameWorkflowStatus.CANCELLED,
        GameWorkflowStatus.EXPIRED,
    },
    GameWorkflowStatus.OPEN: {
        GameWorkflowStatus.NEGOTIATING,
        GameWorkflowStatus.HOLDING,
        GameWorkflowStatus.CONFIRMED,
        GameWorkflowStatus.CANCELLED,
        GameWorkflowStatus.EXPIRED,
    },
    GameWorkflowStatus.NEGOTIATING: {
        GameWorkflowStatus.HOLDING,
        GameWorkflowStatus.CONFIRMED,
        GameWorkflowStatus.CANCELLED,
        GameWorkflowStatus.EXPIRED,
    },
    GameWorkflowStatus.HOLDING: {
        GameWorkflowStatus.CONFIRMED,
        GameWorkflowStatus.COMPLETED,
        GameWorkflowStatus.CANCELLED,
        GameWorkflowStatus.EXPIRED,
    },
    GameWorkflowStatus.CONFIRMED: {
        GameWorkflowStatus.COMPLETED,
        GameWorkflowStatus.CANCELLED,
    },
    GameWorkflowStatus.COMPLETED: set(),
    GameWorkflowStatus.CANCELLED: set(),
    GameWorkflowStatus.EXPIRED: set(),
}


@dataclass(slots=True)
class StateMachine:
    version: str = STATE_MACHINE_VERSION

    def can_transition_game(
        self,
        from_status: GameWorkflowStatus | str | None,
        to_status: GameWorkflowStatus | str,
    ) -> bool:
        target = self._coerce_game_status(to_status)
        if target is None:
            return False
        if from_status is None:
            return target in {GameWorkflowStatus.NEED_CLARIFICATION, GameWorkflowStatus.OPEN}
        source = self._coerce_game_status(from_status)
        if source is None:
            return False
        if source == target:
            return True
        return target in GAME_ALLOWED_TRANSITIONS.get(source, set())

    def validate_game_transition(
        self,
        *,
        entity_id: str,
        from_status: GameWorkflowStatus | str | None,
        to_status: GameWorkflowStatus | str,
        reason: str,
    ) -> StateTransition:
        target = self._coerce_game_status(to_status)
        allowed = target is not None and self.can_transition_game(from_status, target)
        return StateTransition(
            entity_type=EntityType.GAME.value,
            entity_id=entity_id,
            from_status=str(from_status) if from_status is not None else None,
            to_status=target.value if target else str(to_status),
            reason=reason,
            allowed=allowed,
            metadata={"state_machine_version": self.version},
        )

    def _coerce_game_status(self, status: GameWorkflowStatus | str | None) -> GameWorkflowStatus | None:
        if isinstance(status, GameWorkflowStatus):
            return status
        if status is None:
            return None
        try:
            return GameWorkflowStatus(str(status))
        except ValueError:
            return None


class WorkflowStateStore(Protocol):
    def current_status(self, entity_type: str, entity_id: str) -> str | None:
        ...

    def apply_transition(self, transition: StateTransition) -> StateTransition:
        ...

    def transition_history(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[StateTransition]:
        ...


class InMemoryWorkflowStateStore:
    """Small state ledger for the controlled workflow.

    The state machine decides whether a transition is legal. The store applies
    legal transitions, rejects stale transitions, and keeps an auditable history.
    A SQLite/Redis implementation can replace this class behind the same
    protocol when the local trial moves from in-memory to durable deployment.
    """

    def __init__(self) -> None:
        self._statuses: dict[tuple[str, str], str] = {}
        self._history: list[StateTransition] = []

    def current_status(self, entity_type: str, entity_id: str) -> str | None:
        return self._statuses.get((str(entity_type), str(entity_id)))

    def apply_transition(self, transition: StateTransition) -> StateTransition:
        key = (str(transition.entity_type), str(transition.entity_id))
        if not transition.allowed:
            rejected = _transition_with_metadata(
                transition,
                allowed=False,
                store_applied=False,
                store_rejected_reason="transition_not_allowed",
                store_previous_status=self._statuses.get(key),
            )
            self._history.append(rejected)
            return rejected

        current_status = self._statuses.get(key)
        if current_status != transition.from_status:
            rejected = _transition_with_metadata(
                transition,
                allowed=False,
                store_applied=False,
                store_rejected_reason="state_store_status_mismatch",
                store_previous_status=current_status,
                expected_from_status=transition.from_status,
            )
            self._history.append(rejected)
            return rejected

        applied = _transition_with_metadata(
            transition,
            store_applied=True,
            store_previous_status=current_status,
            store_new_status=transition.to_status,
        )
        self._statuses[key] = transition.to_status
        self._history.append(applied)
        return applied

    def transition_history(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[StateTransition]:
        history = list(self._history)
        if entity_type is not None:
            history = [item for item in history if item.entity_type == str(entity_type)]
        if entity_id is not None:
            history = [item for item in history if item.entity_id == str(entity_id)]
        return history


class SQLiteWorkflowStateStore:
    """SQLite-backed workflow state ledger for local durable deployments."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def current_status(self, entity_type: str, entity_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT status
                FROM controlled_workflow_entity_state
                WHERE entity_type = ? AND entity_id = ?
                """,
                (str(entity_type), str(entity_id)),
            ).fetchone()
        return str(row["status"]) if row else None

    def apply_transition(self, transition: StateTransition) -> StateTransition:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current_status = self._current_status_in_tx(conn, transition.entity_type, transition.entity_id)
            if not transition.allowed:
                result = _transition_with_metadata(
                    transition,
                    allowed=False,
                    store_applied=False,
                    store_rejected_reason="transition_not_allowed",
                    store_previous_status=current_status,
                    store_backend="sqlite",
                )
                self._insert_transition(conn, result)
                conn.commit()
                return result
            if current_status != transition.from_status:
                result = _transition_with_metadata(
                    transition,
                    allowed=False,
                    store_applied=False,
                    store_rejected_reason="state_store_status_mismatch",
                    store_previous_status=current_status,
                    expected_from_status=transition.from_status,
                    store_backend="sqlite",
                )
                self._insert_transition(conn, result)
                conn.commit()
                return result

            result = _transition_with_metadata(
                transition,
                store_applied=True,
                store_previous_status=current_status,
                store_new_status=transition.to_status,
                store_backend="sqlite",
            )
            conn.execute(
                """
                INSERT INTO controlled_workflow_entity_state (
                    entity_type, entity_id, status, updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_id)
                DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
                """,
                (
                    result.entity_type,
                    result.entity_id,
                    result.to_status,
                    datetime.now(DEFAULT_TZ).isoformat(),
                ),
            )
            self._insert_transition(conn, result)
            conn.commit()
            return result

    def transition_history(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[StateTransition]:
        sql = "SELECT * FROM controlled_workflow_state_transitions"
        params: list[str] = []
        clauses: list[str] = []
        if entity_type is not None:
            clauses.append("entity_type = ?")
            params.append(str(entity_type))
        if entity_id is not None:
            clauses.append("entity_id = ?")
            params.append(str(entity_id))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id ASC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._transition_from_row(row) for row in rows]

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS controlled_workflow_entity_state (
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (entity_type, entity_id)
                );

                CREATE TABLE IF NOT EXISTS controlled_workflow_state_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    allowed INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_controlled_workflow_state_transitions_entity
                    ON controlled_workflow_state_transitions(entity_type, entity_id, id);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _current_status_in_tx(
        self,
        conn: sqlite3.Connection,
        entity_type: str,
        entity_id: str,
    ) -> str | None:
        row = conn.execute(
            """
            SELECT status
            FROM controlled_workflow_entity_state
            WHERE entity_type = ? AND entity_id = ?
            """,
            (str(entity_type), str(entity_id)),
        ).fetchone()
        return str(row["status"]) if row else None

    def _insert_transition(self, conn: sqlite3.Connection, transition: StateTransition) -> None:
        conn.execute(
            """
            INSERT INTO controlled_workflow_state_transitions (
                entity_type, entity_id, from_status, to_status, reason,
                allowed, metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transition.entity_type,
                transition.entity_id,
                transition.from_status,
                transition.to_status,
                transition.reason,
                1 if transition.allowed else 0,
                json.dumps(transition.metadata, ensure_ascii=False, sort_keys=True),
                datetime.now(DEFAULT_TZ).isoformat(),
            ),
        )

    def _transition_from_row(self, row: sqlite3.Row) -> StateTransition:
        try:
            metadata = json.loads(str(row["metadata_json"] or "{}"))
        except json.JSONDecodeError:
            metadata = {"raw_metadata_json": row["metadata_json"]}
        return StateTransition(
            entity_type=str(row["entity_type"]),
            entity_id=str(row["entity_id"]),
            from_status=str(row["from_status"]) if row["from_status"] is not None else None,
            to_status=str(row["to_status"]),
            reason=str(row["reason"]),
            allowed=bool(row["allowed"]),
            metadata=metadata if isinstance(metadata, dict) else {"metadata": metadata},
        )


def _transition_with_metadata(
    transition: StateTransition,
    *,
    allowed: bool | None = None,
    **metadata: object,
) -> StateTransition:
    return replace(
        transition,
        allowed=transition.allowed if allowed is None else allowed,
        metadata={**transition.metadata, **metadata},
    )
