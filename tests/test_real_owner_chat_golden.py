from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "eval" / "golden" / "real_owner_chat_golden.jsonl"


def read_records() -> list[dict]:
    return [
        json.loads(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_real_owner_chat_golden_transcript_is_structured() -> None:
    records = read_records()

    assert len(records) == 1
    record = records[0]
    assert record["kind"] == "real_owner_chat_golden"
    assert record["id"] == "owner_chat_ai_chitchat_resume_20260704_001"

    messages = record["messages"]
    assert len(messages) == 67
    assert {message["role"] for message in messages} == {"customer", "boss"}
    assert all(message["text"] for message in messages)
    assert all("source_image" in message for message in messages)


def test_real_owner_chat_golden_covers_context_resume_cases() -> None:
    record = read_records()[0]
    eval_cases = {item["id"]: item for item in record["eval_cases"]}
    facts = {item["id"]: item for item in record["business_facts"]}

    assert "resume_game_status_after_casual_chat" in eval_cases
    assert "later_people_count_query_should_search_or_answer_current_status" in eval_cases
    assert "reject_smoking_game_updates_preference" in eval_cases
    assert "casual_chat_interruption" in facts
    assert "resume_status_query" in facts

    resume_case = eval_cases["resume_game_status_after_casual_chat"]
    assert resume_case["expected"]["must_use_existing_context"] is True
    assert resume_case["expected"]["should_not_treat_as_new_game"] is True
    assert "我是AI" in resume_case["expected"]["forbidden_reply_contains"]
