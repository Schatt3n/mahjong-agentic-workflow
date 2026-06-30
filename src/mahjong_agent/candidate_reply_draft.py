from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


ConfirmedCountProvider = Callable[[dict[str, Any] | None], int]


@dataclass(slots=True)
class CandidateReplyDraftService:
    """Draft and guard the boss reply to an invited candidate.

    This service does not call LLMs, update state, or send messages. It only
    creates a safe fallback reply from backend-validated candidate feedback and
    guards an optional model-proposed reply against state/wording conflicts.
    """

    confirmed_count_provider: ConfirmedCountProvider | None = None

    def fallback_reply(
        self,
        classification: dict[str, Any],
        text: str,
        outbox_item: dict[str, Any],
        game: dict[str, Any] | None,
    ) -> str:
        name = str(outbox_item.get("customer_name") or "你")
        intent = str(classification.get("intent") or "")
        if intent == "accepted":
            return self.accepted_reply(game, outbox_item)
        if intent == "candidate_negotiation":
            return self.negotiation_reply(classification)
        if intent == "arrived":
            return f"{name}，好，到了直接进来。"
        if intent == "declined":
            return f"{name}，好，下次有合适的再问你。"
        if intent == "ask_later":
            return f"{name}，好，你确定了跟我说，我这边先看别人。"
        if intent == "do_not_disturb":
            return f"{name}，收到，后面不打扰你。"
        detail = self.question_detail(text, game)
        return f"{name}，{detail}"

    def negotiation_reply(self, classification: dict[str, Any]) -> str:
        requested_start = classification.get("requested_start_time_label")
        if requested_start:
            return f"可以，我问下这桌其他人{requested_start}能不能对上。"
        requested_duration = classification.get("requested_duration_hours")
        if requested_duration:
            duration_text = _duration_text(requested_duration)
            return f"可以，我问下这桌其他人能不能打{duration_text}。"
        return "可以，我先问下这桌其他人，看大家能不能对上。"

    def question_detail(self, text: str, game: dict[str, Any] | None) -> str:
        parsed = game.get("parsed") if isinstance(game, dict) and isinstance(game.get("parsed"), dict) else {}
        normalized = re.sub(r"\s+", "", str(text or "").lower())
        start_time = str(parsed.get("start_time") or "").strip()
        level = str(parsed.get("level") or "").strip()
        duration = parsed.get("duration_hours")
        rules = [str(item) for item in parsed.get("rules") or []]
        smoke = "无烟" if "无烟" in rules else "有烟" if "可吸烟" in rules else ""
        parts: list[str] = []
        if re.search(r"几点|时间", normalized) and start_time:
            parts.append(start_time)
        if re.search(r"多大|多少钱|档", normalized) and level:
            parts.append(f"{level}档")
        if re.search(r"有烟|无烟|抽烟|烟", normalized) and smoke:
            parts.append(smoke)
        if re.search(r"多久|几个小时|打几", normalized) and duration:
            parts.append(f"约{duration}小时")
        if re.search(r"几个人|几缺|几位", normalized):
            return "差不多了，你能来我就给你确认。"
        if re.search(r"哪里|地址|几楼", normalized):
            return "在店里老地方，你能来我给你确认。"
        if not parts:
            parts = [item for item in [start_time, f"{level}档" if level else "", smoke] if item]
        if parts:
            return "，".join(parts[:3]) + "，你能来吗？"
        return "你能来吗？"

    def accepted_reply(self, game: dict[str, Any] | None, outbox_item: dict[str, Any]) -> str:
        label = self.progress_label_after_candidate(game, outbox_item, include_candidate=True)
        if label == "人齐":
            return "好的，人齐了。"
        if label:
            return f"好的，加你{label}了。"
        return "好的，加你了。"

    def progress_label_after_candidate(
        self,
        game: dict[str, Any] | None,
        outbox_item: dict[str, Any],
        *,
        include_candidate: bool,
    ) -> str:
        if not isinstance(game, dict):
            return ""
        parsed = game.get("parsed") if isinstance(game.get("parsed"), dict) else {}
        current_count = parsed.get("current_player_count")
        missing_count = parsed.get("missing_count")
        if not isinstance(current_count, int) or not isinstance(missing_count, int):
            return ""
        confirmed = self._confirmed_count(game)
        already_confirmed = str(outbox_item.get("status") or "") in {"已确认", "已到店"}
        if include_candidate and not already_confirmed:
            confirmed += 1
        after_current = min(4, current_count + confirmed)
        after_missing = max(0, missing_count - confirmed)
        if after_missing <= 0 or after_current >= 4:
            return "人齐"
        mapping = {
            (1, 3): "173",
            (2, 2): "272",
            (3, 1): "371",
        }
        return mapping.get((after_current, after_missing), f"{after_current}缺{after_missing}")

    def guard_reply(
        self,
        reply_text: str,
        *,
        fallback: str,
        classification: dict[str, Any],
    ) -> str:
        text = re.sub(r"\s+", " ", str(reply_text or "")).strip()
        if "留" in text:
            return fallback
        feedback_type = str(classification.get("feedback_type") or "")
        if feedback_type == "candidate_negotiation":
            if re.search(r"加你|人齐|已确认|确认了|371|272|173", text):
                return fallback
        if feedback_type not in {"accepted", "arrived", "candidate_negotiation"}:
            if re.search(r"加你|人齐|已确认|确认了|371|272|173", text):
                return fallback
        if feedback_type in {"accepted", "arrived"}:
            for label in ["人齐", "371", "272", "173"]:
                if label in fallback and label not in text:
                    return fallback
            if not re.search(r"加你|人齐|已确认|确认", text):
                return fallback
        return text or fallback

    def _confirmed_count(self, game: dict[str, Any] | None) -> int:
        if self.confirmed_count_provider:
            return int(self.confirmed_count_provider(game) or 0)
        if not isinstance(game, dict):
            return 0
        outbox = game.get("outbox")
        if not isinstance(outbox, list):
            return 0
        return sum(
            1
            for item in outbox
            if isinstance(item, dict) and str(item.get("status") or "") in {"已确认", "已到店"}
        )


def _duration_text(value: Any) -> str:
    number = float(value)
    if number.is_integer():
        return f"{int(number)}小时"
    return f"{number:g}小时"
