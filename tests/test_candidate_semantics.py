from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from mahjong_agent.budget import LLMBudgetManager
from mahjong_agent.candidate_semantics import (
    CandidateSemanticProposalAdapter,
    CandidateSemanticResolverService,
    candidate_action_for_feedback_type,
    feedback_type_for_candidate_action,
    normalize_candidate_proposed_action,
    normalize_candidate_semantic_type,
)
from mahjong_agent.llm import LLMConfig


TZ = ZoneInfo("Asia/Shanghai")


def fallback_contract(text: str, outbox_item: dict, game: dict | None) -> dict:
    return {
        "source": "rules",
        "semantic_type": "accepted",
        "proposed_action": "mark_candidate_confirmed",
        "confidence": 0.65,
        "reply_text": "",
        "reasoning_summary": "fallback",
        "notes": [],
        "backend_fallback_classification": {
            "intent": "accepted",
            "feedback_type": "accepted",
            "status": "已确认",
        },
        "outbox_id": outbox_item.get("id"),
    }


def candidate_classifier(text: str, game: dict | None) -> dict:
    return {
        "intent": "accepted",
        "feedback_type": "accepted",
        "status": "已确认",
    }


def test_candidate_semantic_adapter_returns_llm_contract_with_fallback() -> None:
    calls: dict[str, object] = {}

    def llm_contract(**kwargs):
        calls["kwargs"] = kwargs
        return {
            **kwargs["fallback"],
            "source": "llm",
            "model": "test-model",
            "confidence": 0.93,
            "reply_text": "好的，加你272了。",
        }

    adapter = CandidateSemanticProposalAdapter(
        fallback_proposal_factory=fallback_contract,
        llm_proposal_factory=llm_contract,
    )

    result = adapter.propose(
        trace_id="trace_1",
        candidate_text="可以",
        outbox_item={"id": "outbox_1"},
        game={"id": "game_1"},
        now=datetime(2026, 7, 1, 18, 0, tzinfo=TZ),
    )

    assert result.proposal["source"] == "llm"
    assert result.proposal["model"] == "test-model"
    assert result.fallback["source"] == "rules"
    assert calls["kwargs"]["fallback"] == result.fallback


def test_candidate_semantic_adapter_degrades_to_fallback_on_llm_error() -> None:
    def broken_llm(**kwargs):
        raise TimeoutError("slow")

    adapter = CandidateSemanticProposalAdapter(
        fallback_proposal_factory=fallback_contract,
        llm_proposal_factory=broken_llm,
    )

    result = adapter.propose(
        trace_id="trace_1",
        candidate_text="可以",
        outbox_item={"id": "outbox_1"},
        game={"id": "game_1"},
        now=datetime(2026, 7, 1, 18, 0, tzinfo=TZ),
    )

    assert result.proposal["source"] == "rules"
    assert result.proposal["semantic_type"] == "accepted"
    assert "TimeoutError" in result.proposal["reasoning_summary"]
    assert result.proposal["notes"]


def test_candidate_semantic_adapter_degrades_to_fallback_on_invalid_llm_contract() -> None:
    adapter = CandidateSemanticProposalAdapter(
        fallback_proposal_factory=fallback_contract,
        llm_proposal_factory=lambda **kwargs: "ok",  # type: ignore[return-value]
    )

    result = adapter.propose(
        trace_id="trace_1",
        candidate_text="可以",
        outbox_item={"id": "outbox_1"},
        game={"id": "game_1"},
        now=datetime(2026, 7, 1, 18, 0, tzinfo=TZ),
    )

    assert result.proposal["source"] == "rules"
    assert "expected dict" in result.proposal["reasoning_summary"]


def test_candidate_contract_normalizes_model_aliases() -> None:
    assert normalize_candidate_semantic_type("candidate-accept") == "accepted"
    assert normalize_candidate_semantic_type("do not disturb") == "do_not_disturb"
    assert normalize_candidate_semantic_type("unknown thing") == "uncertain"
    assert normalize_candidate_proposed_action(
        "confirm candidate",
        semantic_type="accepted",
    ) == "mark_candidate_confirmed"
    assert normalize_candidate_proposed_action(
        "",
        semantic_type="candidate_negotiation",
    ) == "start_negotiation"
    assert feedback_type_for_candidate_action("mark_candidate_confirmed") == "accepted"
    assert feedback_type_for_candidate_action("missing") == ""
    assert candidate_action_for_feedback_type("candidate_question") == "answer_candidate_question"
    assert candidate_action_for_feedback_type("missing") == "request_human_review"


def test_candidate_semantic_resolver_builds_fallback_contract() -> None:
    service = CandidateSemanticResolverService(fallback_classifier=candidate_classifier)

    proposal = service.fallback_proposal("可以", {"id": "outbox_1"}, {"id": "game_1"})

    assert proposal["source"] == "rules"
    assert proposal["semantic_type"] == "accepted"
    assert proposal["proposed_action"] == "mark_candidate_confirmed"
    assert proposal["backend_fallback_classification"]["status"] == "已确认"
    assert proposal["outbox_id"] == "outbox_1"


def test_candidate_semantic_resolver_context_includes_profile_and_progress_preview() -> None:
    service = CandidateSemanticResolverService(
        fallback_classifier=candidate_classifier,
        customer_lookup=lambda customer_id: {
            "gender": "female",
            "preferred_games": ["杭麻"],
            "preferred_levels": ["0.5"],
            "smoke_preference": "no_smoke",
            "notes": "下午常来",
        },
        confirmed_count_provider=lambda game: 1,
    )

    context = service.action_context(
        candidate_text="可以",
        outbox_item={
            "id": "outbox_1",
            "game_id": "game_1",
            "customer_id": "ran",
            "customer_name": "冉姐",
            "status": "已发送",
            "message_text": "冉姐，14:00，0.5无烟，打吗？",
        },
        game={
            "id": "game_1",
            "status": "邀约中",
            "parsed": {
                "summary": "杭麻 0.5 14:00 缺3 无烟",
                "start_time": "14:00",
                "level": "0.5",
                "duration_hours": 4,
                "current_player_count": 1,
                "missing_count": 3,
                "rules": ["杭麻", "无烟"],
            },
            "outbox": [{"customer_name": "刘姐", "status": "已确认"}],
        },
        now=datetime(2026, 7, 1, 14, 0, tzinfo=TZ),
    )

    assert context["candidate"]["profile"]["preferred_games"] == ["杭麻"]
    assert context["game_state"]["confirmed_before"] == 1
    assert context["state_preview"]["if_confirmed"]["progress_label_after"] == "371"
    assert context["state_preview"]["if_confirmed"]["fallback_reply"] == "好的，加你371了。"


def test_candidate_semantic_resolver_calls_llm_and_normalizes_contract() -> None:
    captured: list[dict] = []
    audits: list[tuple[str, str, dict]] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            content = {
                "semantic_type": "negotiation",
                "proposed_action": "",
                "confidence": 1.2,
                "reply_text": "可以，我问下这桌其他人能不能打6小时。",
                "risk_level": "low",
                "reasoning_summary": "候选人提出新时长。",
                "extracted_facts": {"requested_duration_hours": 6},
                "notes": ["ok"],
            }
            return json.dumps(
                {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100},
                },
                ensure_ascii=False,
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse()

    service = CandidateSemanticResolverService(
        fallback_classifier=candidate_classifier,
        llm_config=LLMConfig("test-key", "test-model", "https://example.invalid/v1", "openai", 3.0, 0.1, 260),
        budget_manager=LLMBudgetManager(),
        audit_logger=lambda trace_id, event, payload: audits.append((trace_id, event, payload)),
        urlopen=fake_urlopen,
    )
    fallback = service.fallback_proposal("可以但要六小时", {"id": "outbox_1"}, None)

    proposal = service.llm_proposal(
        trace_id="trace_1",
        candidate_text="可以但要六小时",
        outbox_item={"id": "outbox_1", "customer_id": "ran", "customer_name": "冉姐"},
        game=None,
        fallback=fallback,
        now=datetime(2026, 7, 1, 14, 0, tzinfo=TZ),
    )

    assert captured
    assert "候选人回复的语义解析器" in captured[0]["messages"][0]["content"]
    assert proposal["source"] == "llm"
    assert proposal["model"] == "test-model"
    assert proposal["semantic_type"] == "candidate_negotiation"
    assert proposal["proposed_action"] == "start_negotiation"
    assert proposal["confidence"] == 1.0
    assert proposal["extracted_facts"] == {"requested_duration_hours": 6}
    assert [event for _, event, _ in audits] == ["llm_request", "llm_response", "llm_parsed"]
