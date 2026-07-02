from __future__ import annotations

from dataclasses import dataclass

from .models import GameStatusV2, GameV2, InviteDraftV2, InviteStatusV2


@dataclass(frozen=True, slots=True)
class StatePolicyV2:
    """Deterministic state boundary for Agent Runtime V2.

    The model may propose state-changing tools, but it cannot decide whether a
    database state transition is legal. This policy stays domain-state focused:
    it validates lifecycle transitions and does not parse mahjong language.
    """

    game_transitions: dict[GameStatusV2 | None, set[GameStatusV2]]
    invite_transitions: dict[InviteStatusV2, set[InviteStatusV2]]

    @classmethod
    def default(cls) -> "StatePolicyV2":
        return cls(
            game_transitions={
                None: {GameStatusV2.FORMING},
                GameStatusV2.FORMING: {GameStatusV2.INVITING, GameStatusV2.CANCELLED},
                GameStatusV2.INVITING: {GameStatusV2.READY, GameStatusV2.CANCELLED},
                GameStatusV2.READY: {GameStatusV2.FINISHED, GameStatusV2.CANCELLED},
                GameStatusV2.CANCELLED: set(),
                GameStatusV2.FINISHED: set(),
            },
            invite_transitions={
                InviteStatusV2.PENDING_APPROVAL: {
                    InviteStatusV2.SENT,
                    InviteStatusV2.CONFIRMED,
                    InviteStatusV2.DECLINED,
                    InviteStatusV2.NEGOTIATING,
                    InviteStatusV2.NO_REPLY,
                },
                InviteStatusV2.SENT: {
                    InviteStatusV2.CONFIRMED,
                    InviteStatusV2.DECLINED,
                    InviteStatusV2.NEGOTIATING,
                    InviteStatusV2.NO_REPLY,
                },
                InviteStatusV2.NEGOTIATING: {
                    InviteStatusV2.CONFIRMED,
                    InviteStatusV2.DECLINED,
                    InviteStatusV2.NO_REPLY,
                },
                InviteStatusV2.NO_REPLY: {
                    InviteStatusV2.CONFIRMED,
                    InviteStatusV2.DECLINED,
                    InviteStatusV2.NEGOTIATING,
                },
                InviteStatusV2.CONFIRMED: set(),
                InviteStatusV2.DECLINED: set(),
            },
        )

    @property
    def active_game_statuses(self) -> set[GameStatusV2]:
        return {GameStatusV2.FORMING, GameStatusV2.INVITING, GameStatusV2.READY}

    @property
    def occupied_invite_statuses(self) -> set[InviteStatusV2]:
        return {
            InviteStatusV2.PENDING_APPROVAL,
            InviteStatusV2.SENT,
            InviteStatusV2.CONFIRMED,
            InviteStatusV2.NEGOTIATING,
        }

    def ensure_game_transition(self, from_status: GameStatusV2 | None, to_status: GameStatusV2) -> None:
        allowed = self.game_transitions.get(from_status, set())
        if to_status not in allowed:
            source = from_status.value if from_status else "null"
            raise ValueError(f"illegal game status transition: {source} -> {to_status.value}")

    def ensure_can_create_invite_drafts(self, game: GameV2) -> None:
        if game.status not in {GameStatusV2.FORMING, GameStatusV2.INVITING}:
            raise ValueError(f"game status {game.status.value} cannot create invite drafts")

    def ensure_candidate_reply_allowed(self, game: GameV2, drafts: list[InviteDraftV2]) -> None:
        if game.status != GameStatusV2.INVITING:
            raise ValueError(f"game status {game.status.value} cannot record candidate reply")
        if not drafts:
            raise ValueError("candidate reply requires an existing invite draft")

    def ensure_invite_transition(self, from_status: InviteStatusV2, to_status: InviteStatusV2) -> None:
        if from_status == to_status:
            return
        allowed = self.invite_transitions.get(from_status, set())
        if to_status not in allowed:
            raise ValueError(f"illegal invite status transition: {from_status.value} -> {to_status.value}")
