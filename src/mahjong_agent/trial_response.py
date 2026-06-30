from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .controlled_workflow import ControlledWorkflowResult
from .trial_projection import project_controlled_result_for_trial


class TrialPersistenceAdapter(Protocol):
    def persist(
        self,
        *,
        workflow_result: ControlledWorkflowResult,
        projected: dict[str, Any],
        source_text: str,
        sender_id: str,
        sender_name: str,
        trace_id: str,
        now: datetime,
    ) -> dict[str, Any]:
        ...


@dataclass
class TrialControlledResponseAdapter:
    """Build the trial-console response for the controlled workflow path.

    This adapter is deliberately thin: it projects a finished controlled
    workflow result, delegates persistence, and merges the persistence output
    into the legacy trial-page shape. It does not parse text, choose tools, or
    rewrite replies.
    """

    persistence_adapter: TrialPersistenceAdapter

    def build(
        self,
        *,
        workflow_result: ControlledWorkflowResult,
        source_text: str,
        sender_id: str,
        sender_name: str,
        trace_id: str,
        now: datetime,
    ) -> dict[str, Any]:
        projected = project_controlled_result_for_trial(workflow_result)
        persistence = self.persistence_adapter.persist(
            workflow_result=workflow_result,
            projected=projected,
            source_text=source_text,
            sender_id=sender_id,
            sender_name=sender_name,
            trace_id=trace_id,
            now=now,
        )
        return merge_controlled_trial_response(projected, persistence, trace_id=trace_id)


def merge_controlled_trial_response(
    projected: dict[str, Any],
    persistence: dict[str, Any],
    *,
    trace_id: str,
) -> dict[str, Any]:
    response = dict(projected)
    state = dict(response.get("state") or {})
    response["state"] = state
    response["persistence"] = persistence
    if persistence.get("game"):
        state["games"] = [persistence["game"]]
    if persistence.get("outbox"):
        response["outbox"] = list(persistence["outbox"])
    if persistence.get("agent_actions"):
        response["agent_actions"] = [
            *list(response.get("agent_actions") or []),
            *list(persistence["agent_actions"]),
        ]
    response["controlled_workflow_enabled"] = True
    response["api_trace_id"] = trace_id
    response["trace_id"] = trace_id
    response["legacy_path"] = False
    return response
