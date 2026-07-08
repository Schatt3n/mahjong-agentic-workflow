# Agent Runtime Loop 设计说明

## 核心理念

当前主链路不是传统固定 workflow，也不是放任模型直接改数据库的全自由 agent。它采用“模型决策 + 后端受控执行”的结构：

- 模型负责：理解用户目标、拆解任务、选择工具、根据工具结果调整下一步、生成回复。
- 后端负责：上下文构建、输出合同校验、工具 schema 校验、权限、幂等、顺序、并发、状态机、落库、审计和客户可见文本安全。
- 主 loop 只做编排，不写具体麻将语义 if-else。
- 工具结果必须回喂模型，让模型看到真实系统状态后再继续决策。
- 所有客户可见文本必须经过话术生成和安全审查，包括最终回复和工具参数里的邀约草稿。

## 主流程

```text
handle_user_message
  -> 会话锁、消息幂等、run/version 推进、旧 pending 回复失效
  -> _handle_once
       -> _build_and_trace_context
       -> _call_agent_action
       -> _record_action_contract_feedback  合同错误时回喂模型
       -> _trace_action_plan
       -> _process_tool_action 或 _process_reply_action
       -> 工具结果回喂模型，直到 waiting_user/completed/needs_human 或达到 max_steps
  -> 摘要 checkpoint
  -> 记住消息处理结果，支持重复消息幂等返回
```

## 方法分层

### 入口层

- `handle_user_message`：外层入口，处理并发锁、消息幂等、会话版本、旧输出失效和摘要触发。
- `_handle_once`：主 agent loop，只编排上下文、模型、工具、回复，不承载业务规则。

### 上下文与模型层

- `_fresh_turn_budgets`：为每条用户消息复制独立预算，避免不同消息之间共享计数。
- `_build_and_trace_context`：构建模型上下文，并记录 `context_packed`、`context_built`、`llm_prompt`。
- `_call_agent_action`：调用主模型，记录原始响应，并解析为 `AgentAction`。
- `_record_action_contract_feedback`：当模型输出 JSON 合同不合法时，把错误包装成工具结果回喂模型。
- `_trace_action_plan`：记录模型的目标、计划、状态和工具调用意图，便于回溯。

### 工具执行层

- `_process_tool_action`：处理含工具调用的 action。先处理客户可见文本，再执行工具。
- `_execute_tool_calls`：真正调用 `ToolGateway`，并做跨工具一致性、过期 run 拦截、状态变更记录。
- `_stale_write_tool_result`：当旧 run 被新消息超越时，禁止旧 run 再写状态或草稿。

### 回复层

- `_process_reply_action`：处理最终回复。先话术生成，再内容审查，通过后写入 pending assistant turn。
- `_append_pending_assistant_turn`：保存待外发回复，通道层决定是否真正发送。

### 客户可见文本层

- `_customer_visible_processor`：组装客户可见文本处理器。
- `_run_customer_visible_text_generation`：兼容旧调用的薄封装，实际逻辑在 `visibility.py`。
- `_run_customer_visible_content_review`：兼容旧调用的薄封装，实际逻辑在 `visibility.py`。

## 为什么工具阶段也要审查客户可见文本

工具参数里可能包含候选人邀约草稿，例如：

```json
{
  "name": "create_outbound_message_drafts",
  "arguments": {
    "drafts": [
      {
        "recipient_id": "wang02",
        "message_text": "张哥这边缺人，4点0.5无烟，来不来？"
      }
    ]
  }
}
```

这类文本即使不是当前用户的 `final_reply`，也可能被老板复制或自动外发，所以同样必须审查是否泄露其他客户信息、系统细节、工具执行状态或未发生动作。

## 为什么需要 run_version

用户可能连续发送多条消息，旧流程还没结束，新消息已经补充了条件。`run_version` 用来判断当前流程是否过期：

- 读工具可以继续返回结果。
- 写工具、草稿生成、最终回复必须检查是否过期。
- 过期 run 不允许继续落库，避免旧条件覆盖新条件。

## 为什么合同错误要回喂模型

如果模型输出格式错了，后端不应该猜测它的意图，也不应该直接执行工具。当前设计会把错误作为 `agent_action_contract` 工具结果回喂模型，让模型在下一轮修正 JSON。这比补 if-else 更符合 agent loop 的设计。

## 文件对应关系

- `runtime.py`：主循环和编排。
- `action_contract.py`：主模型输出合同解析与校验。
- `budget.py`：LLM 调用预算。
- `tool_consistency.py`：跨工具参数一致性。
- `visibility.py`：客户可见话术生成与安全审查。
