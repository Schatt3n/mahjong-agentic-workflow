from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_real_group_chat_dataset.py"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_real_group_chat_dataset", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_real_group_chat_datasets_are_anonymized_and_contract_valid() -> None:
    module = load_validator_module()

    records, errors = module.validate_datasets(module.DEFAULT_DATASET_PATHS)

    assert errors == []
    assert sum(record["quality_tier"] == "gold" for record in records) >= 12
    assert sum(record["quality_tier"] == "adversarial" for record in records) >= 4


def test_real_group_chat_gold_covers_key_production_behaviors() -> None:
    module = load_validator_module()
    records, errors = module.validate_datasets(module.DEFAULT_DATASET_PATHS)
    assert errors == []

    gold = [record for record in records if record["quality_tier"] == "gold"]
    case_types = {record["case_type"] for record in gold}
    assert {
        "owner_board_parse",
        "owner_board_snapshot",
        "owner_board_increment",
        "board_state_diff",
        "member_query",
        "fragmented_input",
        "quoted_state_update",
        "quick_filter",
        "message_revoke",
    } <= case_types

    fragmented = next(record for record in gold if record["id"] == "real_group_fragmented_constraint_relaxation_001")
    assert fragmented["expected"]["search_requirement"]["accepted_stakes"] == ["1", "0.5"]
    urgent = next(record for record in gold if record["id"] == "real_group_fragmented_urgent_371_001")
    assert urgent["expected"]["current_players"] == 3
    assert urgent["expected"]["missing_players"] == 1


def test_validator_rejects_raw_identifiers_and_current_model_labels(tmp_path) -> None:
    module = load_validator_module()
    bad_path = tmp_path / "bad.jsonl"
    bad_path.write_text(
        '{"schema_version":1,"kind":"real_group_chat_golden","id":"bad","quality_tier":"gold",'
        '"review_status":"approved","case_type":"query","source":{"channel":"wechat",'
        '"capture_date":"2026-07-22","room_alias":"room_alpha","source_refs":["sha256:1234567890abcdef"],'
        '"anonymized":true},"messages":[{"offset_seconds":0,"role":"customer","text":"x",'
        '"sender_id":"123456789012345678"}],"expected":{},"semantic_action":"process_business"}\n',
        encoding="utf-8",
    )

    _, errors = module.validate_datasets((bad_path,))
    text = "\n".join(errors)

    assert "raw observation/model-label keys" in text
    assert "raw long numeric identifier" in text


def test_adversarial_cases_cannot_be_promoted_without_resolving_open_questions() -> None:
    module = load_validator_module()
    records, errors = module.validate_datasets(module.DEFAULT_DATASET_PATHS)
    assert errors == []

    adversarial = [record for record in records if record["quality_tier"] == "adversarial"]
    assert all(record["review_status"] == "pending_domain_review" for record in adversarial)
    assert all(record["open_questions"] for record in adversarial)
