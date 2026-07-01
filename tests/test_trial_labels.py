from __future__ import annotations

from mahjong_agent.trial_labels import (
    GAME_TYPE_LABELS,
    GENDER_LABELS,
    VARIANT_LABELS,
    gender_label,
    infer_gender_from_customer_text,
    normalize_gender,
)


def test_normalize_gender_accepts_common_aliases() -> None:
    assert normalize_gender("男士") == "male"
    assert normalize_gender("woman") == "female"
    assert normalize_gender("不确定") == "unknown"
    assert normalize_gender("other") == "unknown"


def test_infer_gender_from_customer_name_and_notes() -> None:
    assert infer_gender_from_customer_text("张哥") == "male"
    assert infer_gender_from_customer_text("王姐") == "female"
    assert infer_gender_from_customer_text("小陈", "常客；男性；下午常来") == "male"
    assert infer_gender_from_customer_text("小李", "备注，女士，无烟") == "female"
    assert infer_gender_from_customer_text("Sam") == "unknown"


def test_gender_label_uses_normalized_value() -> None:
    assert gender_label("女") == "女"
    assert gender_label("male") == "男"
    assert gender_label("n/a") == "未知"
    assert GENDER_LABELS["unknown"] == "未知"


def test_trial_game_and_variant_labels_match_boss_trial_display_contract() -> None:
    assert GAME_TYPE_LABELS["hangzhou_mahjong"] == "杭麻"
    assert GAME_TYPE_LABELS["hongzhong_mahjong"] == "红中"
    assert VARIANT_LABELS["caiqiao"] == "财敲"
