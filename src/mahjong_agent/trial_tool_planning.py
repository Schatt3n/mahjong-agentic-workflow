from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


TRIAL_TOOL_PLAN_SYSTEM_PROMPT = """你是麻将馆运营工作流的工具规划器。
你不能直接执行工具，只能从后端本轮提供的 available_tools 里选择需要调用的工具，并返回 JSON。
后端会校验权限、参数、状态和风险；高风险工具 send_message 当前只能创建待审批 outbox，不能直接发送真实消息。
如果用户是在问“有没有人打/有没有局/下班有人吗”，通常应先调用 search_current_open_games。
如果用户明确要老板帮忙组局，且关键信息足够，通常应先调用 search_candidate_customers，再调用 send_message 创建待审批邀约草稿。
如果当前 stage 是 after_candidate_search，且候选人搜索已有结果，通常应调用 send_message 创建待审批 outbox。
如果信息不够，不能为了补齐信息而调用候选人搜索或消息发送。
prompt.text_normalization 是后端提供的低风险文本标准化证据，不是业务事实；涉及档位、人数、时间时仍要结合 source_text、customer_profile 和 parsed_game 判断。
如果 source_text 里出现“0。5/0，5/0 5/0、5”等表达，结合客户画像或麻将语境明显是在说档位时，可按 0.5 理解；如果仍不确定，应规划追问而不是硬调用高风险工具。
不要编造工具名，不要编造后端没有给出的 ID。
reasoning_summary 只写一句简短原因，不要输出长篇思维链。
只输出 JSON：
{"tool_calls":[{"tool_name":"search_current_open_games|search_candidate_customers|send_message","arguments":{},"reason":"一句原因"}],"reasoning_summary":"一句话"}"""


@dataclass(slots=True)
class TrialToolPlanPromptInput:
    stage: str
    now: datetime
    sender_id: str
    sender_name: str
    customer_profile: dict[str, Any]
    source_text: str
    effective_text: str
    workflow_followup_context: dict[str, Any]
    text_normalization: dict[str, Any]
    decision_action: str
    parsed_game: dict[str, Any]
    missing_fields: list[str]
    critical_fields: set[str]
    available_tools: list[dict[str, Any]]
    tool_registry_version: str
    existing_tool_results: dict[str, Any] = field(default_factory=dict)
    active_skills: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class TrialToolPlanPromptBuilder:
    """Builds the legacy trial-page LLM tool-planning prompt contract."""

    system_prompt: str = TRIAL_TOOL_PLAN_SYSTEM_PROMPT

    def build_prompt(self, data: TrialToolPlanPromptInput) -> dict[str, Any]:
        return {
            "stage": data.stage,
            "now": data.now.strftime("%Y-%m-%d %H:%M:%S"),
            "sender": {"id": data.sender_id, "name": data.sender_name},
            "customer_profile": data.customer_profile,
            "source_text": data.source_text,
            "effective_text": data.effective_text,
            "workflow_followup_context": data.workflow_followup_context or {},
            "text_normalization": data.text_normalization,
            "decision_action": data.decision_action,
            "parsed_game": data.parsed_game,
            "missing_fields": data.missing_fields,
            "critical_missing_fields": sorted(set(data.missing_fields) & data.critical_fields),
            "available_tools": data.available_tools,
            "tool_registry_version": data.tool_registry_version,
            "existing_tool_results": data.existing_tool_results,
            "active_skills": data.active_skills,
            "rules": [
                "工具调用由 LLM 提议，真实执行由后端 ToolGateway 校验。",
                "先参考 active_skills 中的运营经验，再选择工具；skill 不能覆盖后端权限和参数校验。",
                "search_current_open_games 是只读当前局池搜索。",
                "search_candidate_customers 是只读客户画像候选人搜索。",
                "send_message 是高风险工具，本系统只允许 create_pending_outbox，不允许直接外发。",
                "如果 critical_missing_fields 非空，不要调用 search_candidate_customers 或 send_message。",
                "如果 workflow_followup_context 表明当前用户是在确认上一轮“要组一个吗”，则按模型语义和后端状态机继续，不要把当前短回复当成孤立消息。",
            ],
        }

    def build_payload(
        self,
        data: TrialToolPlanPromptInput,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        thinking_enabled: bool | None = None,
        response_format: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": json.dumps(self.build_prompt(data), ensure_ascii=False)},
            ],
        }
        if thinking_enabled is not None:
            payload["thinking"] = {"type": "enabled" if thinking_enabled else "disabled"}
        if response_format:
            payload["response_format"] = {"type": response_format}
        return payload


@dataclass(slots=True)
class TrialToolCallNormalizer:
    """Normalizes LLM-proposed tool calls before backend validation."""

    default_send_message_mode: str = "create_pending_outbox"
    default_reason: str = "LLM 请求调用工具。"
    max_reason_chars: int = 240

    def normalize(self, raw_calls: Any, available_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        available = {str(item.get("name")): item for item in available_tools}
        if not isinstance(raw_calls, list):
            return []
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw_calls:
            if not isinstance(item, dict):
                continue
            name = str(item.get("tool_name") or item.get("name") or "").strip()
            if name not in available or name in seen:
                continue
            args = item.get("arguments")
            if not isinstance(args, dict):
                args = {}
            else:
                args = dict(args)
            if name == "send_message":
                args = self._normalize_send_message_arguments(args, available.get(name) or {})
            normalized.append(
                {
                    "tool_name": name,
                    "arguments": args,
                    "reason": str(item.get("reason") or item.get("call_reason") or self.default_reason)[
                        : self.max_reason_chars
                    ],
                    "requested_by": "llm",
                }
            )
            seen.add(name)
        return normalized

    def _normalize_send_message_arguments(self, args: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
        allowed_modes = list(spec.get("allowed_execution_modes") or [self.default_send_message_mode])
        allowed_mode = str(allowed_modes[0] if allowed_modes else self.default_send_message_mode)
        requested_execution_mode = args.get("execution_mode")
        if requested_execution_mode and requested_execution_mode != allowed_mode:
            args["requested_execution_mode"] = requested_execution_mode
        args["execution_mode"] = allowed_mode
        return args


ToolPolicyResolver = Callable[[str, str], dict[str, Any]]
ToolSpecResolver = Callable[[str, str], dict[str, Any] | None]
StageToolSpecsResolver = Callable[[str], list[dict[str, Any]]]
RuntimePolicyGetter = Callable[[], dict[str, Any]]
RuntimePolicyValidator = Callable[..., dict[str, Any] | None]
TrustedActionProposer = Callable[..., bool]


@dataclass(slots=True)
class TrialToolActionProposalFactory:
    """Wraps normalized tool calls into auditable controlled-action proposals."""

    protocol_version: str
    tool_policy: ToolPolicyResolver
    default_reason: str = "请求调用工具。"
    max_reason_chars: int = 240

    def build(
        self,
        *,
        call: dict[str, Any],
        index: int,
        stage: str,
        source: str,
        trace_id: str,
        now: datetime,
    ) -> dict[str, Any]:
        tool_name = str(call.get("tool_name") or "").strip()
        args = call.get("arguments")
        if not isinstance(args, dict):
            args = {}
        else:
            args = dict(args)
        policy = self.tool_policy(tool_name, stage)
        action_hash = self._action_hash(
            trace_id=trace_id,
            stage=stage,
            tool_name=tool_name,
            index=index,
            arguments=args,
        )
        return {
            "action_id": f"act_{action_hash}",
            "idempotency_key": f"{trace_id}:{stage}:{tool_name}:{action_hash}",
            "protocol": self.protocol_version,
            "stage": stage,
            "tool_name": tool_name,
            "arguments": args,
            "proposed_by": str(call.get("requested_by") or source or "unknown"),
            "source": source,
            "reason": str(call.get("reason") or self.default_reason)[: self.max_reason_chars],
            "risk_level": policy.get("risk_level", "unknown"),
            "side_effect": bool(policy.get("side_effect")),
            "approval_required": bool(policy.get("approval_required")),
            "created_at": now.isoformat(),
        }

    def _action_hash(
        self,
        *,
        trace_id: str,
        stage: str,
        tool_name: str,
        index: int,
        arguments: dict[str, Any],
    ) -> str:
        stable_payload = json.dumps(
            {
                "trace_id": trace_id,
                "stage": stage,
                "tool_name": tool_name,
                "index": index,
                "arguments": arguments,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(stable_payload.encode("utf-8")).hexdigest()[:16]


@dataclass(slots=True)
class TrialToolActionValidator:
    """Validates trial tool action proposals before any tool gateway execution."""

    critical_fields: set[str]
    tool_spec_for_stage: ToolSpecResolver
    tool_specs_for_stage: StageToolSpecsResolver
    runtime_policy_getter: RuntimePolicyGetter
    runtime_policy_validation_override: RuntimePolicyValidator
    trusted_action_proposer: TrustedActionProposer

    def validate(
        self,
        *,
        proposal: dict[str, Any],
        game: Any | None,
        missing_fields: list[str],
        tool_results: dict[str, Any],
    ) -> dict[str, Any]:
        tool_name = str(proposal.get("tool_name") or "")
        stage = str(proposal.get("stage") or "")
        args = proposal.get("arguments") if isinstance(proposal.get("arguments"), dict) else {}
        spec = self.tool_spec_for_stage(tool_name, stage)
        available = {str(item.get("name")) for item in self.tool_specs_for_stage(stage)}
        critical_missing = sorted(set(missing_fields) & self.critical_fields)
        notes: list[str] = []

        if tool_name not in available or spec is None:
            return {
                "allowed": False,
                "reason": f"{tool_name or 'unknown'} 不在当前阶段可用工具列表内。",
                "code": "tool_not_available_for_stage",
                "effective_arguments": {},
            }
        if tool_name in {"search_candidate_customers", "send_message"} and game is None:
            return {
                "allowed": False,
                "reason": "当前没有可操作的组局对象，拒绝执行该工具。",
                "code": "missing_game_context",
                "effective_arguments": {},
            }
        if tool_name in {"search_candidate_customers", "send_message"} and critical_missing:
            return {
                "allowed": False,
                "reason": "组局关键信息不足，拒绝搜索候选人或创建外发草稿。",
                "code": "critical_slots_missing",
                "missing_fields": critical_missing,
                "effective_arguments": {},
            }

        runtime_policy = self.runtime_policy_getter()
        if bool(proposal.get("side_effect")) and runtime_policy.get("llm_required_for_side_effect_tools"):
            proposer = str(proposal.get("proposed_by") or proposal.get("source") or "").strip()
            source = str(proposal.get("source") or "").strip()
            if not self.trusted_action_proposer(proposer, source):
                return {
                    "allowed": False,
                    "reason": "当前生产策略要求副作用工具必须由 LLM 或人工明确提案，拒绝后端兜底写入。",
                    "code": "runtime_policy_llm_required_for_side_effect_tool",
                    "runtime_policy": runtime_policy,
                    "effective_arguments": {},
                }

        effective_arguments, stripped_arguments = self._effective_arguments(args, spec)
        if stripped_arguments:
            notes.append(f"已剔除未注册参数：{', '.join(stripped_arguments)}。")
        if tool_name == "send_message":
            send_verdict = self._validate_send_message_arguments(
                args=args,
                spec=spec,
                stage=stage,
                tool_results=tool_results,
                effective_arguments=effective_arguments,
                notes=notes,
            )
            if send_verdict:
                return send_verdict

        allowed_verdict = {
            "allowed": True,
            "reason": "动作通过后端状态、权限和风险校验。",
            "code": "allowed",
            "effective_arguments": effective_arguments,
            "notes": notes,
        }
        policy_verdict = self.runtime_policy_validation_override(
            stage=stage,
            action_name=tool_name,
            side_effect=bool(proposal.get("side_effect")),
            approval_required=bool(proposal.get("approval_required")),
        )
        if policy_verdict:
            original_notes = [str(item) for item in allowed_verdict.get("notes") or []]
            return {
                **allowed_verdict,
                **policy_verdict,
                "effective_arguments": effective_arguments,
                "notes": original_notes + [str(item) for item in policy_verdict.get("notes") or []],
            }
        return allowed_verdict

    def _effective_arguments(
        self,
        args: dict[str, Any],
        spec: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        schema = spec.get("arguments_schema") if isinstance(spec.get("arguments_schema"), dict) else {}
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        allowed_arg_names = set(properties)
        effective_arguments = {
            key: value
            for key, value in dict(args).items()
            if key in allowed_arg_names or key == "requested_execution_mode"
        }
        stripped_arguments = sorted(
            key for key in dict(args) if key not in allowed_arg_names and key != "requested_execution_mode"
        )
        return effective_arguments, stripped_arguments

    def _validate_send_message_arguments(
        self,
        *,
        args: dict[str, Any],
        spec: dict[str, Any],
        stage: str,
        tool_results: dict[str, Any],
        effective_arguments: dict[str, Any],
        notes: list[str],
    ) -> dict[str, Any] | None:
        allowed_modes = list(spec.get("allowed_execution_modes") or [])
        allowed_mode = str(allowed_modes[0] if allowed_modes else "create_pending_outbox")
        requested_mode = str(args.get("requested_execution_mode") or args.get("execution_mode") or "")
        if requested_mode and requested_mode != allowed_mode:
            notes.append(f"模型请求 {requested_mode} 已被降级为 {allowed_mode}。")
        effective_arguments["execution_mode"] = allowed_mode
        candidate_result = tool_results.get("search_candidate_customers") if isinstance(tool_results, dict) else {}
        if stage == "after_candidate_search" and int((candidate_result or {}).get("result_count") or 0) <= 0:
            return {
                "allowed": False,
                "reason": "没有候选人搜索结果，拒绝创建待审批消息。",
                "code": "no_candidate_result",
                "effective_arguments": effective_arguments,
            }
        if stage == "organizer_followup_draft":
            notes.append("send_message 是高风险动作，只允许创建待审批 followup，禁止直接发送。")
        else:
            notes.append("send_message 是高风险动作，只允许创建待审批 outbox，禁止直接发送。")
        return None
