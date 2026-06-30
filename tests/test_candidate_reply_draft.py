from __future__ import annotations

from mahjong_agent.candidate_reply_draft import CandidateReplyDraftService


def game_state(
    *,
    current_player_count: int = 1,
    missing_count: int = 3,
    outbox: list[dict] | None = None,
) -> dict:
    return {
        "id": "game_001",
        "parsed": {
            "start_time": "14:00",
            "level": "0.5",
            "duration_hours": 4,
            "current_player_count": current_player_count,
            "missing_count": missing_count,
            "rules": ["杭麻", "无烟"],
        },
        "outbox": outbox or [],
    }


def outbox_item(*, status: str = "已发送") -> dict:
    return {
        "id": "outbox_001",
        "customer_id": "ran",
        "customer_name": "冉姐",
        "status": status,
    }


def test_accepted_reply_reports_272_after_first_join() -> None:
    service = CandidateReplyDraftService()

    reply = service.accepted_reply(game_state(), outbox_item())

    assert reply == "好的，加你272了。"


def test_accepted_reply_reports_full_when_candidate_fills_last_seat() -> None:
    service = CandidateReplyDraftService()

    reply = service.accepted_reply(
        game_state(current_player_count=3, missing_count=1),
        outbox_item(),
    )

    assert reply == "好的，人齐了。"


def test_accepted_reply_accounts_for_existing_confirmed_candidates() -> None:
    service = CandidateReplyDraftService()

    reply = service.accepted_reply(
        game_state(
            current_player_count=1,
            missing_count=3,
            outbox=[{"status": "已确认"}, {"status": "已发送"}],
        ),
        outbox_item(),
    )

    assert reply == "好的，加你371了。"


def test_negotiation_reply_asks_organizer_before_confirming() -> None:
    service = CandidateReplyDraftService()

    assert service.negotiation_reply({"requested_duration_hours": 6}) == "可以，我问下这桌其他人能不能打6小时。"
    assert service.negotiation_reply({"requested_start_time_label": "四点半"}) == "可以，我问下这桌其他人四点半能不能对上。"


def test_question_reply_uses_known_game_details() -> None:
    service = CandidateReplyDraftService()

    reply = service.fallback_reply(
        {"intent": "question"},
        "几点啊",
        outbox_item(),
        game_state(),
    )

    assert reply == "冉姐，14:00，你能来吗？"


def test_guard_rejects_room_hold_wording() -> None:
    service = CandidateReplyDraftService()

    guarded = service.guard_reply(
        "冉姐，好，我给你留着。",
        fallback="好的，加你272了。",
        classification={"feedback_type": "accepted"},
    )

    assert guarded == "好的，加你272了。"


def test_guard_rejects_wrong_progress_label_for_acceptance() -> None:
    service = CandidateReplyDraftService()

    guarded = service.guard_reply(
        "好的，加你371了。",
        fallback="好的，加你272了。",
        classification={"feedback_type": "accepted"},
    )

    assert guarded == "好的，加你272了。"


def test_guard_rejects_confirmation_wording_for_negotiation() -> None:
    service = CandidateReplyDraftService()

    guarded = service.guard_reply(
        "好的，加你272了。",
        fallback="可以，我问下这桌其他人能不能打6小时。",
        classification={"feedback_type": "candidate_negotiation"},
    )

    assert guarded == "可以，我问下这桌其他人能不能打6小时。"
