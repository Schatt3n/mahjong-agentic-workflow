from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TIMELINE_PATH = ROOT / "eval" / "golden" / "real_owner_chat_timeline_20260627_20260719_owner_b.json"

EXPECTED_SOURCE_IMAGES = {
    "codex-clipboard-87bd449d-d0ae-4bc8-b5f8-9d8b313a1dee.png",
    "codex-clipboard-907aefbe-6887-4104-b781-394d4ca42af9.png",
    "codex-clipboard-f062b1d5-7473-4f42-91f4-4ca482cd85fc.png",
    "codex-clipboard-aef5f9f4-d760-4814-b14c-393b74b756b3.png",
    "codex-clipboard-6337506b-c493-439d-8556-efd9647da32f.png",
    "codex-clipboard-d92f432b-dab7-4b35-987a-5c56a099cbce.png",
    "codex-clipboard-8c66a79b-1b85-467a-b48b-95251012c26e.png",
    "codex-clipboard-fcc26711-6e3d-41be-81d4-091486ebe49d.png",
    "codex-clipboard-126b0eea-2b24-44c0-be45-074a49a68560.png",
    "codex-clipboard-fcb81021-cc4e-4813-b63e-72b68f776033.png",
    "codex-clipboard-712624b8-c601-4a83-a69e-1a99e4095ce1.png",
}


def _load_timeline() -> dict:
    return json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))


def test_owner_b_timeline_preserves_source_order_counts_and_anonymization() -> None:
    record = _load_timeline()
    messages = record["messages"]
    serialized = json.dumps(record, ensure_ascii=False)

    assert record["id"] == "owner_b_chat_multi_episode_timeline_20260627_20260719_001"
    assert len(messages) == 80
    assert [item["turn"] for item in messages] == list(range(1, 81))
    assert sum(item["role"] == "customer" for item in messages) == 46
    assert sum(item["role"] == "boss" for item in messages) == 34
    assert all(item["text"].strip() for item in messages)
    assert all("表情包" not in item["text"] for item in messages)
    assert record["participants"]["represented_people"] == ["候选人甲", "客户的对象", "客户的朋友"]
    assert "wxid_" not in serialized
    assert "候选人甲" in serialized
    assert set(record["source"]["source_image_files"]) == EXPECTED_SOURCE_IMAGES


def test_owner_b_timeline_records_recalled_message_without_inventing_content() -> None:
    record = _load_timeline()
    source_event = record["source_events"][0]
    recalled_case = next(item for item in record["eval_cases"] if item["id"] == "recalled_message_is_not_context")

    assert source_event["id"] == "recalled_message_1"
    assert source_event["event_type"] == "message_recalled"
    assert source_event["content_available"] is False
    assert recalled_case["source_event_refs"] == ["recalled_message_1"]
    assert recalled_case["expected"]["must_not_reconstruct_content"] is True


def test_owner_b_timeline_episode_ranges_partition_messages() -> None:
    record = _load_timeline()
    messages = {item["turn"]: item for item in record["messages"]}
    covered_turns: list[int] = []

    for episode in record["episodes"]:
        episode_turns = list(range(episode["start_turn"], episode["end_turn"] + 1))
        covered_turns.extend(episode_turns)
        observed_times = [datetime.fromisoformat(messages[turn]["observed_at"]) for turn in episode_turns]
        assert observed_times == sorted(observed_times)

    assert covered_turns == list(range(1, 81))
    assert [item["business_exchange_rounds"] for item in record["episodes"]] == [6, 4, 3, 5, 3, 4, 3]
    assert [item["outcome"] for item in record["episodes"]] == [
        "pending_missing_one_after_role_correction",
        "cancelled",
        "accepted_pending_owner_confirmation",
        "pending_reconfirmation",
        "completed",
        "pending_unknown",
        "resolved_target_already_full",
    ]


def test_owner_b_timeline_metrics_do_not_overclaim_success() -> None:
    metrics = _load_timeline()["timeline_metrics"]

    assert metrics["message_count"] == 80
    assert metrics["customer_message_count"] == 46
    assert metrics["boss_message_count"] == 34
    assert metrics["episode_count"] == 7
    assert metrics["terminal_episode_count"] == 3
    assert metrics["successful_episode_count"] == 1
    assert metrics["pending_or_unknown_episode_count"] == 4
    assert any("不能据此宣称平均成局轮数" in item for item in metrics["interpretation"])


def test_owner_b_timeline_replay_scenarios_capture_business_boundaries() -> None:
    scenarios = {item["id"]: item["expected"] for item in _load_timeline()["replay_scenarios"]}

    intermediary = scenarios["replay_intermediary_not_participant"]
    assert intermediary["contact_is_participant"] is False
    assert intermediary["final_seat_format"] == "371"
    assert intermediary["must_correct_earlier_contact_seat_assumption"] is True

    cancelled = scenarios["replay_gender_preference_then_cancel"]
    assert cancelled["final_task_status"] == "cancelled"
    assert cancelled["must_stop_candidate_search"] is True

    reactivated = scenarios["replay_cancel_then_reactivate"]
    assert reactivated["reactivation_requires_game_recheck"] is True
    assert reactivated["must_not_silently_restore_old_claim"] is True

    represented_friend = scenarios["replay_friend_is_separate_participant"]
    assert represented_friend["contact_role"] == "representative"
    assert represented_friend["participant_role"] == "friend"
    assert represented_friend["must_not_add_contact_as_seat"] is True

    stake_mismatch = scenarios["replay_stake_mismatch_does_not_fill_game"]
    assert stake_mismatch["must_not_count_unmatched_candidates"] is True
    assert stake_mismatch["must_not_change_game_stake_without_confirmation"] is True

    full_game = scenarios["replay_game_fills_before_claim"]
    assert full_game["join_result"] == "seat_unavailable"
    assert full_game["must_not_create_new_game_without_confirmation"] is True


def test_owner_b_timeline_eval_cases_reference_real_turns_and_events() -> None:
    record = _load_timeline()
    turn_ids = {item["turn"] for item in record["messages"]}
    event_ids = {item["id"] for item in record["source_events"]}

    for case in record["eval_cases"]:
        assert case["id"]
        assert case["description"]
        assert set(case.get("context_turns", [])).issubset(turn_ids)
        assert case["input_turn"] in turn_ids
        assert set(case.get("source_event_refs", [])).issubset(event_ids)
        assert case["expected"]
