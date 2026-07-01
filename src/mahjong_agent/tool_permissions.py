from __future__ import annotations

from .workflow_models import ActionName, ToolName


ALLOWED_TOOLS_BY_ACTION: dict[ActionName, frozenset[ToolName]] = {
    ActionName.SEARCH_EXISTING_GAMES: frozenset({ToolName.SEARCH_CURRENT_OPEN_GAMES}),
    ActionName.ASK_CREATE_CONFIRMATION: frozenset({ToolName.SEARCH_CURRENT_OPEN_GAMES}),
    ActionName.MATCH_EXISTING_GAME: frozenset({ToolName.SEARCH_CURRENT_OPEN_GAMES}),
    ActionName.QUEUE_INVITES: frozenset(
        {
            ToolName.SEARCH_CURRENT_OPEN_GAMES,
            ToolName.SEARCH_CANDIDATE_CUSTOMERS,
            ToolName.CREATE_PENDING_OUTBOX,
            ToolName.CREATE_GAME,
        }
    ),
    ActionName.CREATE_GAME: frozenset(
        {
            ToolName.SEARCH_CURRENT_OPEN_GAMES,
            ToolName.SEARCH_CANDIDATE_CUSTOMERS,
            ToolName.CREATE_PENDING_OUTBOX,
            ToolName.CREATE_GAME,
        }
    ),
    ActionName.ACCEPT_SEAT: frozenset({ToolName.RECORD_SEAT_ACCEPTANCE}),
    ActionName.JOIN_GAME: frozenset({ToolName.RECORD_SEAT_ACCEPTANCE}),
    ActionName.CANCEL_GAME: frozenset({ToolName.CLOSE_GAME}),
    ActionName.CLOSE_GAME: frozenset({ToolName.CLOSE_GAME}),
    ActionName.ASK_CLARIFICATION: frozenset(),
    ActionName.HUMAN_REVIEW: frozenset(),
    ActionName.IGNORE: frozenset(),
    ActionName.UNKNOWN: frozenset(),
}


SUPPLEMENTARY_ALLOWED_TOOLS: frozenset[ToolName] = frozenset({ToolName.PROFILE_UPDATE})


def allowed_tools_for_action(action: ActionName) -> frozenset[ToolName]:
    return ALLOWED_TOOLS_BY_ACTION.get(action, frozenset())


def tool_allowed_for_action(
    tool_name: ToolName,
    action: ActionName,
    *,
    allow_supplementary: bool = True,
) -> bool:
    if allow_supplementary and tool_name in SUPPLEMENTARY_ALLOWED_TOOLS:
        return True
    return tool_name in allowed_tools_for_action(action)


def validate_required_tools_for_action(
    action: ActionName,
    required_tools: list[ToolName],
    *,
    allow_supplementary: bool = True,
) -> list[str]:
    errors: list[str] = []
    for tool_name in required_tools:
        if not tool_allowed_for_action(tool_name, action, allow_supplementary=allow_supplementary):
            errors.append(f"tool {tool_name.value} is not allowed for action {action.value}")
    return errors
