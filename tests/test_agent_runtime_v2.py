from __future__ import annotations

import json

from mahjong_agent_v2 import AgentRuntimeV2, CustomerProfileV2, InMemoryAgentStoreV2, UserMessageV2
from mahjong_agent_v2.llm import StaticAgentClientV2
from mahjong_agent_v2.tracing import InMemoryTraceRecorderV2


def test_v2_runtime_lets_model_choose_tool_order_and_reply_after_results() -> None:
    store = seeded_store()
    client = StaticAgentClientV2(
        outputs=[
            json.dumps(
                {
                    "goal": "查询是否有现成通宵局",
                    "reasoning_summary": "用户问有没有人，先查当前局。",
                    "reply_to_user": "",
                    "tool_calls": [
                        {
                            "name": "search_current_games",
                            "arguments": {"requirement": {"duration_mode": "overnight"}, "limit": 5},
                        }
                    ],
                    "needs_human": False,
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "goal": "回复当前没有匹配局",
                    "reasoning_summary": "工具返回没有匹配局。",
                    "reply_to_user": "现在没有通宵局，要组一个吗？",
                    "tool_calls": [],
                    "needs_human": False,
                },
                ensure_ascii=False,
            ),
        ],
        calls=[],
    )
    trace = InMemoryTraceRecorderV2()
    runtime = AgentRuntimeV2(llm_client=client, store=store, trace_recorder=trace)

    result = runtime.handle_user_message(message("通宵有人吗"), trace_id="trace_v2_search")

    assert result.final_reply == "现在没有通宵局，要组一个吗？"
    assert [tool.name for tool in result.tool_results] == ["search_current_games"]
    assert len(client.calls) == 2
    assert '"previous_tool_results"' in client.calls[1]["messages"][1]["content"]
    steps = [event.step for event in trace.get_trace("trace_v2_search")]
    assert "llm_prompt" in steps
    assert "llm_response" in steps
    assert "tool_called" in steps
    assert "tool_result" in steps
    assert "final_output" in steps


def test_v2_runtime_creates_game_searches_customers_and_creates_llm_written_drafts() -> None:
    store = seeded_store()
    client = DynamicDraftClient()
    client.outputs.append(
        json.dumps(
            {
                "goal": "帮张哥组通宵1块局",
                "reasoning_summary": "用户已经确认要组局，先建局再找候选人。",
                "reply_to_user": "",
                "tool_calls": [
                    {
                        "name": "create_game",
                        "arguments": {
                            "requirement": {
                                "game_type": "hangzhou_mahjong",
                                "stake": "1",
                                "duration_mode": "overnight",
                                "start_time_mode": "people_ready",
                                "smoke": "any",
                            },
                            "known_players": [
                                {"customer_id": "zhang", "display_name": "张哥", "source": "organizer"}
                            ],
                        },
                    },
                    {
                        "name": "search_customers",
                        "arguments": {
                            "requirement": {
                                "game_type": "hangzhou_mahjong",
                                "stake": "1",
                                "duration_mode": "overnight",
                                "start_time_mode": "people_ready",
                                "smoke": "any",
                            },
                            "exclude_customer_ids": ["zhang"],
                            "limit": 2,
                        },
                    },
                ],
                "needs_human": False,
            },
            ensure_ascii=False,
        )
    )
    client.outputs.append(
        json.dumps(
            {
                "goal": "回复发起人",
                "reasoning_summary": "已经创建待审批邀约草稿。",
                "reply_to_user": "好的，我先帮你问问。",
                "tool_calls": [],
                "needs_human": False,
            },
            ensure_ascii=False,
        )
    )
    trace = InMemoryTraceRecorderV2()
    runtime = AgentRuntimeV2(llm_client=client, store=store, trace_recorder=trace)

    result = runtime.handle_user_message(message("一个人，1块的，通宵，人齐开，烟都可"), trace_id="trace_v2_form")

    assert result.final_reply == "好的，我先帮你问问。"
    assert [tool.name for tool in result.tool_results] == [
        "create_game",
        "search_customers",
        "create_invite_drafts",
    ]
    assert len(store.games) == 1
    assert len(store.invite_drafts) == 1
    draft = next(iter(store.invite_drafts.values()))
    assert draft.message_text == "冉姐，人齐开，1块通宵，打吗？"
    assert result.state_transitions
    assert any(event.step == "state_transition" for event in trace.get_trace("trace_v2_form"))


class DynamicDraftClient:
    def __init__(self) -> None:
        self.outputs: list[str] = []
        self.calls: list[dict] = []

    def complete(self, messages, *, trace_id, timeout_seconds):
        self.calls.append({"messages": messages, "trace_id": trace_id, "timeout_seconds": timeout_seconds})
        if len(self.calls) == 2:
            payload = json.loads(messages[1]["content"])
            game_id = payload["previous_tool_results"][0]["result"]["game"]["game_id"]
            return json.dumps(
                {
                    "goal": "创建候选人邀约草稿",
                    "reasoning_summary": "根据候选人结果生成待审批邀约。",
                    "reply_to_user": "",
                    "tool_calls": [
                        {
                            "name": "create_invite_drafts",
                            "arguments": {
                                "game_id": game_id,
                                "invitations": [
                                    {
                                        "customer_id": "ran",
                                        "display_name": "冉姐",
                                        "message_text": "冉姐，人齐开，1块通宵，打吗？",
                                    }
                                ],
                            },
                        }
                    ],
                    "needs_human": False,
                },
                ensure_ascii=False,
            )
        if not self.outputs:
            raise AssertionError("no fake output")
        return self.outputs.pop(0)


def test_v2_gateway_rejects_invalid_tool_arguments_and_runtime_returns_result_to_model() -> None:
    store = seeded_store()
    client = StaticAgentClientV2(
        outputs=[
            json.dumps(
                {
                    "goal": "尝试建局",
                    "reasoning_summary": "模型误传了非法参数。",
                    "reply_to_user": "",
                    "tool_calls": [{"name": "create_game", "arguments": {"known_players": []}}],
                    "needs_human": False,
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "goal": "修正并追问",
                    "reasoning_summary": "工具返回 schema 错误，不能建局。",
                    "reply_to_user": "我先确认一下，你想打多大的？",
                    "tool_calls": [],
                    "needs_human": False,
                },
                ensure_ascii=False,
            ),
        ],
        calls=[],
    )
    runtime = AgentRuntimeV2(llm_client=client, store=store)

    result = runtime.handle_user_message(message("组"), trace_id="trace_v2_invalid_args")

    assert result.final_reply == "我先确认一下，你想打多大的？"
    assert result.tool_results[0].called is False
    assert result.tool_results[0].allowed is False
    assert "requirement is required" in str(result.tool_results[0].error)
    second_prompt = client.calls[1]["messages"][1]["content"]
    assert "previous_tool_results" in second_prompt
    assert "requirement is required" in second_prompt


def test_v2_runtime_source_does_not_import_legacy_parser_workflow_or_guard() -> None:
    import inspect
    import mahjong_agent_v2.context as context
    import mahjong_agent_v2.runtime as runtime
    import mahjong_agent_v2.tools as tools

    source = "\n".join(
        [
            inspect.getsource(context),
            inspect.getsource(runtime),
            inspect.getsource(tools),
        ]
    )
    assert "mahjong_agent.parser" not in source
    assert "semantic_resolver" not in source
    assert "controlled_workflow" not in source
    assert "reply_guard" not in source


def seeded_store() -> InMemoryAgentStoreV2:
    store = InMemoryAgentStoreV2()
    store.upsert_customer(
        CustomerProfileV2(
            customer_id="zhang",
            display_name="张哥",
            gender="男",
            preferred_games=["hangzhou_mahjong"],
            preferred_stakes=["0.5", "1"],
            smoke_preference="any",
            response_score=0.9,
        )
    )
    store.upsert_customer(
        CustomerProfileV2(
            customer_id="ran",
            display_name="冉姐",
            gender="女",
            preferred_games=["hangzhou_mahjong"],
            preferred_stakes=["1"],
            smoke_preference="any",
            response_score=0.9,
        )
    )
    return store


def message(text: str) -> UserMessageV2:
    return UserMessageV2(
        conversation_id="test_v2",
        sender_id="zhang",
        sender_name="张哥",
        text=text,
    )
