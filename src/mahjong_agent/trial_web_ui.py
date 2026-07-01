from __future__ import annotations


TRIAL_WEB_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>麻将馆组局试用台</title>
  <style>
    :root {
      --bg: #f6f7f4;
      --panel: #ffffff;
      --line: #d9ded8;
      --text: #20251f;
      --muted: #687266;
      --brand: #2f6f5e;
      --brand-soft: #e6f1ed;
      --warn: #9a5b14;
      --bad: #9f2f2f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 18px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfa;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    h1 { font-size: 18px; margin: 0; }
    h2 { font-size: 15px; margin: 0 0 10px; }
    h3 { font-size: 14px; margin: 14px 0 8px; }
    button {
      border: 1px solid #b8c5bc;
      background: #fff;
      color: var(--text);
      border-radius: 6px;
      padding: 7px 10px;
      cursor: pointer;
      white-space: nowrap;
    }
    button.primary { background: var(--brand); color: #fff; border-color: var(--brand); }
    button.ghost { background: var(--brand-soft); border-color: #c5d8d0; color: #214d41; }
    button.danger { color: var(--bad); }
    input, textarea, select {
      width: 100%;
      border: 1px solid #cbd3ca;
      border-radius: 6px;
      padding: 8px;
      background: #fff;
      color: var(--text);
      font: inherit;
    }
    textarea { resize: vertical; min-height: 150px; }
    .app {
      display: grid;
      grid-template-columns: minmax(260px, 340px) minmax(360px, 1fr) minmax(360px, 1fr);
      gap: 12px;
      padding: 12px;
      align-items: start;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }
    .stack { display: grid; gap: 10px; }
    .row { display: flex; gap: 8px; align-items: center; }
    .row > * { flex: 1; }
    .toolbar { display: flex; gap: 8px; flex-wrap: wrap; }
    .kv { display: grid; grid-template-columns: 92px 1fr; gap: 6px 10px; }
    .kv div:nth-child(odd) { color: var(--muted); }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 7px;
      border-radius: 999px;
      background: #eef1ed;
      margin: 0 4px 4px 0;
      font-size: 12px;
      color: #374138;
    }
    .pill.warn { background: #fff4dc; color: var(--warn); }
    .pill.good { background: var(--brand-soft); color: var(--brand); }
    .muted { color: var(--muted); }
    .draft, pre {
      white-space: pre-wrap;
      word-break: break-word;
      background: #f5f7f4;
      border: 1px solid #e1e5df;
      border-radius: 6px;
      padding: 9px;
      margin: 6px 0;
    }
    .draft.compact {
      padding: 7px;
      margin: 4px 0 0;
      min-height: 36px;
    }
    .message-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin: 8px 0;
    }
    .manual-game-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }
    .candidate, .game, .customer {
      border: 1px solid #e0e5de;
      border-radius: 7px;
      padding: 10px;
      margin-bottom: 8px;
      background: #fff;
    }
    .conversation {
      display: grid;
      gap: 6px;
      margin-top: 6px;
    }
    .turn {
      border-left: 3px solid #d7e5dc;
      background: #f8faf7;
      padding: 7px 9px;
      border-radius: 4px;
    }
    .candidate strong, .game strong { font-size: 15px; }
    .bottom {
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: 12px;
      padding: 0 12px 14px;
    }
    .customer-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 8px;
      max-height: 360px;
      overflow: auto;
    }
    .tiny { font-size: 12px; }
    @media (max-width: 1120px) {
      .app, .bottom { grid-template-columns: 1fr; }
      .message-grid { grid-template-columns: 1fr; }
      .manual-game-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>麻将馆组局试用台</h1>
    <div class="toolbar">
      <span id="cacheStatus" class="pill">缓存状态读取中</span>
      <button class="ghost" onclick="fillSample('weak')">弱意图样例</button>
      <button class="ghost" onclick="fillSample('clear')">明确组局样例</button>
      <button onclick="loadState()">刷新</button>
    </div>
  </header>

  <section class="app">
    <section class="panel stack">
      <h2>输入客户消息</h2>
      <div class="row">
        <input id="senderName" placeholder="客户昵称，如张哥" value="张哥" />
        <input id="senderId" placeholder="客户ID，可用微信备注" value="zhang" />
      </div>
      <input id="conversationId" placeholder="会话ID，如 group_a / private_zhang" value="boss_trial" />
      <textarea id="messageText">下午两点 0.5 无烟杭麻，打4小时，帮我组一桌</textarea>
      <div class="toolbar">
        <button class="primary" onclick="analyze()">解析消息</button>
        <button onclick="copyText('messageText')">复制原文</button>
        <button class="ghost" onclick="clearShortMemory()">清空短期记忆</button>
      </div>
      <div class="muted tiny">第一版只生成草稿，不自动群发、不自动私发、不确认房间。</div>
    </section>

    <section class="panel stack">
      <h2>识别出的组局条件</h2>
      <div id="parsedBox" class="muted">等待解析。</div>
      <h3>建议回复（待审批）</h3>
      <div id="suggestedReplyMeta" class="tiny muted"></div>
      <div id="followUpBox" class="draft muted">解析后生成给当前客户的建议回复。</div>
      <h3>群发草稿</h3>
      <div id="groupDraftBox" class="draft muted">信息明确后生成群发草稿。</div>
      <div class="toolbar">
        <button onclick="copyRendered('followUpBox')">复制建议回复</button>
        <button onclick="copyRendered('groupDraftBox')">复制群发</button>
      </div>
    </section>

    <section class="panel stack">
      <h2>当前匹配和待审批邀约</h2>
      <div id="candidateBox" class="muted">解析后显示可拼局或候选人。</div>
    </section>
  </section>

  <section class="bottom">
    <section class="panel">
      <div class="row">
        <h2>当前局看板</h2>
        <button class="danger" onclick="clearBoard()">清空当前局</button>
      </div>
      <h3>手动创建局</h3>
      <div class="manual-game-grid">
        <select id="manualGameType">
          <option value="hangzhou_mahjong">杭麻</option>
          <option value="sichuan_mahjong">川麻</option>
          <option value="hongzhong_mahjong">红中</option>
          <option value="zhuoji_mahjong">捉鸡</option>
          <option value="hunan_mahjong">湖南麻将</option>
        </select>
        <input id="manualVariant" placeholder="细分，如财敲/换三张，可空" value="财敲" />
        <input id="manualStartTime" type="time" />
        <input id="manualLevel" placeholder="档位，如0.5/1/2-16" value="0.5" />
        <input id="manualCurrentPlayers" type="number" min="0" max="4" placeholder="当前人数" value="3" />
        <input id="manualMissingCount" type="number" min="0" max="4" placeholder="缺口" value="1" />
        <input id="manualDurationHours" type="number" min="1" max="12" step="0.5" placeholder="时长/小时" value="4" />
        <select id="manualSmoke">
          <option value="no_smoke">无烟</option>
          <option value="smoke_ok">有烟</option>
          <option value="any">烟况都可</option>
        </select>
        <select id="manualStatus">
          <option value="待组局">待组局</option>
          <option value="邀约中">邀约中</option>
          <option value="已满">已满</option>
        </select>
        <input id="manualOrganizerName" placeholder="发起人/来源" value="老板手动创建" />
      </div>
      <textarea id="manualSourceText" style="min-height: 72px; margin-top: 8px;" placeholder="来源说明，如：电话里李姐说六点有烟1块，三缺一"></textarea>
      <div class="toolbar" style="margin: 8px 0 12px;">
        <button class="primary" onclick="manualCreateGame()">创建到看板</button>
      </div>
      <div id="gameBoard" class="muted">暂无当前局。</div>
    </section>
    <section class="panel">
      <h2>今日复盘</h2>
      <div id="recapBox" class="muted">暂无复盘。</div>
    </section>
  </section>

  <section class="bottom">
    <section class="panel stack">
      <h2>评测样本沉淀</h2>
      <textarea id="evalNote" placeholder="写清楚老板判断：哪里错、哪里对、希望以后怎么处理。"></textarea>
      <div class="row">
        <select id="evalExpectedAction">
          <option value="">golden 默认沿用当前动作</option>
          <option value="ask_clarification">追问信息</option>
          <option value="create_pending_game">进入待组局</option>
          <option value="create_game">创建组局</option>
          <option value="queue_invites">推荐并生成邀约</option>
          <option value="accept_seat">接受入局</option>
          <option value="decline_invite">拒绝入局</option>
          <option value="close_game">关闭局</option>
          <option value="ignore">静默</option>
          <option value="human_review">转人工</option>
        </select>
        <input id="evalTags" placeholder="标签，逗号分隔，如弱意图,张哥,杭州" />
      </div>
      <div class="toolbar">
        <button class="danger" onclick="recordEvalCase('badcase')">归档 badcase</button>
        <button class="ghost" onclick="recordEvalCase('golden')">加入 golden</button>
        <button onclick="recordEvalCase('few_shot')">采集 few-shot</button>
      </div>
      <div id="evalResult" class="muted tiny">先解析一条消息，再把结果沉淀成评测数据。</div>
    </section>
    <section class="panel">
      <h2>可观测与评测入口</h2>
      <div id="evalOverview" class="muted">评测数据读取中。</div>
      <div class="toolbar" style="margin-top: 10px;">
        <a href="/logs" target="_blank"><button>查看日志</button></a>
        <a href="/api/logs" target="_blank"><button>JSON 日志</button></a>
        <a href="/api/eval-cases" target="_blank"><button>评测数据</button></a>
      </div>
    </section>
  </section>

  <section class="bottom">
    <section class="panel">
      <h2>客户画像管理</h2>
      <div class="row">
        <input id="customerName" placeholder="昵称" />
        <input id="customerContact" placeholder="微信备注/联系方式" />
      </div>
      <div class="row">
        <select id="customerGender">
          <option value="unknown">性别未知</option>
          <option value="male">男</option>
          <option value="female">女</option>
        </select>
      </div>
      <div class="row">
        <input id="customerGames" placeholder="常打大类，逗号分隔，如杭麻,川麻；财敲/换三张等细分写备注" />
        <input id="customerLevels" placeholder="常打档位，如0.5,1" />
      </div>
      <div class="row">
        <input id="customerHours" placeholder="常来时间，如14,19,20" />
        <select id="customerSmoke">
          <option value="any">烟况都可</option>
          <option value="no_smoke">无烟偏好</option>
          <option value="smoke_ok">可有烟</option>
        </select>
      </div>
      <textarea id="customerNotes" placeholder="备注，如常一个人来、少打扰"></textarea>
      <button class="primary" onclick="saveCustomer()">保存客户</button>
    </section>
    <section class="panel">
      <h2>常客列表</h2>
      <div id="customerList" class="customer-grid"></div>
    </section>
  </section>

  <script>
    let currentAnalysis = null;
    window.latestState = null;

    const samples = {
      weak: "老板，今天下班有人打麻将吗？0.5或者1都行，烟也都可",
      clear: "下午两点 0.5 无烟杭麻，打4小时，一缺三，帮我组一桌"
    };

    function fillSample(name) {
      document.getElementById("messageText").value = samples[name];
    }

    async function api(path, options = {}) {
      const res = await fetch(path, {
        headers: {"Content-Type": "application/json"},
        ...options
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || data.error || "请求失败");
      return data;
    }

    async function loadState() {
      const state = await api("/api/state");
      renderState(state);
    }

    async function analyze() {
      const payload = {
        sender_name: document.getElementById("senderName").value,
        sender_id: document.getElementById("senderId").value,
        conversation_id: document.getElementById("conversationId").value,
        text: document.getElementById("messageText").value
      };
      currentAnalysis = await api("/api/analyze", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      renderAnalysis(currentAnalysis);
      renderState(currentAnalysis.state);
    }

    function renderAnalysis(result) {
      const parsed = result.parsed || {};
      const missing = result.missing_fields || [];
      const rules = (parsed.rules || []).map(item => `<span class="pill good">${escapeHtml(item)}</span>`).join("");
      const composition = parsed.candidate_composition_preference || {};
      const compositionText = (composition.gender_labels || []).length ? (composition.gender_labels || []).join("、") : "-";
      const fields = [
        ["会话ID", result.conversation_id || "-"],
        ["用户意向", parsed.user_intent || intentLabel(result.decision?.action)],
        ["玩法", parsed.game_label || "-"],
        ["时间", parsed.start_time || "-"],
        ["档位", parsed.level || "-"],
        ["时长", parsed.duration_text || (parsed.duration_hours ? `${parsed.duration_hours} 小时` : "-")],
        ["当前人数", parsed.current_player_count ?? "-"],
        ["缺口", parsed.missing_count ?? "-"],
        ["烟况/规则", rules || "-"],
        ["候选偏好", compositionText]
      ];
      document.getElementById("parsedBox").innerHTML = `
        <div class="kv">${fields.map(([k, v]) => `<div>${k}</div><div>${v}</div>`).join("")}</div>
        <div>${missing.map(item => `<span class="pill warn">缺 ${fieldLabel(item)}</span>`).join("")}</div>
        <div class="muted tiny">${escapeHtml(parsed.summary || result.decision?.reply_text || "")}</div>
      `;
      const suggested = result.suggested_reply || {};
      const sourceText = suggested.source === "llm" ? `LLM：${suggested.model || "-"}` : "规则兜底";
      document.getElementById("suggestedReplyMeta").innerHTML = `
        <span class="pill warn">${escapeHtml(suggested.status || "待审批")}</span>
        <span class="pill">${escapeHtml(sourceText)}</span>
        ${(suggested.notes || []).map(note => `<span class="pill">${escapeHtml(note)}</span>`).join("")}
      `;
      document.getElementById("followUpBox").textContent = suggested.text || result.follow_up || "信息基本够，可以生成候选和草稿。";
      document.getElementById("groupDraftBox").textContent = result.group_draft || "暂未生成群发草稿。";
      renderCandidates(result.outbox || [], result.pool_matches || []);
    }

    function renderCandidates(outbox, poolMatches) {
      const box = document.getElementById("candidateBox");
      if (!outbox.length && !poolMatches.length) {
        box.innerHTML = `<div class="muted">暂无可拼局或待审批邀约。通常是因为时间、档位或人数还没补齐。</div>`;
        return;
      }
      const poolHtml = poolMatches.length ? `
        <h3>可拼/可加入的局</h3>
        ${poolMatches.map(item => `
          <div class="candidate">
            <div class="row">
              <strong>${escapeHtml(item.summary || "匹配局")} <span class="pill">${escapeHtml(String(item.score || 0))}分</span></strong>
              <span class="pill good">可拼局</span>
            </div>
            <div>${(item.reasons || []).map(reason => `<span class="pill good">${escapeHtml(reason)}</span>`).join("")}</div>
            <div class="draft" id="pool-${item.game_id}">${escapeHtml(item.reply_text || "")}</div>
            <div class="toolbar">
              <button onclick="copyPoolReply('${item.game_id}')">复制回复</button>
            </div>
          </div>
        `).join("")}
      ` : "";
      const outboxHtml = outbox.length ? `
        <h3>推荐候选人和待审批邀约</h3>
        ${outbox.map(item => `
        <div class="candidate">
          <div class="row">
            <strong>${escapeHtml(item.customer_name)} <span class="pill">${item.score}分</span></strong>
            <span class="pill">${escapeHtml(item.gender_label || "未知")}</span>
            <span class="pill warn">${escapeHtml(item.approval_status || item.status || "待审批")}</span>
          </div>
          <div>${(item.reasons || []).map(reason => `<span class="pill good">${escapeHtml(reason)}</span>`).join("")}</div>
          <div>${(item.warnings || []).map(reason => `<span class="pill warn">${escapeHtml(reason)}</span>`).join("")}</div>
          <div class="draft" id="draft-${item.id}">${escapeHtml(item.message_text)}</div>
          <div class="toolbar">
            <button onclick="copyDraft('${item.id}')">复制邀约</button>
            <button onclick="approvalDecision('${item.approval?.id || ""}', 'approved')">审批通过</button>
            <button class="danger" onclick="approvalDecision('${item.approval?.id || ""}', 'rejected')">审批拒绝</button>
            <button onclick="sendOutbox('${item.id}')">已发送</button>
            <button onclick="feedback('${item.id}', '${item.game_id}', '${item.customer_id}', 'accepted')">已确认</button>
            <button onclick="feedback('${item.id}', '${item.game_id}', '${item.customer_id}', 'arrived')">已到店</button>
            <button onclick="feedback('${item.id}', '${item.game_id}', '${item.customer_id}', 'declined')">拒绝</button>
            <button onclick="feedback('${item.id}', '${item.game_id}', '${item.customer_id}', 'no_reply')">未回复</button>
            <button class="danger" onclick="feedback('${item.id}', '${item.game_id}', '${item.customer_id}', 'do_not_disturb')">别再打扰</button>
          </div>
          <div class="message-grid">
            <input id="candidate-reply-${item.id}" placeholder="模拟候选人回复，如：可以 / 今天不来 / 几点啊" />
            <button onclick="candidateReply('${item.id}')">模拟回复</button>
          </div>
          <div class="draft compact" id="candidate-result-${item.id}">候选人回复后，系统会给出老板下一句建议。</div>
          <div class="conversation" id="candidate-conversation-${item.id}">
            ${renderCandidateConversation(item.conversation || [])}
          </div>
        </div>
        `).join("")}
      ` : "";
      box.innerHTML = poolHtml + outboxHtml;
    }

    function renderCandidateConversation(turns) {
      if (!turns.length) {
        return `<div class="muted tiny">暂无模拟会话。</div>`;
      }
      return turns.map((turn, index) => `
        <div class="turn">
          <div class="muted tiny">第 ${index + 1} 轮 · ${escapeHtml(turn.status || turn.feedback_type || "")}</div>
          <div><strong>候选人：</strong>${escapeHtml(turn.candidate_text || "-")}</div>
          <div><strong>老板：</strong>${escapeHtml(turn.boss_reply || "-")}</div>
        </div>
      `).join("");
    }

    async function copyDraft(id) {
      await navigator.clipboard.writeText(document.getElementById(`draft-${id}`).textContent);
      const item = findOutbox(id);
      if (item) await feedback(id, item.game_id, item.customer_id, "copied");
    }

    async function copyPoolReply(gameId) {
      await navigator.clipboard.writeText(document.getElementById(`pool-${gameId}`).textContent);
    }

    function findOutbox(id) {
      if (!currentAnalysis) return null;
      return (currentAnalysis.outbox || []).find(item => item.id === id);
    }

    async function approvalDecision(approvalId, decision) {
      if (!approvalId) {
        alert("这条草稿还没有审批请求，请刷新后再试。");
        return;
      }
      const data = await api("/api/approval-decision", {
        method: "POST",
        body: JSON.stringify({approval_id: approvalId, decision})
      });
      const approval = data.approval || {};
      if (currentAnalysis?.outbox && approval.target_type === "outbox") {
        currentAnalysis.outbox = currentAnalysis.outbox.map(item => (
          item.id === approval.target_id
            ? {...item, approval, approval_status: approvalStatusLabel(approval.status), status: approvalStatusLabel(approval.status), message_text: approval.final_message_text || item.message_text}
            : item
        ));
        renderCandidates(currentAnalysis.outbox || [], currentAnalysis.pool_matches || []);
      }
      renderState(data.state);
    }

    async function feedback(outboxId, gameId, customerId, feedbackType) {
      const data = await api("/api/feedback", {
        method: "POST",
        body: JSON.stringify({
          outbox_id: outboxId || null,
          game_id: gameId || null,
          customer_id: customerId || null,
          feedback_type: feedbackType
        })
      });
      renderState(data.state);
    }

    async function candidateReply(outboxId) {
      const input = document.getElementById(`candidate-reply-${outboxId}`);
      const text = (input?.value || "").trim();
      if (!text) {
        alert("请输入候选人的回复内容。");
        return;
      }
      const data = await api("/api/candidate-message", {
        method: "POST",
        body: JSON.stringify({outbox_id: outboxId, text})
      });
      const candidate = data.candidate_message || {};
      if (currentAnalysis?.outbox && data.outbox_item) {
        currentAnalysis.outbox = currentAnalysis.outbox.map(item => (
          item.id === outboxId ? {...item, ...data.outbox_item, status: data.outbox_item.status, approval_status: data.outbox_item.status} : item
        ));
        renderCandidates(currentAnalysis.outbox || [], currentAnalysis.pool_matches || []);
      }
      const freshResultBox = document.getElementById(`candidate-result-${outboxId}`);
      if (freshResultBox) {
        const source = candidate.reply_source === "llm" ? `LLM：${candidate.model || "-"}` : "规则兜底";
        const followup = data.organizer_followup;
        freshResultBox.innerHTML = `
          <div>识别：${escapeHtml(candidate.status || candidate.intent || "-")}；${escapeHtml(source)}；老板建议回复：${escapeHtml(candidate.suggested_boss_reply || "-")}</div>
          ${followup ? `<div class="draft compact"><strong>待问${escapeHtml(followup.recipient_name || "发起人")}：</strong>${escapeHtml(followup.message_text || "-")}</div>` : ""}
        `;
      }
      renderState(data.state);
    }

    async function gameFeedback(gameId, feedbackType) {
      const data = await api("/api/feedback", {
        method: "POST",
        body: JSON.stringify({game_id: gameId, feedback_type: feedbackType})
      });
      renderState(data.state);
    }

    async function clearBoard() {
      if (!confirm("确定清空当前局看板吗？历史日志和复盘仍会保留。")) return;
      const data = await api("/api/clear-board", {
        method: "POST",
        body: JSON.stringify({reason: "老板在试用台手动清空当前局看板"})
      });
      renderState(data.state);
      alert(`已清空 ${data.cleared_count || 0} 个当前局。`);
    }

    async function clearShortMemory() {
      const senderId = document.getElementById("senderId").value || "anonymous";
      const conversationId = document.getElementById("conversationId").value || "boss_trial";
      if (!confirm(`确定清空 ${conversationId} / ${senderId} 的短期记忆吗？客户画像、当前局和日志不会删除。`)) return;
      const data = await api("/api/clear-short-memory", {
        method: "POST",
        body: JSON.stringify({
          sender_id: senderId,
          conversation_id: conversationId,
          reason: "老板在试用台手动清空当前客户短期记忆"
        })
      });
      renderState(data.state);
      alert(`已清空 ${data.cleared_count || 0} 条短期记忆。`);
    }

    async function manualCreateGame() {
      const payload = {
        organizer_id: "boss_manual",
        organizer_name: document.getElementById("manualOrganizerName").value || "老板手动创建",
        game_type: document.getElementById("manualGameType").value,
        variant: normalizeVariant(document.getElementById("manualVariant").value),
        level: document.getElementById("manualLevel").value,
        start_time: document.getElementById("manualStartTime").value,
        current_player_count: Number(document.getElementById("manualCurrentPlayers").value),
        missing_count: Number(document.getElementById("manualMissingCount").value),
        duration_hours: Number(document.getElementById("manualDurationHours").value),
        smoke: document.getElementById("manualSmoke").value,
        status: document.getElementById("manualStatus").value,
        source_text: document.getElementById("manualSourceText").value
      };
      const data = await api("/api/manual-create-game", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      renderState(data.state);
      document.getElementById("manualSourceText").value = "";
    }

    function normalizeVariant(value) {
      const text = String(value || "").trim();
      return {
        "财敲": "caiqiao",
        "幺鸡": "yaoji",
        "妖鸡": "yaoji",
        "素鸡": "suji",
        "幺鸡47": "yaoji_47"
      }[text] || "";
    }

    async function recordEvalCase(caseType) {
      if (!currentAnalysis) {
        alert("请先解析一条消息，再归档评测样本。");
        return;
      }
      const expectedAction = document.getElementById("evalExpectedAction").value;
      const expected = {};
      if (caseType === "golden" && expectedAction) {
        expected.action = expectedAction;
        expected.should_reply = Boolean(currentAnalysis.decision?.should_reply);
      }
      const data = await api("/api/eval-cases", {
        method: "POST",
        body: JSON.stringify({
          case_type: caseType,
          source_trace_id: currentAnalysis.trace_id,
          sender_id: currentAnalysis.sender_id,
          sender_name: currentAnalysis.sender_name,
          text: currentAnalysis.source_text || document.getElementById("messageText").value,
          note: document.getElementById("evalNote").value,
          tags: splitFreeText(document.getElementById("evalTags").value),
          expected,
          analysis: currentAnalysis
        })
      });
      document.getElementById("evalResult").textContent = `${caseType} 已写入：${data.path}，id=${data.record_id}`;
      renderEvalOverview(data.overview || {});
    }

    function renderState(state) {
      window.latestState = state || {};
      renderCache(state.cache || {});
      renderGames(state.games || []);
      renderRecap(state.recap || {});
      renderCustomers(state.customers || []);
      renderEvalOverview(state.evals || {});
    }

    function renderCache(cache) {
      const status = document.getElementById("cacheStatus");
      if (!status) return;
      if (cache.redis_enabled) {
        status.className = "pill good";
        status.textContent = "Redis 短期记忆已启用";
      } else {
        status.className = "pill warn";
        status.textContent = "仅 SQLite，Redis 未启用";
      }
    }

    function renderGames(games) {
      const box = document.getElementById("gameBoard");
      if (!games.length) {
        box.textContent = "暂无当前局。";
        return;
      }
      box.innerHTML = games.map(game => {
        const outbox = game.outbox || [];
        const followups = game.followups || [];
        const confirmed = game.confirmed_count ?? outbox.filter(item => ["已确认", "已到店"].includes(item.status)).length;
        const missing = game.parsed?.missing_count;
        const stillMissing = game.remaining_missing_count ?? (missing == null ? "-" : Math.max(0, missing - confirmed));
        const duration = game.parsed?.duration_text ? `，${game.parsed.duration_text}` : (game.parsed?.duration_hours ? `，约 ${game.parsed.duration_hours} 小时` : "");
        const participants = game.participants || [];
        const title = game.live_summary || game.parsed?.live_summary || dynamicGameSummary(game, stillMissing);
        return `
          <div class="game">
            <strong>${escapeHtml(title)}</strong>
            <span class="pill">${escapeHtml(game.status)}</span>
            <div class="muted tiny">已确认 ${confirmed} 人，还缺 ${stillMissing} 人${escapeHtml(duration)}</div>
            <div>${participants.map(item => `<span class="pill">${escapeHtml(item.customer_name || "-")}：${escapeHtml(item.status || item.role || "")}${item.count ? ` x${escapeHtml(item.count)}` : ""}</span>`).join("")}</div>
            <div class="message-grid">
              <div>
                <div class="muted tiny">用户消息</div>
                <div class="draft compact">${escapeHtml(game.source_text || "-")}</div>
              </div>
              <div>
                <div class="muted tiny">系统建议回复</div>
                <div class="draft compact">${escapeHtml(game.reply_text || "-")}</div>
              </div>
            </div>
            <div>${outbox.slice(0, 6).map(item => `<span class="pill">${escapeHtml(item.customer_name)}：${escapeHtml(item.status)}</span>`).join("")}</div>
            ${followups.length ? `
              <div class="conversation">
                <div class="muted tiny">待协商确认</div>
                ${followups.slice(0, 5).map(item => `
                  <div class="turn">
                    <div><strong>给${escapeHtml(item.recipient_name || "-")}：</strong>${escapeHtml(item.message_text || "-")}</div>
                    <div class="muted tiny">${escapeHtml(item.status || "待审批")} · ${escapeHtml(item.reason || "")}</div>
                  </div>
                `).join("")}
              </div>
            ` : ""}
            <div class="toolbar">
              <button onclick="gameFeedback('${game.id}', 'game_success')">已成局</button>
              <button onclick="gameFeedback('${game.id}', 'game_cancelled')">局取消</button>
            </div>
          </div>
        `;
      }).join("");
    }

    function dynamicGameSummary(game, stillMissing) {
      const parsed = game.parsed || {};
      const rules = (parsed.rules || []).filter(rule => !["杭麻", "川麻", "麻将", parsed.game_label].includes(rule));
      const level = parsed.level ? `${parsed.level}档` : "";
      const missing = stillMissing === "-" ? "" : (Number(stillMissing) > 0 ? `缺${stillMissing}` : "人齐");
      return [parsed.game_label, level, parsed.start_time, missing, ...rules].filter(Boolean).join(" ") || parsed.summary || game.source_text || "-";
    }

    function renderRecap(recap) {
      const games = recap.games_by_status || {};
      const outbox = recap.outbox_by_status || {};
      const top = recap.top_customers || [];
      const archived = window.latestState?.recent_archived_games || [];
      document.getElementById("recapBox").innerHTML = `
        <div class="kv">
          <div>今日组局</div><div>${Object.values(games).reduce((a, b) => a + b, 0)} 次</div>
          <div>邀约草稿</div><div>${Object.values(outbox).reduce((a, b) => a + b, 0)} 条</div>
          <div>成局</div><div>${games["已成局"] || 0} 次</div>
        </div>
        <h3>响应较好客户</h3>
        <div>${top.map(item => `<span class="pill good">${escapeHtml(item.display_name)} ${Math.round(item.response_rate * 100)}%</span>`).join("") || "暂无"}</div>
        <h3>建议</h3>
        <div>${(recap.suggestions || []).map(item => `<div class="muted">- ${escapeHtml(item)}</div>`).join("")}</div>
        <h3>最近归档局</h3>
        <div>${archived.slice(0, 5).map(game => `
          <div class="draft compact">
            <strong>${escapeHtml(game.parsed?.summary || game.source_text || game.id)}</strong>
            <span class="pill">${escapeHtml(game.status)}</span>
            <div class="muted tiny">${escapeHtml(game.final_reason || "暂无归档原因")}</div>
          </div>
        `).join("") || "暂无归档局。"}</div>
      `;
    }

    function renderEvalOverview(evals) {
      const box = document.getElementById("evalOverview");
      if (!box) return;
      const counts = evals.counts || {};
      const paths = evals.paths || {};
      box.innerHTML = `
        <div class="kv">
          <div>golden</div><div>${counts.golden ?? 0} 条</div>
          <div>boss-trial golden</div><div>${counts.boss_trial_golden ?? 0} 条</div>
          <div>badcase</div><div>${counts.badcase ?? 0} 条</div>
          <div>few-shot</div><div>${counts.few_shot ?? 0} 条</div>
          <div>skills</div><div>${counts.skills ?? 0} 条</div>
        </div>
        <h3>文件路径</h3>
        <div class="tiny muted">golden：${escapeHtml(paths.golden || "-")}</div>
        <div class="tiny muted">boss-trial golden：${escapeHtml(paths.boss_trial_golden || "-")}</div>
        <div class="tiny muted">badcase：${escapeHtml(paths.badcase || "-")}</div>
        <div class="tiny muted">few-shot：${escapeHtml(paths.few_shot || "-")}</div>
        <div class="tiny muted">skills：${escapeHtml(paths.skills || "-")}</div>
        <h3>回归命令</h3>
        <pre>${escapeHtml(evals.runner || "PYTHONPATH=src python scripts/run_scenario_eval.py")}</pre>
      `;
    }

    function renderCustomers(customers) {
      const box = document.getElementById("customerList");
      box.innerHTML = customers.map(customer => `
        <div class="customer">
          <strong>${escapeHtml(customer.display_name)}</strong>
          <span class="pill">${escapeHtml(customer.gender_label || "未知")}</span>
          ${customer.no_contact ? '<span class="pill warn">勿扰</span>' : ''}
          <div class="muted tiny">${escapeHtml(customer.contact || "")}</div>
          <div>${(customer.preferred_games || []).map(item => `<span class="pill">${escapeHtml(item)}</span>`).join("")}</div>
          <div>${(customer.preferred_levels || []).map(item => `<span class="pill">${escapeHtml(item)}档</span>`).join("")}</div>
          <div class="muted tiny">响应率 ${Math.round((customer.response_rate || 0) * 100)}%，最近邀约 ${formatTime(customer.last_invited_at)}</div>
          <button onclick='editCustomer(${JSON.stringify(customer).replaceAll("'", "&#39;")})'>编辑</button>
        </div>
      `).join("");
    }

    function editCustomer(customer) {
      document.getElementById("customerName").value = customer.display_name || "";
      document.getElementById("customerContact").value = customer.contact || "";
      document.getElementById("customerGender").value = customer.gender || "unknown";
      document.getElementById("customerGames").value = (customer.preferred_games || []).join(",");
      document.getElementById("customerLevels").value = (customer.preferred_levels || []).join(",");
      document.getElementById("customerHours").value = (customer.usual_start_hours || []).join(",");
      document.getElementById("customerSmoke").value = customer.smoke_preference || "any";
      document.getElementById("customerNotes").value = customer.notes || "";
      document.getElementById("senderName").value = customer.display_name || "";
      document.getElementById("senderId").value = customer.id || "";
    }

    async function saveCustomer() {
      const name = document.getElementById("customerName").value.trim();
      const payload = {
        id: name,
        display_name: name,
        contact: document.getElementById("customerContact").value,
        gender: document.getElementById("customerGender").value,
        preferred_games: splitInput("customerGames"),
        preferred_levels: splitInput("customerLevels"),
        usual_start_hours: splitInput("customerHours").map(Number).filter(Number.isFinite),
        smoke_preference: document.getElementById("customerSmoke").value,
        notes: document.getElementById("customerNotes").value,
        response_rate: 0.5
      };
      await api("/api/customers", {method: "POST", body: JSON.stringify(payload)});
      await loadState();
    }

    async function sendOutbox(outboxId) {
      const data = await api("/api/send-outbox", {
        method: "POST",
        body: JSON.stringify({outbox_id: outboxId, channel: "manual"})
      });
      if (currentAnalysis?.outbox && data.outbox_item) {
        currentAnalysis.outbox = currentAnalysis.outbox.map(item => (
          item.id === outboxId
            ? {...item, ...data.outbox_item, approval_status: data.outbox_item.approval_status || data.outbox_item.status}
            : item
        ));
        renderCandidates(currentAnalysis.outbox || [], currentAnalysis.pool_matches || []);
      }
      await loadState();
    }

    function splitInput(id) {
      return document.getElementById(id).value.split(/[,，、\s]+/).map(s => s.trim()).filter(Boolean);
    }

    function splitFreeText(value) {
      return String(value || "").split(/[,，、\s]+/).map(s => s.trim()).filter(Boolean);
    }

    async function copyText(id) {
      await navigator.clipboard.writeText(document.getElementById(id).value);
    }

    async function copyRendered(id) {
      await navigator.clipboard.writeText(document.getElementById(id).textContent);
    }

    function fieldLabel(value) {
      return {
        play_type: "玩法",
        start_time: "时间",
        stake: "档位",
        known_players: "人数",
        smoke: "烟况",
        duration: "时长"
      }[value] || value;
    }

    function intentLabel(action) {
      return {
        ask_clarification: "想打/想组局，信息待确认",
        create_pending_game: "明确组局，先入待组局",
        create_game: "创建组局需求",
        queue_invites: "找人组局",
        accept_seat: "接受邀约/报名入局",
        decline_invite: "拒绝邀约",
        close_game: "取消或关闭组局",
        ignore: "无关消息，无需回复",
        human_review: "高风险或不确定，转人工"
      }[action] || action || "-";
    }

    function formatTime(value) {
      if (!value) return "-";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return "-";
      return `${date.getMonth() + 1}-${date.getDate()} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
    }

    function approvalStatusLabel(value) {
      return {
        pending: "待审批",
        approved: "已审批",
        rejected: "审批拒绝"
      }[String(value || "").toLowerCase()] || value || "待审批";
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[char]));
    }

    loadState().catch(err => alert(err.message));
  </script>
</body>
</html>
"""
