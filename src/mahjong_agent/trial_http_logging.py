from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def truncate_text(value: str, limit: int) -> str:
    text = value.replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def summarize_http_input(path: str, body: dict[str, Any]) -> str:
    if path == "/api/analyze":
        return _dump_json(
            {
                "direction": "input",
                "path": path,
                "conversation_id": body.get("conversation_id") or body.get("conversationId"),
                "sender_id": body.get("sender_id"),
                "sender_name": body.get("sender_name"),
                "text": truncate_text(str(body.get("text") or ""), 240),
            }
        )
    if path == "/api/feedback":
        return _dump_json(
            {
                "direction": "input",
                "path": path,
                "game_id": body.get("game_id"),
                "outbox_id": body.get("outbox_id"),
                "customer_id": body.get("customer_id"),
                "feedback_type": body.get("feedback_type"),
            }
        )
    if path == "/api/approval-decision":
        return _dump_json(
            {
                "direction": "input",
                "path": path,
                "approval_id": body.get("approval_id"),
                "target_type": body.get("target_type"),
                "target_id": body.get("target_id"),
                "decision": body.get("decision") or body.get("status"),
            }
        )
    if path == "/api/send-outbox":
        return _dump_json(
            {
                "direction": "input",
                "path": path,
                "outbox_id": body.get("outbox_id"),
                "channel": body.get("channel") or "manual",
            }
        )
    if path == "/api/runtime-policy":
        return _dump_json(
            {
                "direction": "input",
                "path": path,
                "controlled_agent_mode": body.get("controlled_agent_mode"),
                "read_only_mode": body.get("read_only_mode"),
                "state_writes_enabled": body.get("state_writes_enabled"),
                "delivery_enabled": body.get("delivery_enabled"),
                "approval_enabled": body.get("approval_enabled"),
                "eval_writes_enabled": body.get("eval_writes_enabled"),
                "llm_required_for_side_effect_tools": body.get("llm_required_for_side_effect_tools"),
                "llm_required_for_state_writes": body.get("llm_required_for_state_writes"),
                "reason": truncate_text(str(body.get("reason") or ""), 160),
            }
        )
    if path == "/api/candidate-message":
        return _dump_json(
            {
                "direction": "input",
                "path": path,
                "game_id": body.get("game_id"),
                "outbox_id": body.get("outbox_id"),
                "source_trace_id": body.get("source_trace_id"),
                "sender_id": body.get("sender_id"),
                "text": truncate_text(str(body.get("text") or ""), 240),
            }
        )
    if path == "/api/clear-board":
        return _dump_json(
            {
                "direction": "input",
                "path": path,
                "reason": truncate_text(str(body.get("reason") or ""), 160),
            }
        )
    if path == "/api/clear-short-memory":
        return _dump_json(
            {
                "direction": "input",
                "path": path,
                "conversation_id": body.get("conversation_id") or body.get("conversationId"),
                "sender_id": body.get("sender_id") or body.get("senderId"),
                "reason": truncate_text(str(body.get("reason") or ""), 160),
            }
        )
    if path == "/api/manual-create-game":
        return _dump_json(
            {
                "direction": "input",
                "path": path,
                "organizer_id": body.get("organizer_id"),
                "organizer_name": body.get("organizer_name"),
                "game_type": body.get("game_type"),
                "level": body.get("level"),
                "start_time": body.get("start_time"),
                "current_player_count": body.get("current_player_count"),
                "missing_count": body.get("missing_count"),
                "smoke": body.get("smoke"),
                "status": body.get("status"),
            }
        )
    if path == "/api/customers":
        return _dump_json(
            {
                "direction": "input",
                "path": path,
                "customer_id": body.get("id"),
                "display_name": body.get("display_name"),
                "gender": body.get("gender"),
                "preferred_games": body.get("preferred_games"),
                "preferred_levels": body.get("preferred_levels"),
            }
        )
    if path == "/api/eval-cases":
        analysis = body.get("analysis") if isinstance(body.get("analysis"), dict) else {}
        return _dump_json(
            {
                "direction": "input",
                "path": path,
                "case_type": body.get("case_type") or body.get("kind"),
                "source_trace_id": body.get("source_trace_id") or analysis.get("trace_id"),
                "sender_id": body.get("sender_id") or analysis.get("sender_id"),
                "text": truncate_text(
                    str(body.get("text") or analysis.get("source_text") or analysis.get("effective_text") or ""),
                    240,
                ),
                "note": truncate_text(str(body.get("note") or body.get("notes") or ""), 160),
            }
        )
    return _dump_json({"direction": "input", "path": path})


def summarize_http_output(path: str, payload: dict[str, Any]) -> str:
    if path == "/api/analyze":
        decision = payload.get("decision") or {}
        parsed = payload.get("parsed") if isinstance(payload.get("parsed"), dict) else {}
        suggested = payload.get("suggested_reply") if isinstance(payload.get("suggested_reply"), dict) else {}
        return _dump_json(
            {
                "direction": "output",
                "path": path,
                "action": parsed.get("intent_action") or decision.get("action"),
                "raw_action": decision.get("action"),
                "intent_action": parsed.get("intent_action"),
                "user_intent": parsed.get("user_intent"),
                "reply_text": truncate_text(str(decision.get("reply_text") or ""), 240),
                "suggested_reply": truncate_text(str(suggested.get("text") or ""), 240),
                "suggested_reasoning": truncate_text(str(suggested.get("reasoning_summary") or ""), 240),
                "missing_fields": payload.get("missing_fields") or [],
                "group_draft": truncate_text(str(payload.get("group_draft") or ""), 240),
                "candidate_count": len(payload.get("candidates") or []),
                "outbox_count": len(payload.get("outbox") or []),
                "pool_match_count": len(payload.get("pool_matches") or []),
                "used_short_memory": bool(payload.get("used_short_memory")),
                "conversation_id": payload.get("conversation_id"),
                "game_id": parsed.get("id"),
            }
        )
    if path == "/api/state":
        return _dump_json(
            {
                "direction": "output",
                "path": path,
                "customer_count": len(payload.get("customers") or []),
                "game_count": len(payload.get("games") or []),
                "recent_outbox_count": len(payload.get("recent_outbox") or []),
                "redis_enabled": (payload.get("cache") or {}).get("redis_enabled"),
            }
        )
    if path == "/api/feedback":
        state = payload.get("state") or {}
        return _dump_json(
            {
                "direction": "output",
                "path": path,
                "ok": payload.get("ok"),
                "game_count": len(state.get("games") or []),
                "recent_outbox_count": len(state.get("recent_outbox") or []),
            }
        )
    if path == "/api/approval-decision":
        state = payload.get("state") or {}
        approval = payload.get("approval") or {}
        return _dump_json(
            {
                "direction": "output",
                "path": path,
                "ok": payload.get("ok"),
                "approval_id": approval.get("id"),
                "approval_status": approval.get("status"),
                "target_type": approval.get("target_type"),
                "target_id": approval.get("target_id"),
                "recent_approval_count": len(state.get("recent_approvals") or []),
            }
        )
    if path == "/api/send-outbox":
        state = payload.get("state") or {}
        delivery = payload.get("delivery") or {}
        outbox_item = payload.get("outbox_item") or {}
        return _dump_json(
            {
                "direction": "output",
                "path": path,
                "ok": payload.get("ok"),
                "deduplicated": payload.get("deduplicated"),
                "delivery_id": delivery.get("id"),
                "outbox_id": delivery.get("outbox_id") or outbox_item.get("id"),
                "outbox_status": outbox_item.get("status"),
                "recent_delivery_count": len(state.get("recent_delivery_attempts") or []),
            }
        )
    if path == "/api/runtime-policy":
        policy = payload.get("policy") or {}
        return _dump_json(
            {
                "direction": "output",
                "path": path,
                "ok": payload.get("ok"),
                "controlled_agent_mode": policy.get("controlled_agent_mode"),
                "read_only_mode": policy.get("read_only_mode"),
                "state_writes_enabled": policy.get("state_writes_enabled"),
                "delivery_enabled": policy.get("delivery_enabled"),
                "approval_enabled": policy.get("approval_enabled"),
                "eval_writes_enabled": policy.get("eval_writes_enabled"),
                "llm_required_for_side_effect_tools": policy.get("llm_required_for_side_effect_tools"),
                "llm_required_for_state_writes": policy.get("llm_required_for_state_writes"),
            }
        )
    if path == "/api/candidate-message":
        state = payload.get("state") or {}
        candidate = payload.get("candidate_message") or {}
        return _dump_json(
            {
                "direction": "output",
                "path": path,
                "ok": payload.get("ok"),
                "intent": candidate.get("intent"),
                "feedback_type": candidate.get("feedback_type"),
                "suggested_boss_reply": truncate_text(str(candidate.get("suggested_boss_reply") or ""), 240),
                "game_count": len(state.get("games") or []),
                "recent_outbox_count": len(state.get("recent_outbox") or []),
            }
        )
    if path == "/api/manual-create-game":
        state = payload.get("state") or {}
        game = payload.get("game") or {}
        return _dump_json(
            {
                "direction": "output",
                "path": path,
                "ok": payload.get("ok"),
                "game_id": game.get("id"),
                "game_count": len(state.get("games") or []),
            }
        )
    if path == "/api/clear-board":
        state = payload.get("state") or {}
        return _dump_json(
            {
                "direction": "output",
                "path": path,
                "ok": payload.get("ok"),
                "cleared_count": payload.get("cleared_count"),
                "cleared_game_ids": payload.get("cleared_game_ids") or [],
                "game_count": len(state.get("games") or []),
            }
        )
    if path == "/api/clear-short-memory":
        return _dump_json(
            {
                "direction": "output",
                "path": path,
                "ok": payload.get("ok"),
                "conversation_id": payload.get("conversation_id"),
                "sender_id": payload.get("sender_id"),
                "cleared_count": payload.get("cleared_count"),
                "cache_key": payload.get("cache_key"),
            }
        )
    if path == "/api/customers":
        return _dump_json(
            {
                "direction": "output",
                "path": path,
                "customer_id": payload.get("id"),
                "display_name": payload.get("display_name"),
            }
        )
    if path == "/api/eval-cases":
        return _dump_json(
            {
                "direction": "output",
                "path": path,
                "ok": payload.get("ok"),
                "case_type": payload.get("case_type"),
                "record_id": payload.get("record_id"),
                "dataset_path": payload.get("path"),
                "counts": (payload.get("overview") or {}).get("counts"),
            }
        )
    return _dump_json({"direction": "output", "path": path})


def recent_log_lines(log_path: Path, limit: int = 200) -> list[str]:
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def render_log_page(lines: list[str], *, title: str = "麻将馆试用日志") -> str:
    body = "\n".join(lines) if lines else "暂无日志。"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; padding: 24px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background: #f7f8f5; color: #1f2a24; }}
    .bar {{ display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin-bottom: 16px; }}
    h1 {{ font-size: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    a {{ color: #286955; text-decoration: none; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #fff; border: 1px solid #d9ded6; border-radius: 8px; padding: 16px; line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="bar">
    <h1>{html.escape(title)}</h1>
    <a href="/">返回控制台</a>
  </div>
  <pre>{html.escape(body)}</pre>
</body>
</html>"""


def _dump_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
