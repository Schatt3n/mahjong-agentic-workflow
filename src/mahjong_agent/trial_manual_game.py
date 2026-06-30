from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from typing import Any, Callable

from .trial_persistence import (
    ActionExecutor,
    ActionPlanProjector,
    ActionRecordFactory,
    GAME_TYPE_LABELS,
    VARIANT_LABELS,
)


TraceIdFactory = Callable[[], str]
NowFactory = Callable[[], datetime]
DateTimeParser = Callable[[Any], datetime | None]
GameLookup = Callable[[str], dict[str, Any] | None]
GameStateWriter = Callable[..., dict[str, Any]]
StateLoader = Callable[[datetime], dict[str, Any]]
GameCacheUpdater = Callable[[str], None]
ActionCompactor = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class TrialManualGameAdapter:
    """Controlled adapter for boss-created games from phone/offline input."""

    action_record_factory: ActionRecordFactory
    action_executor: ActionExecutor
    action_plan_projector: ActionPlanProjector
    game_state_writer: GameStateWriter
    game_lookup: GameLookup
    state_loader: StateLoader
    trace_id_factory: TraceIdFactory
    now_factory: NowFactory
    parse_datetime: DateTimeParser
    timezone: tzinfo
    action_compactor: ActionCompactor | None = None
    active_game_statuses: set[str] = field(default_factory=set)
    final_game_statuses: set[str] = field(default_factory=set)
    game_cache_updater: GameCacheUpdater | None = None

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        trace_id = str(payload.get("trace_id") or self.trace_id_factory())
        now = self.parse_datetime(payload.get("now")) or self.now_factory()
        spec = self._materialize(payload=payload, trace_id=trace_id, now=now)
        action = self.action_record_factory(
            trace_id=trace_id,
            stage="manual_create_game",
            action_name="create_game",
            arguments={
                "game_id": spec["game_id"],
                "status": spec["status"],
                "organizer_id": spec["organizer_id"],
                "organizer_name": spec["organizer_name"],
                "start_at": spec["parsed"]["start_at"],
                "level": spec["parsed"]["level"],
                "current_player_count": spec["parsed"]["current_player_count"],
                "missing_count": spec["parsed"]["missing_count"],
                "duration_hours": spec["parsed"]["duration_hours"],
                "rules": spec["parsed"]["rules"],
            },
            proposed_by="boss_manual",
            source="boss_manual",
            risk_level="medium",
            approval_required=True,
            reason="老板手动创建局，用于电话、线下口头消息等非文本入口。",
            now=now,
            validation={
                "allowed": True,
                "code": "manual_approved",
                "reason": "老板手动创建局，视为已审批。",
                "notes": ["内部看板写入，不会自动外发消息。"],
            },
        )
        create_result = self.action_executor(
            action,
            lambda: self.game_state_writer(
                game_id=spec["game_id"],
                status=spec["status"],
                organizer_id=spec["organizer_id"],
                organizer_name=spec["organizer_name"],
                source_text=spec["source_text"],
                parsed=spec["parsed"],
                notes=[
                    *spec["parsed"]["notes"],
                    {
                        "kind": "controlled_action",
                        "action": self.action_compactor(action) if self.action_compactor else _compact_action(action),
                    },
                ],
            ),
        )
        if create_result.get("ok") and self.game_cache_updater:
            self.game_cache_updater(spec["game_id"])
        created = self.game_lookup(spec["game_id"])
        return {
            "ok": bool(create_result.get("ok")),
            "deduplicated": bool(create_result.get("deduplicated")),
            "game": created or {"id": spec["game_id"], "parsed": spec["parsed"]},
            "agent_actions": [
                self.action_plan_projector(stage="manual_create_game", source="boss_manual", action=action)
            ],
            "state": self.state_loader(now),
        }

    def _materialize(self, *, payload: dict[str, Any], trace_id: str, now: datetime) -> dict[str, Any]:
        organizer_id = str(payload.get("organizer_id") or "boss_manual").strip() or "boss_manual"
        organizer_name = str(payload.get("organizer_name") or "老板手动创建").strip() or "老板手动创建"
        game_id = str(
            payload.get("game_id")
            or f"manual_{hashlib.sha256(f'manual-game:{trace_id}'.encode('utf-8')).hexdigest()[:12]}"
        )
        game_type = self._game_type(payload)
        game_label = GAME_TYPE_LABELS.get(game_type, "杭麻")
        variant = str(payload.get("variant") or "").strip() or None
        variant_label = VARIANT_LABELS.get(variant or "", variant)
        level = str(payload.get("level") or "").strip()
        if not level:
            raise ValueError("手动创建局需要填写档位")
        start_at = self._start_at(payload, now)
        if start_at is None:
            raise ValueError("手动创建局需要填写开局时间")
        current_player_count, missing_count = self._player_counts(payload)
        rules = self._rules(payload, game_label, variant_label)
        duration_hours = _safe_float(payload.get("duration_hours"))
        if duration_hours is None or duration_hours <= 0:
            raise ValueError("手动创建局需要填写预计时长")
        source_text = str(payload.get("source_text") or "").strip()
        if not source_text:
            source_text = "老板手动创建：" + self._summary(game_label, None, level, start_at, missing_count, rules)
        status = str(payload.get("status") or "").strip() or ("已满" if missing_count <= 0 else "待组局")
        if status not in self.active_game_statuses and status not in self.final_game_statuses and status != "已满":
            status = "待组局"
        parsed = {
            "id": game_id,
            "status": "open" if status not in self.final_game_statuses else "closed",
            "game_type": game_type,
            "game_label": " ".join(part for part in [game_label, variant_label] if part),
            "ruleset": game_type,
            "variant": variant,
            "variant_label": variant_label,
            "level": level,
            "base_score": _safe_float(level) if "-" not in level else None,
            "cap_score": None,
            "start_at": start_at.isoformat(),
            "start_time": start_at.strftime("%H:%M"),
            "duration_hours": duration_hours,
            "current_player_count": current_player_count,
            "missing_count": missing_count,
            "rules": rules,
            "play_options": [variant_label] if variant_label else [],
            "ambiguities": [],
            "notes": ["老板手动创建，用于电话/线下消息等非文本入口"],
            "summary": self._summary(game_label, variant_label, level, start_at, missing_count, rules),
            "intent_action": "manual_create_game",
            "user_intent": "老板手动创建局",
        }
        return {
            "game_id": game_id,
            "organizer_id": organizer_id,
            "organizer_name": organizer_name,
            "status": status,
            "source_text": source_text,
            "parsed": parsed,
        }

    def _game_type(self, payload: dict[str, Any]) -> str:
        raw = str(payload.get("game_type") or payload.get("game_label") or "hangzhou_mahjong").strip()
        mapping = {
            "杭麻": "hangzhou_mahjong",
            "财敲": "hangzhou_mahjong",
            "川麻": "sichuan_mahjong",
            "四川麻将": "sichuan_mahjong",
            "红中": "hongzhong_mahjong",
            "红中麻将": "hongzhong_mahjong",
            "捉鸡": "zhuoji_mahjong",
            "湖南麻将": "hunan_mahjong",
        }
        return mapping.get(raw, raw if raw in GAME_TYPE_LABELS else "hangzhou_mahjong")

    def _start_at(self, payload: dict[str, Any], now: datetime) -> datetime | None:
        explicit = self.parse_datetime(str(payload.get("start_at") or ""))
        if explicit:
            return explicit
        raw = str(payload.get("start_time") or "").strip()
        match = re.search(r"(\d{1,2})[:：](\d{1,2})", raw)
        if not match:
            match = re.search(r"(\d{1,2})\s*点(?:半|(\d{1,2})分?)?", raw)
        if not match:
            return None
        hour = int(match.group(1))
        minute_text = match.group(2)
        minute = 30 if "半" in raw and minute_text is None else int(minute_text or 0)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None
        candidate = datetime(now.year, now.month, now.day, hour, minute, tzinfo=self.timezone)
        if candidate < now - timedelta(minutes=30):
            candidate += timedelta(days=1)
        return candidate

    def _player_counts(self, payload: dict[str, Any]) -> tuple[int, int]:
        current = _safe_int(payload.get("current_player_count"))
        missing = _safe_int(payload.get("missing_count"))
        if current is None and missing is None:
            current, missing = 3, 1
        elif current is None:
            missing = max(0, min(4, missing or 0))
            current = max(0, 4 - missing)
        elif missing is None:
            current = max(0, min(4, current))
            missing = max(0, 4 - current)
        else:
            current = max(0, min(4, current))
            missing = max(0, min(4, missing))
        return current, missing

    def _rules(self, payload: dict[str, Any], game_label: str, variant_label: str | None) -> list[str]:
        rules = [game_label]
        if variant_label:
            rules.append(variant_label)
        smoke = str(payload.get("smoke") or payload.get("smoke_preference") or "").strip()
        smoke_rule = {
            "no_smoke": "无烟",
            "无烟": "无烟",
            "smoke_ok": "可吸烟",
            "有烟": "可吸烟",
            "可吸烟": "可吸烟",
            "any": "烟况都可",
            "都可": "烟况都可",
            "烟况都可": "烟况都可",
        }.get(smoke)
        if smoke_rule:
            rules.append(smoke_rule)
        extra = payload.get("rules") or []
        if isinstance(extra, str):
            extra = re.split(r"[,，、\s]+", extra)
        for item in extra:
            value = str(item or "").strip()
            if value:
                rules.append(value)
        return _unique_strings(rules)

    def _summary(
        self,
        game_label: str,
        variant_label: str | None,
        level: str,
        start_at: datetime,
        missing_count: int,
        rules: list[str],
    ) -> str:
        label = " ".join(part for part in [game_label, variant_label] if part)
        parts = [
            label,
            f"{level}档" if level else "",
            start_at.strftime("%H:%M"),
            f"缺{missing_count}",
            _smoke_text_from_rules(rules),
        ]
        return " ".join(part for part in parts if part)


def _compact_action(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_id": action.get("action_id"),
        "tool_name": action.get("tool_name"),
        "validation": action.get("validation"),
        "idempotency_key": action.get("idempotency_key"),
    }


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        value = str(item or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _smoke_text_from_rules(rules: list[str]) -> str:
    if "无烟" in rules:
        return "无烟"
    if "可吸烟" in rules or "有烟" in rules:
        return "有烟"
    if "烟况都可" in rules:
        return "烟况都可"
    return ""
