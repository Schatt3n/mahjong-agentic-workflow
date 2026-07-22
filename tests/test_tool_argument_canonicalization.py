from __future__ import annotations

from mahjong_agent_runtime import InMemoryAgentStore, ToolCall, ToolGateway


def test_equivalent_game_search_arguments_share_one_idempotency_key() -> None:
    gateway = ToolGateway(InMemoryAgentStore())
    first = ToolCall(
        name="search_current_games",
        arguments={
            "requirement": {
                "game_type": "hangzhou_mahjong",
                "stake": "1",
                "smoke_preference": "无烟",
            },
            "limit": 5,
        },
        reason="先查当前局",
    )
    repeated = ToolCall(
        name="search_current_games",
        arguments={
            "requirement": {
                "game_type": "hangzhou_mahjong",
                "stake": "1",
                "base_stake": 1.0,
                "stake_label": "1",
                "smoke_preference": "无烟",
            },
            "limit": 5,
        },
        reason="重复确认当前局",
    )

    first_result = gateway.execute(
        first,
        trace_id="trace-first",
        conversation_id="conversation-1",
        sender_id="customer-1",
        sender_name="客户",
        step_index=1,
        source_message_id="message-1",
    )
    repeated_result = gateway.execute(
        repeated,
        trace_id="trace-repeated",
        conversation_id="conversation-1",
        sender_id="customer-1",
        sender_name="客户",
        step_index=2,
        source_message_id="message-1",
    )

    assert first_result.called is True
    assert first_result.deduplicated is False
    assert repeated_result.called is True
    assert repeated_result.deduplicated is True
    assert repeated_result.idempotency_key == first_result.idempotency_key
