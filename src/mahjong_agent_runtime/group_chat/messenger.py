"""Channel transport contract used by the group-chat domain."""

from __future__ import annotations

from typing import Any, Protocol


class GroupMessenger(Protocol):
    def send_group_message(self, room_id: str, text: str, *, metadata: dict[str, Any] | None = None) -> str: ...

    def send_private_message(
        self,
        external_user_id: str,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str: ...


__all__ = ["GroupMessenger"]
