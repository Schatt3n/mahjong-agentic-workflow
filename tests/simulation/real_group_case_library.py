"""Curated real-group examples used only to shape synthetic test messages.

The simulation must never read raw production chat logs directly.  This
library accepts only anonymized, reviewed golden records and exposes a small
prompt-safe projection that contains neither source hashes nor external user
identifiers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


CUSTOMER_ROLE = "customer"
OPERATOR_ROLE = "operator"


@dataclass(slots=True, frozen=True)
class RealGroupCaseExample:
    """A privacy-safe projection of one approved real group-chat case."""

    case_id: str
    case_type: str
    tags: tuple[str, ...]
    turns: tuple[dict[str, str], ...]
    semantic_shape: dict[str, Any]

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_type": self.case_type,
            "turns": [dict(item) for item in self.turns],
            "semantic_shape": dict(self.semantic_shape),
        }


class RealGroupCaseLibrary:
    """Load and deterministically select approved real conversation examples."""

    def __init__(self, examples: Iterable[RealGroupCaseExample] = ()) -> None:
        self.examples = tuple(examples)

    @classmethod
    def from_jsonl(cls, path: Path) -> "RealGroupCaseLibrary":
        examples: list[RealGroupCaseExample] = []
        if not path.exists():
            return cls()
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            example = _safe_example(record)
            if example is not None:
                examples.append(example)
        return cls(examples)

    def select_for_generation(
        self,
        *,
        channel: str,
        fallback_text: str,
        dialog_phase: str,
        is_follow_up: bool,
        seed_material: str,
        speaker_role: str = CUSTOMER_ROLE,
        limit: int = 3,
    ) -> tuple[RealGroupCaseExample, ...]:
        """Return stable, semantically related examples for one generated turn.

        Chitchat intentionally receives no business examples.  This prevents a
        style reference from turning an unrelated social message into a new
        Mahjong request.
        """

        if channel != "group" or dialog_phase == "chitchat" or limit <= 0:
            return ()
        candidates = [
            example
            for example in self.examples
            if any(turn.get("role") == speaker_role for turn in example.turns)
        ]
        ranked = sorted(
            candidates,
            key=lambda item: (
                -_semantic_score(item, fallback_text=fallback_text, is_follow_up=is_follow_up),
                _stable_tiebreaker(seed_material, item.case_id),
            ),
        )
        return tuple(ranked[:limit])


def _safe_example(record: Any) -> RealGroupCaseExample | None:
    if not isinstance(record, dict):
        return None
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    if (
        record.get("quality_tier") != "gold"
        or record.get("review_status") != "approved"
        or source.get("anonymized") is not True
    ):
        return None
    case_id = str(record.get("id") or "").strip()
    case_type = str(record.get("case_type") or "").strip()
    messages = record.get("messages")
    if not case_id or not case_type or not isinstance(messages, list):
        return None
    turns: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip()
        text = str(message.get("text") or "").strip()
        if role not in {CUSTOMER_ROLE, OPERATOR_ROLE} or not text:
            continue
        turn = {
            "role": role,
            "content_type": str(message.get("content_type") or "text"),
            "text": text,
        }
        quoted_text = str(message.get("quoted_text") or "").strip()
        if quoted_text:
            turn["quoted_text"] = quoted_text
        turns.append(turn)
    if not turns:
        return None
    expected = record.get("expected") if isinstance(record.get("expected"), dict) else {}
    semantic_shape = {
        key: expected[key]
        for key in (
            "intent",
            "search_requirement",
            "current_players",
            "missing_players",
            "urgency",
            "same_session",
            "preferred_channel_action",
        )
        if key in expected
    }
    return RealGroupCaseExample(
        case_id=case_id,
        case_type=case_type,
        tags=tuple(str(tag) for tag in record.get("tags") or []),
        turns=tuple(turns),
        semantic_shape=semantic_shape,
    )


def _semantic_score(
    example: RealGroupCaseExample,
    *,
    fallback_text: str,
    is_follow_up: bool,
) -> int:
    normalized = str(fallback_text or "")
    score = 0
    if is_follow_up and example.case_type == "fragmented_input":
        score += 12
    if any(cue in normalized for cue in ("吗", "嘛", "有没", "还有", "几", "?", "？")):
        if example.case_type == "member_query":
            score += 10
    if any(code in normalized for code in ("173", "272", "371", "三缺一", "二缺二")):
        if "participant_code" in example.tags or example.case_type == "fragmented_input":
            score += 8
    if any(cue in normalized for cue in ("也可以", "都行", "补充", "再说")):
        if "constraint_relaxation" in example.tags:
            score += 6
    if example.case_type in {"member_query", "fragmented_input"}:
        score += 2
    return score


def _stable_tiebreaker(seed_material: str, case_id: str) -> str:
    return hashlib.sha256(f"{seed_material}:{case_id}".encode("utf-8")).hexdigest()
