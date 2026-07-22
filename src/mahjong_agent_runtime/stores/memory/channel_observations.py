"""In-memory channel observation archive used by focused tests."""

from __future__ import annotations

from typing import Any


class InMemoryChannelObservationsStoreMixin:
    """Mirror the durable observation API without mixing it into Agent turns."""

    __slots__ = ()

    def upsert_channel_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        channel = str(observation.get("channel") or "").strip()
        source_message_id = str(observation.get("source_message_id") or "").strip()
        if not channel:
            raise ValueError("channel observation requires channel")
        if not source_message_id:
            raise ValueError("channel observation requires source_message_id")
        record = dict(observation)
        record["channel"] = channel
        record["source_message_id"] = source_message_id
        record["payload"] = dict(record.get("payload") or {})
        with self._lock:
            self.channel_observations[f"{channel}:{source_message_id}"] = record
        return dict(record)

    def list_channel_observations(
        self,
        *,
        channel: str | None = None,
        room_id: str | None = None,
        room_topic_keyword: str | None = None,
        semantic_action: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._lock:
            records = [dict(item) for item in self.channel_observations.values()]
        if channel:
            records = [item for item in records if item.get("channel") == channel]
        if room_id:
            records = [item for item in records if item.get("room_id") == room_id]
        if room_topic_keyword:
            keyword = room_topic_keyword.casefold()
            records = [item for item in records if keyword in str(item.get("room_topic") or "").casefold()]
        if semantic_action:
            records = [item for item in records if item.get("semantic_action") == semantic_action]
        records.sort(key=lambda item: str(item.get("received_at") or ""), reverse=True)
        return records[: max(1, min(int(limit), 1_000))]


__all__ = ["InMemoryChannelObservationsStoreMixin"]
