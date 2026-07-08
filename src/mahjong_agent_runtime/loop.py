from __future__ import annotations

"""The thin goal-driven agent loop."""

from dataclasses import dataclass
from typing import Any

from .budget import TokenBudget
from .hooks import HookManager
from .lifecycle import ContextLifecycleManager
from .models import AgentRuntimeResult, StateTransition, ToolResult, UserMessage
from .processing import ActionProcessor
from .runtime_components import TurnBudgets
from .store import InMemoryAgentStore


@dataclass(slots=True)
class AgentLoop:
    """Run buildContext -> callLLM -> executeTools/appendResults until terminal."""

    store: InMemoryAgentStore
    trace_recorder: Any
    context_lifecycle: ContextLifecycleManager
    action_processor: ActionProcessor
    token_budget: TokenBudget
    review_token_budget: TokenBudget
    text_generation_token_budget: TokenBudget
    max_steps: int = 8
    hook_manager: HookManager | None = None

    def run(self, message: UserMessage, *, trace_id: str, run_id: str, run_version: int) -> AgentRuntimeResult:
        budgets = self.fresh_turn_budgets()
        self.store.append_user_turn(message, trace_id)
        self.trace_recorder.record(trace_id, "user_input", {"message": message.to_dict()})
        self._emit("after_user_turn_appended", trace_id=trace_id, payload={"message": message.to_dict()})

        actions = []
        tool_results: list[ToolResult] = []
        pending_tool_results: list[ToolResult] = []
        pre_model_transitions: list[StateTransition] = []
        final_reply = ""

        for step_index in range(1, self.max_steps + 1):
            built = self.context_lifecycle.build_and_trace_context(
                message,
                trace_id=trace_id,
                pending_tool_results=pending_tool_results,
                run_id=run_id,
                run_version=run_version,
                step_index=step_index,
            )
            built, summary_transition = self.context_lifecycle.summarize_and_rebuild_context_if_needed(
                message,
                built=built,
                trace_id=trace_id,
                pending_tool_results=pending_tool_results,
                run_id=run_id,
                run_version=run_version,
                step_index=step_index,
                budget=budgets.agent,
            )
            if summary_transition is not None:
                pre_model_transitions.append(summary_transition)

            model_step = self.action_processor.call_agent_action(
                message,
                trace_id=trace_id,
                built_messages=built.messages,
                step_index=step_index,
                budget=budgets.agent,
                run_id=run_id,
                run_version=run_version,
            )
            if model_step.stop_loop:
                final_reply = model_step.final_reply or ""
                break

            action = model_step.action
            if action is None:
                final_reply = "这个我先转人工确认一下。"
                break
            actions.append(action)

            if model_step.errors:
                pending_tool_results = self.action_processor.record_action_contract_feedback(
                    message,
                    trace_id=trace_id,
                    raw_response=model_step.raw_response,
                    errors=model_step.errors,
                    step_index=step_index,
                )
                continue

            self.action_processor.trace_action_plan(
                action,
                trace_id=trace_id,
                step_index=step_index,
                previous_tool_result_count=len(pending_tool_results),
            )
            processed = self.action_processor.process_action(
                action,
                message=message,
                trace_id=trace_id,
                context_payload=built.payload,
                previous_pending_tool_results=pending_tool_results,
                step_index=step_index,
                budgets=budgets,
                run_id=run_id,
                run_version=run_version,
            )
            actions[-1] = processed.action
            tool_results.extend(processed.tool_results)
            pending_tool_results = processed.pending_tool_results
            if processed.stop_loop:
                final_reply = processed.final_reply or ""
                break
            if processed.continue_loop:
                continue
        else:
            final_reply = "这个我先转人工确认一下。"
            self.action_processor.append_pending_assistant_turn(
                message.conversation_id,
                final_reply,
                trace_id,
                run_id=run_id,
                run_version=run_version,
            )
            self.trace_recorder.record(
                trace_id,
                "final_output",
                {"reply": final_reply, "reason": "max_steps_exceeded"},
                level="WARN",
            )

        transitions = pre_model_transitions + [
            transition
            for result in tool_results
            if not result.deduplicated
            for transition in result.state_transitions
        ]
        return AgentRuntimeResult(
            trace_id=trace_id,
            conversation_id=message.conversation_id,
            final_reply=final_reply,
            actions=actions,
            tool_results=tool_results,
            state_transitions=transitions,
        )

    def fresh_turn_budgets(self) -> TurnBudgets:
        return TurnBudgets(
            agent=TokenBudget(
                max_tokens_per_call=self.token_budget.max_tokens_per_call,
                max_calls_per_turn=self.token_budget.max_calls_per_turn,
            ),
            review=TokenBudget(
                max_tokens_per_call=self.review_token_budget.max_tokens_per_call,
                max_calls_per_turn=self.review_token_budget.max_calls_per_turn,
            ),
            text_generation=TokenBudget(
                max_tokens_per_call=self.text_generation_token_budget.max_tokens_per_call,
                max_calls_per_turn=self.text_generation_token_budget.max_calls_per_turn,
            ),
        )

    def _emit(self, event_name: str, *, trace_id: str, payload: dict[str, Any]) -> None:
        if self.hook_manager is not None:
            self.hook_manager.emit(event_name, trace_id=trace_id, payload=payload)

