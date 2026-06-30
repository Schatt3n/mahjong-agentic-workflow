from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Callable, Protocol

from .budget import LLMBudgetManager, usage_from_response
from .candidate_reply_draft import CandidateReplyDraftService
from .llm import LLMConfig


AuditLogger = Callable[[str, str, dict[str, Any]], None]
FallbackClassifier = Callable[[str, dict[str, Any] | None], dict[str, Any]]
CustomerLookup = Callable[[str], dict[str, Any] | None]
ConfirmedCountProvider = Callable[[dict[str, Any] | None], int]


class UrlOpenResponse(Protocol):
    def __enter__(self) -> "UrlOpenResponse":
        ...

    def __exit__(self, exc_type, exc, tb) -> None:
        ...

    def read(self) -> bytes:
        ...


UrlOpen = Callable[..., UrlOpenResponse]


VALID_CANDIDATE_SEMANTIC_TYPES = {
    "accepted",
    "arrived",
    "declined",
    "ask_later",
    "candidate_question",
    "candidate_negotiation",
    "do_not_disturb",
    "uncertain",
}

VALID_CANDIDATE_ACTIONS = {
    "mark_candidate_confirmed",
    "mark_candidate_arrived",
    "mark_candidate_declined",
    "mark_candidate_ask_later",
    "answer_candidate_question",
    "start_negotiation",
    "set_do_not_disturb",
    "request_human_review",
    "no_state_change",
}

SEMANTIC_TO_ACTION = {
    "accepted": "mark_candidate_confirmed",
    "arrived": "mark_candidate_arrived",
    "declined": "mark_candidate_declined",
    "ask_later": "mark_candidate_ask_later",
    "candidate_question": "answer_candidate_question",
    "candidate_negotiation": "start_negotiation",
    "do_not_disturb": "set_do_not_disturb",
    "uncertain": "request_human_review",
}

ACTION_TO_FEEDBACK_TYPE = {
    "mark_candidate_confirmed": "accepted",
    "mark_candidate_arrived": "arrived",
    "mark_candidate_declined": "declined",
    "mark_candidate_ask_later": "ask_later",
    "answer_candidate_question": "candidate_question",
    "start_negotiation": "candidate_negotiation",
    "set_do_not_disturb": "do_not_disturb",
    "request_human_review": "candidate_question",
    "no_state_change": "candidate_question",
}

FEEDBACK_TYPE_TO_ACTION = {
    "accepted": "mark_candidate_confirmed",
    "arrived": "mark_candidate_arrived",
    "declined": "mark_candidate_declined",
    "ask_later": "mark_candidate_ask_later",
    "candidate_question": "answer_candidate_question",
    "candidate_negotiation": "start_negotiation",
    "do_not_disturb": "set_do_not_disturb",
}


FallbackProposalFactory = Callable[[str, dict[str, Any], dict[str, Any] | None], dict[str, Any]]
LLMProposalFactory = Callable[..., dict[str, Any]]


CANDIDATE_SEMANTIC_SYSTEM_PROMPT = """你是麻将馆候选人回复的语义解析器和动作提案器。
你必须结合上下文判断候选人的真实含义：原邀约消息、当前局状态、已确认人数、候选人历史回复、候选人画像。
你只能“提出动作”，不能直接改数据库，不能声称已经发送真实消息。
后端会校验状态机、幂等、并发、局是否已满、候选人是否在该局 outbox 中、风险和置信度后再落库。

可用 semantic_type：
- accepted：候选人明确答应当前邀约，且没有提出新条件。
- arrived：候选人说已经到店/到了。
- declined：候选人拒绝或表示来不了。
- ask_later：候选人暂时不确定、让稍后再说。
- candidate_question：候选人只是追问时间/地点/烟况/玩法/人数等信息。
- candidate_negotiation：候选人提出和原局不同的新条件，例如改时间、改时长、改烟况、改玩法。
- do_not_disturb：候选人明确不要再问/别打扰。
- uncertain：语义不够确定。

可用 proposed_action：
- mark_candidate_confirmed
- mark_candidate_arrived
- mark_candidate_declined
- mark_candidate_ask_later
- answer_candidate_question
- start_negotiation
- set_do_not_disturb
- request_human_review
- no_state_change

输出要求：
- 如果候选人说“打！”、“来”、“可以”、“行”、“算我”等，在原邀约语境下通常是 accepted。
- 如果候选人说“可以，但是/不过/最早/只能/想打X小时/能不能X点”，通常是 candidate_negotiation。
- reply_text 是老板给候选人的建议回复，短、自然、微信口吻。
- accepted/arrived 时，reply_text 要使用 context.state_preview.if_confirmed.fallback_reply 的局面标签，不能自己编 371/272/人齐。
- candidate_negotiation 时，不能说加你、371、272、人齐、已确认，要先说问下这桌其他人/发起人。
- 不要说“给你留着/留位/留座”。
- reasoning_summary 只写一句简短判断依据，不要输出长篇思维链。

只输出 JSON：
{"semantic_type":"accepted|arrived|declined|ask_later|candidate_question|candidate_negotiation|do_not_disturb|uncertain","proposed_action":"动作名","confidence":0.0,"reply_text":"老板建议回复","risk_level":"low|medium|high","reasoning_summary":"一句话原因","extracted_facts":{"requested_start_time":"可选 HH:MM","requested_start_at":"可选 ISO 时间","requested_duration_hours":null},"notes":["可选简短说明"]}"""


@dataclass(frozen=True, slots=True)
class CandidateSemanticProposalResult:
    """Candidate reply semantic contract result.

    The proposal is what the model or fallback semantic resolver suggests.
    The fallback is always preserved so the backend validator can compare or
    safely degrade without re-running semantic heuristics.
    """

    proposal: dict[str, Any]
    fallback: dict[str, Any]


@dataclass(slots=True)
class CandidateSemanticProposalAdapter:
    """Build a candidate-reply semantic proposal without side effects.

    This adapter is intentionally limited to the LLM/fallback proposal boundary.
    It does not validate actions, execute tools, update state, or send messages.
    """

    fallback_proposal_factory: FallbackProposalFactory
    llm_proposal_factory: LLMProposalFactory

    def propose(
        self,
        *,
        trace_id: str,
        candidate_text: str,
        outbox_item: dict[str, Any],
        game: dict[str, Any] | None,
        now: datetime,
    ) -> CandidateSemanticProposalResult:
        fallback = self._safe_fallback(candidate_text, outbox_item, game)
        try:
            proposal = self.llm_proposal_factory(
                trace_id=trace_id,
                candidate_text=candidate_text,
                outbox_item=outbox_item,
                game=game,
                fallback=fallback,
                now=now,
            )
        except Exception as exc:
            proposal = self._fallback_with_note(
                fallback,
                f"LLM candidate semantic proposal raised {type(exc).__name__}: {exc}",
            )
        if not isinstance(proposal, dict):
            proposal = self._fallback_with_note(
                fallback,
                f"LLM candidate semantic proposal returned {type(proposal).__name__}, expected dict.",
            )
        return CandidateSemanticProposalResult(proposal=dict(proposal), fallback=fallback)

    def _safe_fallback(
        self,
        candidate_text: str,
        outbox_item: dict[str, Any],
        game: dict[str, Any] | None,
    ) -> dict[str, Any]:
        fallback = self.fallback_proposal_factory(candidate_text, outbox_item, game)
        if isinstance(fallback, dict):
            return dict(fallback)
        return {
            "source": "rules",
            "model": None,
            "semantic_type": "uncertain",
            "proposed_action": "request_human_review",
            "confidence": 0.0,
            "reply_text": "",
            "risk_level": "medium",
            "reasoning_summary": "Fallback semantic resolver returned invalid contract.",
            "notes": [f"fallback_return_type={type(fallback).__name__}"],
            "extracted_facts": {},
            "backend_fallback_classification": {
                "intent": "candidate_question",
                "feedback_type": "candidate_question",
                "status": "待确认",
            },
            "outbox_id": outbox_item.get("id"),
        }

    def _fallback_with_note(self, fallback: dict[str, Any], note: str) -> dict[str, Any]:
        proposal = dict(fallback)
        notes = proposal.get("notes") if isinstance(proposal.get("notes"), list) else []
        proposal["notes"] = [*notes, note]
        proposal["reasoning_summary"] = note
        return proposal


@dataclass(slots=True)
class CandidateSemanticResolverService:
    """Build candidate reply semantic contracts without writing state.

    The service may call an LLM to produce a semantic/action proposal contract,
    but it never validates the action, updates game state, records feedback, or
    sends messages. Those steps remain backend-owned.
    """

    fallback_classifier: FallbackClassifier
    llm_config: LLMConfig | None = None
    budget_manager: LLMBudgetManager | None = None
    audit_logger: AuditLogger | None = None
    customer_lookup: CustomerLookup | None = None
    confirmed_count_provider: ConfirmedCountProvider | None = None
    urlopen: UrlOpen = urllib.request.urlopen

    def fallback_proposal(
        self,
        text: str,
        outbox_item: dict[str, Any],
        game: dict[str, Any] | None,
    ) -> dict[str, Any]:
        classification = self.fallback_classifier(text, game)
        feedback_type = str(classification.get("feedback_type") or "candidate_question")
        return {
            "source": "rules",
            "model": None,
            "semantic_type": feedback_type,
            "proposed_action": candidate_action_for_feedback_type(feedback_type),
            "confidence": 0.65,
            "reply_text": "",
            "risk_level": "low",
            "reasoning_summary": "LLM 不可用，使用后端安全降级语义判断。",
            "notes": [],
            "extracted_facts": {},
            "backend_fallback_classification": classification,
            "outbox_id": outbox_item.get("id"),
        }

    def llm_proposal(
        self,
        *,
        trace_id: str,
        candidate_text: str,
        outbox_item: dict[str, Any],
        game: dict[str, Any] | None,
        fallback: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        if not self.llm_config or not self.budget_manager:
            return fallback
        max_tokens = min(self.llm_config.max_completion_tokens, 260)
        payload = self.payload(
            candidate_text=candidate_text,
            outbox_item=outbox_item,
            game=game,
            now=now,
            max_tokens=max_tokens,
        )
        budget_decision = self.budget_manager.reserve(
            key="boss_trial_candidate_semantic",
            model=self.llm_config.model,
            prompt=payload,
            max_completion_tokens=max_tokens,
        )
        if not budget_decision.allowed:
            self._audit(
                trace_id,
                "llm_budget_denied",
                {
                    "stage": "candidate_action_proposal",
                    "provider": self.llm_config.provider,
                    "model": self.llm_config.model,
                    "budget": budget_decision.to_dict(),
                },
            )
            return {
                **fallback,
                "model": self.llm_config.model,
                "reasoning_summary": "LLM 预算拒绝，使用后端安全降级语义判断。",
            }

        self._audit(
            trace_id,
            "llm_request",
            {
                "stage": "candidate_action_proposal",
                "provider": self.llm_config.provider,
                "model": self.llm_config.model,
                "base_url": self.llm_config.base_url,
                "timeout_seconds": self.llm_config.timeout_seconds,
                "budget": budget_decision.to_dict(),
                "payload": payload,
            },
        )
        request = urllib.request.Request(
            f"{self.llm_config.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.llm_config.api_key}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        try:
            with self.urlopen(request, timeout=self.llm_config.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self._audit(
                trace_id,
                "llm_error",
                {
                    "stage": "candidate_action_proposal",
                    "provider": self.llm_config.provider,
                    "model": self.llm_config.model,
                    "error": f"HTTP {exc.code}",
                    "budget": budget_decision.to_dict(),
                },
            )
            return {
                **fallback,
                "model": self.llm_config.model,
                "reasoning_summary": f"LLM 语义提案失败，使用安全降级：HTTP {exc.code}",
            }
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            self._audit(
                trace_id,
                "llm_error",
                {
                    "stage": "candidate_action_proposal",
                    "provider": self.llm_config.provider,
                    "model": self.llm_config.model,
                    "error": f"{type(exc).__name__}: {exc}",
                    "budget": budget_decision.to_dict(),
                },
            )
            return {
                **fallback,
                "model": self.llm_config.model,
                "reasoning_summary": f"LLM 语义提案失败，使用安全降级：{type(exc).__name__}",
            }

        actual_usage = usage_from_response(data, self.llm_config.model)
        self.budget_manager.commit(budget_decision.reservation_id, actual_usage)
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        self._audit(
            trace_id,
            "llm_response",
            {
                "stage": "candidate_action_proposal",
                "provider": self.llm_config.provider,
                "model": self.llm_config.model,
                "raw_response": data,
                "content": content,
                "usage": actual_usage.to_dict() if actual_usage else None,
            },
        )
        parsed = _parse_json_object(content)
        proposal = normalize_candidate_action_proposal(
            parsed,
            fallback=fallback,
            source="llm",
            model=self.llm_config.model,
            budget=budget_decision.to_dict(),
        )
        self._audit(
            trace_id,
            "llm_parsed",
            {
                "stage": "candidate_action_proposal",
                "provider": self.llm_config.provider,
                "model": self.llm_config.model,
                "parsed": proposal,
            },
        )
        return proposal

    def payload(
        self,
        *,
        candidate_text: str,
        outbox_item: dict[str, Any],
        game: dict[str, Any] | None,
        now: datetime,
        max_tokens: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.llm_config.model if self.llm_config else "",
            "temperature": min(self.llm_config.temperature, 0.2) if self.llm_config else 0.1,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": CANDIDATE_SEMANTIC_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        self.action_context(
                            candidate_text=candidate_text,
                            outbox_item=outbox_item,
                            game=game,
                            now=now,
                        ),
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        if self.llm_config and self.llm_config.thinking_enabled is not None:
            payload["thinking"] = {"type": "enabled" if self.llm_config.thinking_enabled else "disabled"}
        if self.llm_config and self.llm_config.response_format:
            payload["response_format"] = {"type": self.llm_config.response_format}
        return payload

    def action_context(
        self,
        *,
        candidate_text: str,
        outbox_item: dict[str, Any],
        game: dict[str, Any] | None,
        now: datetime,
    ) -> dict[str, Any]:
        parsed = game.get("parsed") if isinstance(game, dict) and isinstance(game.get("parsed"), dict) else {}
        confirmed_before = self._confirmed_count(game) if isinstance(game, dict) else 0
        reply_service = CandidateReplyDraftService(confirmed_count_provider=self._confirmed_count)
        if_confirmed_label = reply_service.progress_label_after_candidate(game, outbox_item, include_candidate=True)
        no_change_label = reply_service.progress_label_after_candidate(game, outbox_item, include_candidate=False)
        customer = self._customer(str(outbox_item.get("customer_id") or ""))
        return {
            "task": "理解候选人回复并提出后端可校验动作。不要直接改状态。",
            "now": now.isoformat(),
            "candidate": {
                "customer_id": outbox_item.get("customer_id"),
                "customer_name": outbox_item.get("customer_name"),
                "reply_text": candidate_text,
                "profile": {
                    "gender": customer.get("gender"),
                    "preferred_games": customer.get("preferred_games") or [],
                    "preferred_levels": customer.get("preferred_levels") or [],
                    "smoke_preference": customer.get("smoke_preference"),
                    "notes": customer.get("notes"),
                },
                "current_outbox_status": outbox_item.get("status"),
                "conversation": outbox_item.get("conversation") or [],
            },
            "original_invite": {
                "message_text": outbox_item.get("message_text"),
                "game_id": outbox_item.get("game_id"),
            },
            "game_state": {
                "game_id": (game or {}).get("id") or outbox_item.get("game_id"),
                "status": (game or {}).get("status"),
                "summary": parsed.get("summary"),
                "start_time": parsed.get("start_time"),
                "start_at": parsed.get("start_at"),
                "level": parsed.get("level"),
                "duration_hours": parsed.get("duration_hours"),
                "rules": parsed.get("rules") or [],
                "current_player_count": parsed.get("current_player_count"),
                "missing_count": parsed.get("missing_count"),
                "confirmed_before": confirmed_before,
                "participants": (game or {}).get("participants") or [],
                "outbox_statuses": [
                    {
                        "customer_id": item.get("customer_id"),
                        "customer_name": item.get("customer_name"),
                        "status": item.get("status"),
                    }
                    for item in ((game or {}).get("outbox") or [])[:12]
                ],
            },
            "state_preview": {
                "if_confirmed": {
                    "confirmed_after": confirmed_before + (0 if str(outbox_item.get("status") or "") in {"已确认", "已到店"} else 1),
                    "progress_label_after": if_confirmed_label,
                    "fallback_reply": reply_service.accepted_reply(game, outbox_item),
                },
                "if_no_state_change": {
                    "confirmed_count": confirmed_before,
                    "progress_label": no_change_label,
                },
            },
            "backend_boundaries": [
                "LLM 只能返回 proposed_action；后端校验后才会 record_feedback。",
                "候选人不在 outbox、局已满、局已结束、状态冲突、低置信度时，后端会拒绝提交。",
                "send_message 当前只能创建待审批消息，不能自动外发。",
            ],
        }

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

    def _customer(self, customer_id: str) -> dict[str, Any]:
        if not customer_id or not self.customer_lookup:
            return {}
        customer = self.customer_lookup(customer_id)
        return customer if isinstance(customer, dict) else {}

    def _audit(self, trace_id: str, event: str, payload: dict[str, Any]) -> None:
        if self.audit_logger:
            self.audit_logger(trace_id, event, payload)


def normalize_candidate_semantic_type(value: str) -> str:
    normalized = re.sub(r"[\s_-]+", "", str(value or "").lower())
    aliases = {
        "accept": "accepted",
        "accepted": "accepted",
        "confirm": "accepted",
        "confirmed": "accepted",
        "candidateaccept": "accepted",
        "arrive": "arrived",
        "arrived": "arrived",
        "decline": "declined",
        "declined": "declined",
        "reject": "declined",
        "asklater": "ask_later",
        "later": "ask_later",
        "question": "candidate_question",
        "candidatequestion": "candidate_question",
        "negotiation": "candidate_negotiation",
        "candidatenegotiation": "candidate_negotiation",
        "donotdisturb": "do_not_disturb",
        "dnd": "do_not_disturb",
        "uncertain": "uncertain",
    }
    if normalized in aliases:
        return aliases[normalized]
    value = str(value or "")
    return value if value in VALID_CANDIDATE_SEMANTIC_TYPES else "uncertain"


def normalize_candidate_proposed_action(value: str, *, semantic_type: str) -> str:
    normalized = re.sub(r"[\s_-]+", "", str(value or "").lower())
    aliases = {
        "markcandidateconfirmed": "mark_candidate_confirmed",
        "confirmcandidate": "mark_candidate_confirmed",
        "markconfirmed": "mark_candidate_confirmed",
        "markcandidatearrived": "mark_candidate_arrived",
        "markarrived": "mark_candidate_arrived",
        "markcandidatedeclined": "mark_candidate_declined",
        "declinecandidate": "mark_candidate_declined",
        "markcandidateasklater": "mark_candidate_ask_later",
        "asklater": "mark_candidate_ask_later",
        "answercandidatequestion": "answer_candidate_question",
        "answerquestion": "answer_candidate_question",
        "startnegotiation": "start_negotiation",
        "negotiation": "start_negotiation",
        "setdonotdisturb": "set_do_not_disturb",
        "requesthumanreview": "request_human_review",
        "nostatechange": "no_state_change",
    }
    action = aliases.get(normalized, str(value or ""))
    if action in VALID_CANDIDATE_ACTIONS:
        return action
    return SEMANTIC_TO_ACTION.get(semantic_type, "request_human_review")


def feedback_type_for_candidate_action(action: str) -> str:
    return ACTION_TO_FEEDBACK_TYPE.get(str(action or ""), "")


def candidate_action_for_feedback_type(feedback_type: str) -> str:
    return FEEDBACK_TYPE_TO_ACTION.get(str(feedback_type or ""), "request_human_review")


def normalize_candidate_action_proposal(
    parsed: dict[str, Any],
    *,
    fallback: dict[str, Any],
    source: str,
    model: str | None,
    budget: dict[str, Any] | None = None,
) -> dict[str, Any]:
    semantic_type = normalize_candidate_semantic_type(
        str(parsed.get("semantic_type") or parsed.get("intent") or parsed.get("feedback_type") or "")
    )
    proposed_action = normalize_candidate_proposed_action(
        str(parsed.get("proposed_action") or parsed.get("action") or ""),
        semantic_type=semantic_type,
    )
    confidence = _safe_float(parsed.get("confidence"))
    if confidence is None:
        confidence = _safe_float(fallback.get("confidence")) or 0.0
    confidence = max(0.0, min(1.0, float(confidence)))
    extracted_facts = parsed.get("extracted_facts") if isinstance(parsed.get("extracted_facts"), dict) else {}
    notes = parsed.get("notes") if isinstance(parsed.get("notes"), list) else []
    return {
        "source": source,
        "model": model,
        "semantic_type": semantic_type,
        "proposed_action": proposed_action,
        "confidence": confidence,
        "reply_text": str(parsed.get("reply_text") or parsed.get("message_text") or "").strip(),
        "risk_level": str(parsed.get("risk_level") or "low"),
        "reasoning_summary": str(parsed.get("reasoning_summary") or parsed.get("reason") or "").strip(),
        "notes": [str(item) for item in notes[:6]],
        "extracted_facts": extracted_facts,
        "budget": budget,
        "backend_fallback_classification": fallback.get("backend_fallback_classification"),
    }


def _parse_json_object(content: Any) -> dict[str, Any]:
    text = str(content or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
