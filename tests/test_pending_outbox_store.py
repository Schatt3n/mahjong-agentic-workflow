from __future__ import annotations

from mahjong_agent.tools import InMemoryPendingOutboxStore, PendingOutboxTool, SQLitePendingOutboxStore
from mahjong_agent.workflow_models import GameRequirement, SlotSource, SlotValue


def confirmed_slot(name: str, value) -> SlotValue:
    return SlotValue(
        name=name,
        value=value,
        source=SlotSource.EXPLICIT,
        confidence=0.9,
        confirmed=True,
        needs_confirmation=False,
    )


def requirement() -> GameRequirement:
    game = GameRequirement()
    game.set_slot(confirmed_slot("stake", "0.5"))
    game.set_slot(confirmed_slot("start_time_mode", "people_ready"))
    game.set_slot(confirmed_slot("smoke", "no_smoke"))
    game.set_slot(confirmed_slot("duration_hours", 4))
    return game


def candidates() -> list[dict]:
    return [
        {
            "customer_id": "ran",
            "display_name": "冉姐",
            "score": 98,
            "reasons": ["常打0.5"],
            "warnings": [],
        },
        {
            "customer_id": "liu",
            "display_name": "刘姐",
            "score": 92,
            "reasons": ["无烟匹配"],
            "warnings": ["最近邀约过"],
        },
    ]


def test_pending_outbox_tool_can_store_drafts_in_memory() -> None:
    store = InMemoryPendingOutboxStore()
    result = PendingOutboxTool(store=store).create_pending_invites(
        requirement(),
        candidates(),
        conversation_id="boss_trial",
        trace_id="trace_outbox",
    )

    assert result["result_count"] == 2
    assert result["stored_count"] == 2
    pending = store.list_pending(conversation_id="boss_trial")
    assert len(pending) == 2
    assert pending[0]["status"] == "pending_approval"
    assert pending[0]["metadata"]["candidate_reasons"] == ["常打0.5"]


def test_sqlite_pending_outbox_store_persists_pending_drafts(tmp_path) -> None:
    path = tmp_path / "outbox" / "pending_outbox.sqlite3"
    store = SQLitePendingOutboxStore(path)
    result = PendingOutboxTool(store=store).create_pending_invites(
        requirement(),
        candidates(),
        conversation_id="boss_trial",
        trace_id="trace_outbox_sqlite",
    )

    reloaded = SQLitePendingOutboxStore(path)
    pending = reloaded.list_pending(conversation_id="boss_trial")

    assert result["stored_count"] == 2
    assert len(pending) == 2
    assert pending[0]["id"] == result["drafts"][0]["id"]
    assert pending[0]["target_customer_id"] == "ran"
    assert pending[0]["message_text"].endswith("打吗？")
    assert reloaded.get(result["drafts"][1]["id"])["metadata"]["candidate_warnings"] == ["最近邀约过"]
