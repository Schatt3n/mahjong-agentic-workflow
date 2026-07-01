from __future__ import annotations

import json

from mahjong_agent.trial_http_logging import (
    recent_log_lines,
    render_log_page,
    summarize_http_input,
    summarize_http_output,
    truncate_text,
)


def test_summarize_http_input_redacts_to_auditable_fields() -> None:
    content = summarize_http_input(
        "/api/analyze",
        {
            "conversationId": "conv_1",
            "sender_id": "zhang",
            "sender_name": "张哥",
            "text": "下午两点\\n0.5无烟杭麻，帮我组一桌",
            "ignored_large_field": "x" * 1000,
        },
    )

    payload = json.loads(content)

    assert payload == {
        "direction": "input",
        "path": "/api/analyze",
        "conversation_id": "conv_1",
        "sender_id": "zhang",
        "sender_name": "张哥",
        "text": "下午两点\\n0.5无烟杭麻，帮我组一桌",
    }


def test_summarize_http_output_keeps_decision_counts_and_short_reply() -> None:
    content = summarize_http_output(
        "/api/analyze",
        {
            "decision": {"action": "queue_invites", "reply_text": "好的，我帮你问问。"},
            "parsed": {"intent_action": "create_game", "user_intent": "找人组局", "id": "game_1"},
            "suggested_reply": {"text": "好的，我帮你问问。", "reasoning_summary": "信息齐全"},
            "missing_fields": [],
            "candidates": [{"id": "ran"}],
            "outbox": [{"id": "out_1"}, {"id": "out_2"}],
            "pool_matches": [],
            "conversation_id": "conv_1",
        },
    )

    payload = json.loads(content)

    assert payload["direction"] == "output"
    assert payload["action"] == "create_game"
    assert payload["raw_action"] == "queue_invites"
    assert payload["candidate_count"] == 1
    assert payload["outbox_count"] == 2
    assert payload["game_id"] == "game_1"


def test_recent_log_lines_returns_tail(tmp_path) -> None:
    path = tmp_path / "boss_trial_io.log"
    path.write_text("line1\nline2\nline3\n", encoding="utf-8")

    assert recent_log_lines(path, limit=2) == ["line2", "line3"]
    assert recent_log_lines(tmp_path / "missing.log") == []


def test_render_log_page_escapes_log_content() -> None:
    page = render_log_page(["trace-INFO: <script>alert(1)</script>"])

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "返回控制台" in page


def test_truncate_text_escapes_newlines_before_limit() -> None:
    assert truncate_text("a\nb", 10) == "a\\nb"
    assert truncate_text("abcdef", 4) == "abc…"
