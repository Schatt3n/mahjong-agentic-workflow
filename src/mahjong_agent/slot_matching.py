from __future__ import annotations

import re
from typing import Any

from .workflow_models import SlotValue


ANY_SLOT_VALUES: dict[str, set[str]] = {
    "smoke": {
        "any",
        "either",
        "both",
        "smoke_any",
        "smoke_ok",
        "都可",
        "都行",
        "均可",
        "有烟无烟都可",
        "有烟无烟都行",
    },
}

VALUE_ALIASES: dict[str, dict[str, str]] = {
    "smoke": {
        "无烟": "no_smoke",
        "不要烟": "no_smoke",
        "禁烟": "no_smoke",
        "no smoke": "no_smoke",
        "有烟": "smoke_ok",
        "可烟": "smoke_ok",
        "能抽烟": "smoke_ok",
        "smoking": "smoke_ok",
    },
    "game_type": {
        "杭麻": "hangzhou_mahjong",
        "杭州麻将": "hangzhou_mahjong",
        "财敲": "hangzhou_mahjong",
        "川麻": "sichuan_mahjong",
        "四川麻将": "sichuan_mahjong",
    },
}


def slot_values_compatible(requested: SlotValue | None, offered: SlotValue | None, *, slot_name: str) -> bool:
    """Return whether two usable slot values can represent an acceptable match.

    This belongs to the contract/tool boundary: the LLM may express a slot as a
    single value, a list of acceptable values, or an "any" value. Backend layers
    should compare those forms consistently instead of scattering string checks.
    """

    if requested is None or not requested.usable:
        return True
    if offered is None or not offered.usable:
        return True
    requested_values = normalized_slot_values(requested.value, slot_name=slot_name)
    offered_values = normalized_slot_values(offered.value, slot_name=slot_name)
    if not requested_values or not offered_values:
        return True
    if any(_is_any_value(item, slot_name=slot_name) for item in requested_values):
        return True
    if any(_is_any_value(item, slot_name=slot_name) for item in offered_values):
        return True
    return bool(set(requested_values) & set(offered_values))


def normalized_slot_values(value: Any, *, slot_name: str) -> list[str]:
    if value in (None, "", "unknown"):
        return []
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(normalized_slot_values(item, slot_name=slot_name))
        return _dedupe(values)
    if isinstance(value, (list, tuple, set)):
        values = []
        for item in value:
            values.extend(normalized_slot_values(item, slot_name=slot_name))
        return _dedupe(values)
    text = str(value).strip()
    if not text:
        return []
    parts = [
        part.strip()
        for part in re.split(r"[/／,，、;；]|\bor\b|或者|或|和", text)
        if part.strip()
    ]
    if not parts:
        parts = [text]
    return _dedupe(_normalize_scalar(part, slot_name=slot_name) for part in parts)


def _normalize_scalar(value: str, *, slot_name: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.replace("。", ".").replace("．", ".").replace("，", ",")
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"(?<!\d)0[,、]\s*5(?!\d)", "0.5", normalized)
    aliases = VALUE_ALIASES.get(slot_name, {})
    return aliases.get(normalized, normalized)


def _is_any_value(value: str, *, slot_name: str) -> bool:
    if value in {"any", "either", "both", "all", "不限", "都可", "都行", "均可"}:
        return True
    return value in ANY_SLOT_VALUES.get(slot_name, set())


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
