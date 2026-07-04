import { WechatyBuilder } from 'wechaty'
import qrcodeTerminal from 'qrcode-terminal'

const DEFAULT_ENDPOINT = 'http://127.0.0.1:8790/api/channels/wechaty/raw'

const endpoint = process.env.MAHJONG_WECHATY_RAW_ENDPOINT || DEFAULT_ENDPOINT
const botName = process.env.MAHJONG_WECHATY_BOT_NAME || 'mahjong-wechaty-bridge'
const forwardSelfMessages = process.env.MAHJONG_WECHATY_FORWARD_SELF
  ? truthy(process.env.MAHJONG_WECHATY_FORWARD_SELF)
  : true

function truthy(value) {
  return ['1', 'true', 'yes', 'on'].includes(String(value || '').trim().toLowerCase())
}

function nowText() {
  const date = new Date()
  const pad = (item) => String(item).padStart(2, '0')
  return [
    date.getFullYear(),
    '-',
    pad(date.getMonth() + 1),
    '-',
    pad(date.getDate()),
    ' ',
    pad(date.getHours()),
    ':',
    pad(date.getMinutes()),
    ':',
    pad(date.getSeconds()),
  ].join('')
}

function primitive(value) {
  if (value === null || value === undefined) {
    return value
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return value
  }
  return String(value)
}

function cleanText(value) {
  const text = String(value || '').replace(/[\u0000-\u001f\u007f]/g, '').trim()
  return text
}

function jsonable(value, depth = 0) {
  if (depth > 4) {
    return String(value)
  }
  if (value === null || value === undefined) {
    return value
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return value
  }
  if (Array.isArray(value)) {
    return value.map((item) => jsonable(item, depth + 1))
  }
  if (typeof value === 'object') {
    const data = {}
    for (const [key, item] of Object.entries(value)) {
      data[key] = jsonable(item, depth + 1)
    }
    return data
  }
  return String(value)
}

async function safeCall(label, fn) {
  try {
    const value = await fn()
    return primitive(value)
  } catch (error) {
    return { error: `${label}: ${error?.message || String(error)}` }
  }
}

async function safeObject(label, fn) {
  try {
    return await fn()
  } catch (error) {
    return { error: `${label}: ${error?.message || String(error)}` }
  }
}

async function buildPayload(message) {
  const rawPayload = message.payload || {}
  const room = await safeObject('room', () => message.room())
  const talker = await safeObject('talker', () => message.talker())
  const listener = await safeObject('listener', () => message.listener())
  const text = await safeCall('text', () => message.text())
  const type = await safeCall('type', () => message.type())
  const id = primitive(message.id || rawPayload.id || rawPayload.filename || '')

  let roomPayload = null
  if (room && typeof room === 'object' && !room.error) {
    await safeCall('room.ready', () => room.ready?.())
    roomPayload = {
      id: primitive(room.id),
      topic: cleanText(await safeCall('room.topic', () => room.topic())),
      payload: jsonable(room.payload || {}),
    }
  }

  let talkerPayload = null
  if (talker && typeof talker === 'object' && !talker.error) {
    await safeCall('talker.ready', () => talker.ready?.())
    talkerPayload = {
      id: primitive(talker.id),
      name: cleanText(await safeCall('talker.name', () => talker.name())),
      alias: cleanText(await safeCall('talker.alias', () => talker.alias())),
      payload: jsonable(talker.payload || {}),
    }
  }

  let listenerPayload = null
  if (listener && typeof listener === 'object' && !listener.error) {
    await safeCall('listener.ready', () => listener.ready?.())
    listenerPayload = {
      id: primitive(listener.id),
      name: cleanText(await safeCall('listener.name', () => listener.name())),
      payload: jsonable(listener.payload || {}),
    }
  }

  const roomId = roomPayload?.id || primitive(rawPayload.roomId || rawPayload.room?.id || '')
  const senderId = talkerPayload?.id || primitive(rawPayload.talkerId || rawPayload.fromId || '')
  const senderName =
    talkerPayload?.name ||
    cleanText(rawPayload.talkerName || rawPayload.fromName || rawPayload.senderName || '')
  if (!talkerPayload && senderId) {
    talkerPayload = {
      id: senderId,
      name: senderName,
      alias: '',
      payload: {},
    }
  }
  if (!listenerPayload && rawPayload.listenerId) {
    listenerPayload = {
      id: primitive(rawPayload.listenerId),
      name: '',
      payload: {},
    }
  }
  const conversationId = roomId ? `wechaty:room:${roomId}` : `wechaty:contact:${senderId}`

  return {
    captured_at: nowText(),
    channel: 'wechaty',
    platform_name: 'wechaty',
    puppet: process.env.WECHATY_PUPPET || '',
    conversation_id: conversationId,
    message_id: id,
    source_message_id: id,
    message_type: primitive(type),
    is_room: Boolean(roomId),
    room: roomPayload,
    sender_id: senderId,
    sender_name: senderName,
    talker: talkerPayload,
    listener: listenerPayload,
    text: typeof text === 'string' ? text : '',
    raw_text: text,
    self_message: await safeCall('self', () => message.self()),
    payload: rawPayload,
  }
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify(payload),
  })
  const body = await response.text()
  let parsed = null
  try {
    parsed = JSON.parse(body)
  } catch {
    parsed = { raw_response: body }
  }
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${body}`)
  }
  return parsed
}

const bot = WechatyBuilder.build({ name: botName })

bot.on('scan', (qrcode, status) => {
  console.log(`[${nowText()}] scan status=${status}`)
  console.log(`https://wechaty.js.org/qrcode/${encodeURIComponent(qrcode)}`)
  qrcodeTerminal.generate(qrcode, { small: true })
})

bot.on('login', (user) => {
  console.log(`[${nowText()}] login: ${user}`)
})

bot.on('logout', (user) => {
  console.log(`[${nowText()}] logout: ${user}`)
})

bot.on('error', (error) => {
  console.error(`[${nowText()}] error:`, error)
})

bot.on('message', async (message) => {
  if (!forwardSelfMessages && message.self()) {
    console.log(`[${nowText()}] skipped self message_id=${message.id || message.payload?.id || '-'}`)
    return
  }
  const payload = await buildPayload(message)
  try {
    const result = await postJson(endpoint, payload)
    console.log(
      `[${nowText()}] forwarded message_id=${payload.message_id || '-'} ` +
        `conversation_id=${payload.conversation_id} trace_id=${result.trace_id || '-'}`
    )
  } catch (error) {
    console.error(`[${nowText()}] forward failed: ${error?.message || String(error)}`)
  }
})

process.once('SIGINT', async () => {
  console.log(`[${nowText()}] stopping...`)
  await bot.stop()
  process.exit(0)
})

console.log(`[${nowText()}] starting ${botName}`)
console.log(`[${nowText()}] endpoint=${endpoint}`)
console.log(`[${nowText()}] WECHATY_PUPPET=${process.env.WECHATY_PUPPET || '(default)'}`)

await bot.start()
