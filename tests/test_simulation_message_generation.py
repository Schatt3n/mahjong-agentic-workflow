from __future__ import annotations

import json
from pathlib import Path

from tests.simulation.behavior_policy import (
    DIALOG_PHASE_BUSINESS,
    BehaviorPolicy,
    MessageGenerationRequest,
    MessageGenerationResult,
)
from tests.simulation.message_generation import (
    GLMSimulationMessageGenerator,
    SimulationGeneratorConfig,
)
from tests.simulation.real_group_case_library import RealGroupCaseLibrary
from tests.simulation.sim_factory import VirtualUser


class FakeCompletionClient:
    def __init__(self, output: str | Exception) -> None:
        self.output = output
        self.calls: list[dict] = []

    def complete(self, messages, *, trace_id: str, timeout_seconds: float) -> str:
        self.calls.append(
            {
                "messages": messages,
                "trace_id": trace_id,
                "timeout_seconds": timeout_seconds,
            }
        )
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


def _request() -> MessageGenerationRequest:
    return MessageGenerationRequest(
        sender_id="sim_user_081",
        sender_name="王哥",
        persona="active_gambler",
        preferred_game="sichuan_mahjong",
        channel="group",
        conversation_id="sim:group:sim_group_001",
        turn_count=1,
        last_agent_reply="你这边几个人？",
        fallback_text="我一个人",
        is_follow_up=True,
        dialog_phase=DIALOG_PHASE_BUSINESS,
        business_anchor="帮我约个川麻局",
    )


def test_glm_generator_returns_contract_text_and_audit_metadata() -> None:
    client = FakeCompletionClient(json.dumps({"text": "就我一个"}, ensure_ascii=False))
    generator = GLMSimulationMessageGenerator(
        client,
        config=SimulationGeneratorConfig(model="glm-4.7-flash", timeout_seconds=7),
    )

    result = generator.generate(_request())

    assert result.text == "就我一个"
    assert result.source == "glm"
    assert result.model == "glm-4.7-flash"
    assert result.trace_id.startswith("trace_sim_gen_")
    assert result.latency_ms is not None
    assert result.error is None
    assert result.reference_case_ids
    assert client.calls[0]["timeout_seconds"] == 7
    prompt_payload = json.loads(client.calls[0]["messages"][1]["content"])
    assert prompt_payload["last_agent_reply"] == "你这边几个人？"
    assert prompt_payload["fallback_text"] == "我一个人"
    assert prompt_payload["dialog_phase"] == DIALOG_PHASE_BUSINESS
    assert prompt_payload["business_anchor"] == "帮我约个川麻局"
    assert {
        item["case_id"] for item in prompt_payload["real_group_chat_references"]
    } == set(result.reference_case_ids)


def test_real_case_library_only_loads_anonymized_approved_gold(tmp_path: Path) -> None:
    dataset = tmp_path / "real_cases.jsonl"
    records = [
        {
            "id": "approved_query",
            "case_type": "member_query",
            "quality_tier": "gold",
            "review_status": "approved",
            "source": {"anonymized": True, "source_refs": ["must-not-enter-prompt"]},
            "tags": ["real_group_chat", "query"],
            "messages": [
                {"role": "customer", "content_type": "text", "text": "1块杭麻有人吗"}
            ],
            "expected": {"intent": "query", "search_requirement": {"stake": "1"}},
        },
        {
            "id": "not_reviewed",
            "case_type": "member_query",
            "quality_tier": "gold",
            "review_status": "pending",
            "source": {"anonymized": True},
            "messages": [{"role": "customer", "content_type": "text", "text": "不该进入"}],
        },
        {
            "id": "not_anonymized",
            "case_type": "member_query",
            "quality_tier": "gold",
            "review_status": "approved",
            "source": {"anonymized": False},
            "messages": [{"role": "customer", "content_type": "text", "text": "也不该进入"}],
        },
    ]
    dataset.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n",
        encoding="utf-8",
    )

    library = RealGroupCaseLibrary.from_jsonl(dataset)

    assert [item.case_id for item in library.examples] == ["approved_query"]
    payload = library.examples[0].to_prompt_payload()
    assert payload["turns"][0]["text"] == "1块杭麻有人吗"
    assert "source" not in payload
    assert "source_refs" not in json.dumps(payload, ensure_ascii=False)


def test_glm_group_prompt_uses_real_cases_and_records_provenance(tmp_path: Path) -> None:
    dataset = tmp_path / "real_cases.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "real_fragment",
                "case_type": "fragmented_input",
                "quality_tier": "gold",
                "review_status": "approved",
                "source": {"anonymized": True},
                "tags": ["fragmented_input", "constraint_relaxation"],
                "messages": [
                    {"role": "customer", "content_type": "text", "text": "现在一块无烟还有嘛"},
                    {"role": "customer", "content_type": "text", "text": "0.5无烟也可以"},
                ],
                "expected": {"intent": "query", "same_session": True},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    client = FakeCompletionClient(json.dumps({"text": "五毛无烟也行"}, ensure_ascii=False))
    generator = GLMSimulationMessageGenerator(
        client,
        config=SimulationGeneratorConfig(
            model="glm-4.7-flash",
            timeout_seconds=7,
            real_case_dataset_path=dataset,
        ),
        case_library=RealGroupCaseLibrary.from_jsonl(dataset),
    )

    result = generator.generate(_request())

    assert result.reference_case_ids == ("real_fragment",)
    prompt_payload = json.loads(client.calls[0]["messages"][1]["content"])
    assert prompt_payload["real_group_chat_references"][0]["case_id"] == "real_fragment"
    assert prompt_payload["real_group_chat_references"][0]["turns"][1]["text"] == "0.5无烟也可以"
    assert "请模仿表达习惯但不要逐字复制" in client.calls[0]["messages"][0]["content"]


def test_real_group_examples_are_not_injected_into_private_or_chitchat_turns(tmp_path: Path) -> None:
    dataset = tmp_path / "real_cases.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "real_query",
                "case_type": "member_query",
                "quality_tier": "gold",
                "review_status": "approved",
                "source": {"anonymized": True},
                "messages": [{"role": "customer", "content_type": "text", "text": "1块有人吗"}],
                "expected": {"intent": "query"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    library = RealGroupCaseLibrary.from_jsonl(dataset)

    private_refs = library.select_for_generation(
        channel="private",
        fallback_text="一块有人吗",
        dialog_phase="business",
        is_follow_up=False,
        seed_material="private",
    )
    chitchat_refs = library.select_for_generation(
        channel="group",
        fallback_text="今天也太热了",
        dialog_phase="chitchat",
        is_follow_up=False,
        seed_material="chitchat",
    )

    assert private_refs == ()
    assert chitchat_refs == ()


def test_glm_generator_falls_back_without_breaking_simulation() -> None:
    client = FakeCompletionClient("not-json")
    generator = GLMSimulationMessageGenerator(
        client,
        config=SimulationGeneratorConfig(model="glm-4.7-flash"),
    )

    result = generator.generate(_request())

    assert result.text == "我一个人"
    assert result.source == "rule_fallback"
    assert result.model == "glm-4.7-flash"
    assert "ValueError" in str(result.error)


def test_behavior_policy_only_calls_generator_when_action_is_dispatched() -> None:
    class CountingGenerator:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, request: MessageGenerationRequest) -> MessageGenerationResult:
            self.calls += 1
            return MessageGenerationResult(
                text=f"模型生成：{request.fallback_text}",
                source="glm",
                model="glm-4.7-flash",
                trace_id="trace_lazy_generation",
            )

    user = VirtualUser(
        customer_id="sim_user_081",
        display_name="王哥",
        balance=100,
        preferred_game="sichuan_mahjong",
        persona="active_gambler",
    )
    generator = CountingGenerator()
    policy = BehaviorPolicy([user], seed=7, message_generator=generator)

    scheduled = policy.first_action(user, sequence=1)

    assert scheduled is not None
    assert generator.calls == 0
    dispatched = policy.materialize_action(scheduled, user=user)
    assert generator.calls == 1
    assert dispatched.generation_source == "glm"
    assert dispatched.text.startswith("模型生成：")
