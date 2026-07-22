#!/usr/bin/env python3
"""Validate anonymized real-group-chat evaluation assets before commit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_PATHS = (
    ROOT / "eval" / "golden" / "real_group_chat_20260722.jsonl",
    ROOT / "eval" / "adversarial" / "real_group_chat_20260722.jsonl",
)
SOURCE_REF_PATTERN = re.compile(r"^sha256:[0-9a-f]{16}$")
RAW_MESSAGE_ID_PATTERN = re.compile(r"(?<!\d)\d{17,20}(?!\d)")
ALLOWED_ROLES = {"operator", "customer", "system"}

# Hashes let the validator reject exact observed room/member identities without
# committing those identities to the repository as a plaintext denylist.
FORBIDDEN_IDENTITY_HASHES = {
    "9aeba2369a09040f889a1de892554dc3e8dedab11852409d3e0514bbf89e517c",
    "d24fb248b6f0ed821ea7d90f5b3805ef5d8198a950cfb0ac2e8c81cd6d59a519",
    "363c3a5031150d0df661dfda2948d6d61ae47765fdee60b7b79bcec97bf6c567",
    "ef24e3ff42a62ff0aac6cf4e9b359e39f8578941253c0c4c607eadb607a7062c",
    "d351d6316ec75699207f756dc12d116a16c333867dfb747949cb535b217c623f",
    "6a1f2baa90441f4231b816615bd732305bef6b6772e29a515c85d5790cd5b284",
    "ff1a5f530ed8d499cad45aaae98d895f419bd4822de615bbb7080f178a75ec64",
}
FORBIDDEN_RAW_KEYS = {
    "room_id",
    "sender_id",
    "sender_name",
    "source_message_id",
    "payload",
    "avatar",
    "signature",
    "weixin",
    "semantic_action",
    "semantic_category",
    "business_message_detected",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read one JSON object per non-empty line and include line diagnostics."""

    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            value = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: record must be a JSON object")
        records.append(value)
    return records


def _iter_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _iter_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_keys(child)


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_strings(child)


def _validate_record(record: dict[str, Any], *, path: Path, index: int) -> list[str]:
    label = f"{path.name} record {index} ({record.get('id', 'missing-id')})"
    errors: list[str] = []
    required = {"schema_version", "kind", "id", "quality_tier", "review_status", "source", "case_type", "messages"}
    missing = sorted(required - set(record))
    if missing:
        errors.append(f"{label}: missing required fields {missing}")

    source = record.get("source")
    if not isinstance(source, dict):
        errors.append(f"{label}: source must be an object")
    else:
        if source.get("anonymized") is not True:
            errors.append(f"{label}: source.anonymized must be true")
        if source.get("capture_date") != "2026-07-22":
            errors.append(f"{label}: unexpected capture_date")
        room_alias = source.get("room_alias")
        if not isinstance(room_alias, str) or not room_alias.startswith("room_"):
            errors.append(f"{label}: room_alias must use an anonymous room_* value")
        refs = source.get("source_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{label}: source_refs must be a non-empty array")
        elif any(not isinstance(ref, str) or SOURCE_REF_PATTERN.fullmatch(ref) is None for ref in refs):
            errors.append(f"{label}: every source_ref must be a truncated sha256 reference")

    messages = record.get("messages")
    if not isinstance(messages, list) or not messages:
        errors.append(f"{label}: messages must be a non-empty array")
    else:
        offsets: list[int] = []
        for message_index, message in enumerate(messages, start=1):
            if not isinstance(message, dict):
                errors.append(f"{label}: message {message_index} must be an object")
                continue
            if message.get("role") not in ALLOWED_ROLES:
                errors.append(f"{label}: message {message_index} has invalid role")
            offset = message.get("offset_seconds")
            if not isinstance(offset, int) or offset < 0:
                errors.append(f"{label}: message {message_index} has invalid offset_seconds")
            else:
                offsets.append(offset)
            if not isinstance(message.get("text"), str):
                errors.append(f"{label}: message {message_index} text must be a string")
        if offsets != sorted(offsets):
            errors.append(f"{label}: message offsets must be monotonic")

    tier = record.get("quality_tier")
    if tier == "gold":
        if record.get("review_status") != "approved":
            errors.append(f"{label}: gold record must be approved")
        if not isinstance(record.get("expected"), dict):
            errors.append(f"{label}: gold record requires expected contract")
    elif tier == "adversarial":
        if record.get("review_status") != "pending_domain_review":
            errors.append(f"{label}: adversarial record must remain pending_domain_review")
        if not isinstance(record.get("candidate_expectation"), dict):
            errors.append(f"{label}: adversarial record requires candidate_expectation")
        if not isinstance(record.get("open_questions"), list) or not record.get("open_questions"):
            errors.append(f"{label}: adversarial record requires open_questions")
    else:
        errors.append(f"{label}: unsupported quality_tier {tier!r}")

    raw_json = json.dumps(record, ensure_ascii=False, sort_keys=True)
    leaked_identity_count = sum(
        hashlib.sha256(value.encode("utf-8")).hexdigest() in FORBIDDEN_IDENTITY_HASHES
        for value in _iter_strings(record)
    )
    if leaked_identity_count:
        errors.append(f"{label}: contains {leaked_identity_count} forbidden plaintext identities")
    leaked_keys = sorted(set(_iter_keys(record)) & FORBIDDEN_RAW_KEYS)
    if leaked_keys:
        errors.append(f"{label}: contains raw observation/model-label keys {leaked_keys}")
    if RAW_MESSAGE_ID_PATTERN.search(raw_json):
        errors.append(f"{label}: contains a raw long numeric identifier")
    return errors


def validate_datasets(paths: Iterable[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate every dataset and enforce globally unique case identifiers."""

    records: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    for path in paths:
        if not path.exists():
            errors.append(f"missing dataset: {path}")
            continue
        try:
            current = read_jsonl(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        for index, record in enumerate(current, start=1):
            record_id = record.get("id")
            if not isinstance(record_id, str) or not record_id:
                errors.append(f"{path.name} record {index}: id must be a non-empty string")
            elif record_id in seen_ids:
                errors.append(f"{path.name} record {index}: duplicate id {record_id}")
            else:
                seen_ids.add(record_id)
            errors.extend(_validate_record(record, path=path, index=index))
        records.extend(current)
    return records, errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate anonymized real group chat datasets.")
    parser.add_argument("paths", nargs="*", type=Path, help="optional JSONL paths; defaults to current real datasets")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = tuple(args.paths) or DEFAULT_DATASET_PATHS
    records, errors = validate_datasets(paths)
    if errors:
        print("Real group chat dataset validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    gold_count = sum(record.get("quality_tier") == "gold" for record in records)
    adversarial_count = sum(record.get("quality_tier") == "adversarial" for record in records)
    print(f"Validated {len(records)} real group chat cases: gold={gold_count}, adversarial={adversarial_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
