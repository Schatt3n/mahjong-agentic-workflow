# 群聊/私聊参与意向关联设计（未实现）

## 状态

**未实现，等待真实样本、评测集和方案评审后开发。**

当前 WeChaty 只观察群已经能够接收真实消息，并使用模型判断消息是否属于麻将运营业务，但尚未实现：Agent 作为老板发布局信息后，将用户在群聊或私聊中的参与表达关联到正确的局，再完成好友关系检查、私聊确认和参与状态推进。

## 业务场景

Agent 在微信群发布：

```text
杭麻1块 371 无烟 人齐开
川麻1-32 371 换三张
```

随后可能出现：

1. 用户在群里回复：“川麻那个我可以”。
2. 用户看到群消息后，私聊 Agent：“川麻那个我可以”。
3. 用户只回复“我来”或“可以”，但当前存在多个可参与的局。
4. 用户不是 Agent 好友，无法直接进入私聊确认。
5. 用户加好友后，需要恢复此前未完成的确认任务，不能要求用户重新描述全部条件。

## 核心原则

- `room_id` 和 `conversation_id` 只表示通信上下文，不等于具体业务局。
- 群聊与私聊保持原始上下文隔离，通过 `customer_id + game_id + join_request_id` 推进同一业务任务。
- 用户表达兴趣后不能直接计入已确认人数，必须经过局状态、好友关系、缺失信息和座位并发校验。
- 低置信度或存在多个候选局时不得猜测，应向用户追问。
- 已满、已取消、已过期的发布记录不得继续接受参与。
- 不通过新增大量业务 `if-else` 处理引用歧义，应使用发布台账、候选召回、结构化语义判断和状态机共同完成。

## 建议设计

### 1. Agent 发布台账

Agent 每次向微信群发布局信息后，保存通道返回的消息 ID，并将一条消息中的每个局独立关联到 `game_id`：

```text
publication_id
channel_message_id
room_id
published_at
publication_items[]
  - item_id
  - game_id
  - rendered_text
  - item_position
  - valid_until
```

即使多个局合并在一条微信消息中，也必须拥有不同的 `publication_item`。

### 2. 跨通道局引用解析

收到“川麻那个我可以”后，从以下范围召回候选局：

- 当前群最近由 Agent 发布且仍有效的局；
- 用户与 Agent 共同群聊中的近期有效发布；
- Agent 最近私聊邀请过该用户的局；
- 用户当前正在协商的局。

关联证据优先级：

1. 微信引用消息 ID；
2. 邀约记录中的 `game_id`；
3. 明确的玩法、档位、时间、烟况等条件；
4. 用户近期参与任务与发布时间；
5. 模型语义推断。

如果存在多个候选局，Agent 应使用能够区分候选项的最少问题追问，例如：

```text
你说的是人齐开的1-32，还是六点的2-16？
```

在用户确认前不得推进局状态。

### 3. 好友关系与渠道身份

群成员身份和私聊联系人身份需要映射到统一客户：

```text
customer_id
wechat_contact_id
wechat_room_member_id
friend_status
```

好友状态至少包括：

- `UNKNOWN`
- `NOT_FRIEND`
- `FRIEND_REQUESTED`
- `FRIEND`
- `BLOCKED`

非好友用户先创建待处理 `join_request`。好友关系建立后，按 `join_request_id` 恢复私聊确认，不重新理解整段群聊。

### 4. 参与状态

```text
INTERESTED
WAITING_FRIEND
CONFIRMING_DETAILS
SEAT_HELD
CONFIRMED
REJECTED
WITHDRAWN
EXPIRED
```

只有进入 `CONFIRMED` 后，才更新局的已确认人数。最后一个座位必须通过数据库事务或乐观版本校验处理并发竞争。

### 5. 隐私边界

- 群聊仅回复必要内容，例如“好，我私聊你确认下”。
- 用户私聊内容不得写回群聊上下文。
- 不向参与者公开其他用户私聊、微信备注、画像或关系冲突原因。
- 所有客户可见文本继续通过客户可见内容审查合同。

## 建议工具

- `search_recent_agent_publications`
- `resolve_game_reference`
- `get_contact_relationship`
- `create_or_resume_join_request`
- `request_friend_connection`
- `get_game_availability`
- `confirm_game_participant`
- `send_channel_message`

模型负责决定调用顺序和处理歧义；后端继续负责工具参数合同、权限、幂等、并发、状态机合法性和落库。

## 验收标准

- [ ] 群里只存在一个川麻局时，“川麻那个我可以”能关联正确 `game_id`。
- [ ] 私聊表达相同意图时，能从用户可见的近期发布中关联正确局。
- [ ] 同时存在多个川麻局时不误加人，必须追问区分条件。
- [ ] 引用 Agent 发布消息回复“我来”时，能通过引用消息 ID 精确关联。
- [ ] 非好友用户进入 `WAITING_FRIEND`，加好友后恢复同一 `join_request`。
- [ ] 信息未确认前不增加已确认人数。
- [ ] 两人并发抢最后一个位置时最多一人确认成功。
- [ ] 局满、取消或过期后，旧发布引用不会继续加人。
- [ ] 群聊与私聊原始上下文隔离，连续 10 轮隐私对抗测试无泄露。
- [ ] 重复微信消息不会生成重复参与记录。
- [ ] 全链路记录 `traceId、source_message_id、publication_id、game_id、join_request_id`。
- [ ] 完成真实 DeepSeek 回归和 WeChaty 白名单灰度验证。

## 暂不包含

- 本设计记录不代表群聊自动外发已经开放。
- 本阶段不修改主 Agent、游戏状态机或数据库结构。
- 在真实群聊回复样本和评测集形成之前，不实现基于关键词的补丁式归属逻辑。
