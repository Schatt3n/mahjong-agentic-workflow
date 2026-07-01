from __future__ import annotations

import re
from typing import Any


GENDER_LABELS = {"male": "男", "female": "女", "unknown": "未知"}
GENDER_NOTE_PREFIX = "候选人组合偏好："

GAME_TYPE_LABELS = {
    "mahjong": "麻将",
    "hangzhou_mahjong": "杭麻",
    "sichuan_mahjong": "川麻",
    "hongzhong_mahjong": "红中",
    "zhuoji_mahjong": "捉鸡",
    "hunan_mahjong": "湖南麻将",
    "chongqing_mahjong": "重庆麻将",
}

VARIANT_LABELS = {
    "caiqiao": "财敲",
    "yaoji": "幺鸡",
    "suji": "素鸡",
    "yaoji_47": "幺鸡47",
    "shayu": "鲨鱼",
}


def normalize_gender(value: Any) -> str:
    text = str(value or "").strip().lower()
    mapping = {
        "male": "male",
        "m": "male",
        "man": "male",
        "男": "male",
        "男性": "male",
        "男生": "male",
        "男士": "male",
        "female": "female",
        "f": "female",
        "woman": "female",
        "女": "female",
        "女性": "female",
        "女生": "female",
        "女士": "female",
        "unknown": "unknown",
        "未知": "unknown",
        "不确定": "unknown",
        "": "unknown",
    }
    return mapping.get(text, "unknown")


def infer_gender_from_customer_text(display_name: str, notes: str = "") -> str:
    name = display_name.strip()
    normalized_name = name.lower()
    note_text = notes.strip()
    if re.search(r"(^|[；;，,\s])男(性|生|士)?([；;，,\s]|$)", note_text):
        return "male"
    if re.search(r"(^|[；;，,\s])女(性|生|士)?([；;，,\s]|$)", note_text):
        return "female"
    if name.endswith("哥"):
        return "male"
    if name.endswith("姐"):
        return "female"
    if normalized_name in {"ben"}:
        return "male"
    if normalized_name in {"amy"}:
        return "female"
    return "unknown"


def gender_label(value: Any) -> str:
    return GENDER_LABELS.get(normalize_gender(value), "未知")
