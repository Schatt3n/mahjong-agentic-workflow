"""Deterministic parsing for stable Mahjong room-board syntax."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from ..domains import START_KIND_ASAP_WHEN_FULL
from ..models import DEFAULT_TZ, now


SEAT_CODE_PATTERN = re.compile(r"(?<!\d)(173|272|371)(?!\d)")
CLAIM_PATTERN = re.compile(
    r"^\s*(?P<item_no>\d{1,2})\s*(?:号|个|这个)?\s*(?:来|我来|可以|我可以|这个我来|打|我打|加我|算我一个)\s*[!！。.]?\s*$"
)
FIXED_TIME_PATTERN = re.compile(r"(?<!\d)(?P<hour>[01]?\d|2[0-3])\s*[:.：]\s*(?P<minute>[0-5]\d)(?!\d)")
CHINESE_TIME_PATTERN = re.compile(r"(?<!\d)(?P<hour>[0-2]?\d)\s*[点时](?P<half>半)?(?P<minute>[0-5]?\d)?")
STAKE_CAP_PATTERN = re.compile(r"(?<!\d)(?P<base>\d+(?:\.\d+)?)\s*[-—~至]\s*(?P<cap>\d+(?:\.\d+)?)(?!\d)")
DECIMAL_STAKE_PATTERN = re.compile(r"(?<!\d)(?P<stake>0\.5|[1-9]\d*(?:\.\d+)?)\s*(?:块|元|档)?(?!\d)")
DURATION_PATTERN = re.compile(r"(?<!\d)(?P<hours>\d+(?:\.5)?)\s*(?:h|小时)", re.IGNORECASE)


def normalize_text(text: str) -> str:
    return (
        str(text or "")
        .replace("，", " ")
        .replace(",", " ")
        .replace("；", " ")
        .replace(";", " ")
        .replace("０", "0")
        .replace("１", "1")
        .replace("２", "2")
        .replace("３", "3")
        .replace("４", "4")
        .replace("５", "5")
        .replace("６", "6")
        .replace("７", "7")
        .replace("８", "8")
        .replace("９", "9")
        .strip()
    )


def parse_claim_item_no(text: str) -> int | None:
    match = CLAIM_PATTERN.fullmatch(normalize_text(text))
    return int(match.group("item_no")) if match else None


def parse_game_post(text: str, *, anchor: datetime | None = None) -> dict[str, Any] | None:
    """Parse only complete board syntax; ambiguous natural language must fall through."""

    original = str(text or "").strip()
    normalized = normalize_text(original).lower()
    seat_match = SEAT_CODE_PATTERN.search(normalized)
    if seat_match is None:
        return None
    seat_code = seat_match.group(1)
    known_player_count = int(seat_code[0])
    needed_seats = int(seat_code[2])
    if known_player_count + needed_seats != 4:
        return None

    start_fields, time_span = _parse_start_time(normalized, anchor=anchor)
    stake_fields, stake_span = _parse_stake(normalized, excluded_span=time_span)
    smoke_preference = _parse_smoke(normalized)
    requested_game, variant = _parse_game_type(normalized)
    has_domain_signal = bool(
        start_fields
        or stake_fields
        or smoke_preference
        or requested_game
        or any(token in normalized for token in ("麻将", "局", "人齐开"))
    )
    if not has_domain_signal:
        return None

    parsed: dict[str, Any] = {
        **start_fields,
        **stake_fields,
        "known_player_count": known_player_count,
        "current_player_count": known_player_count,
        "needed_seats": needed_seats,
        "seat_format": seat_code,
        "source_text": original,
    }
    if smoke_preference:
        parsed["smoke_preference"] = smoke_preference
    if requested_game:
        parsed["requested_game"] = requested_game
    if variant:
        parsed["game_variant"] = variant
    duration_match = DURATION_PATTERN.search(normalized)
    if duration_match:
        parsed["duration_hours"] = float(duration_match.group("hours"))
    return parsed


def parse_explicit_need(text: str, *, anchor: datetime | None = None) -> dict[str, Any]:
    """Extract unambiguous fields for private handoff without deciding user intent."""

    normalized = normalize_text(text).lower()
    start_fields, time_span = _parse_start_time(normalized, anchor=anchor)
    stake_fields, _ = _parse_stake(normalized, excluded_span=time_span)
    payload: dict[str, Any] = {**start_fields, **stake_fields}
    smoke = _parse_smoke(normalized)
    game, variant = _parse_game_type(normalized)
    if smoke:
        payload["smoke_preference"] = smoke
    if game:
        payload["requested_game"] = game
    if variant:
        payload["game_variant"] = variant
    seat_match = SEAT_CODE_PATTERN.search(normalized)
    if seat_match:
        code = seat_match.group(1)
        payload.update(
            {
                "seat_format": code,
                "known_player_count": int(code[0]),
                "needed_seats": int(code[2]),
            }
        )
    duration_match = DURATION_PATTERN.search(normalized)
    if duration_match:
        payload["duration_hours"] = float(duration_match.group("hours"))
    return payload


def _parse_start_time(text: str, *, anchor: datetime | None) -> tuple[dict[str, Any], tuple[int, int] | None]:
    if "人齐开" in text or "齐了开" in text or "人齐就开" in text:
        return ({"start_time_kind": START_KIND_ASAP_WHEN_FULL, "start_time": "人齐开"}, None)
    match = FIXED_TIME_PATTERN.search(text)
    if match is None:
        match = CHINESE_TIME_PATTERN.search(text)
    if match is None:
        return {}, None
    hour = int(match.group("hour"))
    half = bool(match.groupdict().get("half"))
    raw_minute = match.groupdict().get("minute")
    minute = 30 if half else int(raw_minute or 0)
    if hour > 23 or minute > 59:
        return {}, None
    stamp = anchor or now()
    stamp = stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=DEFAULT_TZ)
    if "明天" in text:
        stamp += timedelta(days=1)
    planned = stamp.replace(hour=hour, minute=minute, second=0, microsecond=0)
    display = f"{hour:02d}:{minute:02d}"
    return (
        {
            "start_time_kind": "scheduled",
            "start_time": display,
            "planned_start_at": planned.isoformat(),
        },
        match.span(),
    )


def _parse_stake(text: str, *, excluded_span: tuple[int, int] | None) -> tuple[dict[str, Any], tuple[int, int] | None]:
    cap_match = STAKE_CAP_PATTERN.search(text)
    if cap_match:
        return (
            {
                "stake": _clean_number(cap_match.group("base")),
                "base_stake": float(cap_match.group("base")),
                "cap_score": float(cap_match.group("cap")),
                "stake_label": f"{_clean_number(cap_match.group('base'))}-{_clean_number(cap_match.group('cap'))}",
            },
            cap_match.span(),
        )
    for match in DECIMAL_STAKE_PATTERN.finditer(text):
        if excluded_span and _spans_overlap(match.span(), excluded_span):
            continue
        if SEAT_CODE_PATTERN.fullmatch(match.group("stake")):
            continue
        value = _clean_number(match.group("stake"))
        return {"stake": value, "base_stake": float(match.group("stake")), "stake_label": value}, match.span()
    return {}, None


def _parse_smoke(text: str) -> str | None:
    if "无烟" in text or "禁烟" in text:
        return "no_smoking"
    if "烟都可" in text or "有烟无烟都" in text or "不限烟" in text or "烟不限" in text:
        return "any"
    if "有烟" in text or "可烟" in text:
        return "smoking"
    return None


def _parse_game_type(text: str) -> tuple[str | None, str | None]:
    if "cq" in text or "财敲" in text:
        return "hangzhou_mahjong", "caiqiao"
    if "川麻" in text or "四川麻将" in text:
        return "sichuan_mahjong", None
    if "红中" in text:
        return "red_center_mahjong", None
    if "杭麻" in text or "杭州麻将" in text:
        return "hangzhou_mahjong", None
    return None, None


def _clean_number(value: str) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def _spans_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


__all__ = ["parse_claim_item_no", "parse_explicit_need", "parse_game_post"]
