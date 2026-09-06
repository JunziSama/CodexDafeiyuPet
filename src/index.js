import Schema from '@deepseek-ai/schemastery'
import { CompanionReducer } from './companion-reducer.js'
import { HelperProcess } from './helper-process.js'
import {
  CompanionMessageKind,
  CompanionState,
  createMessage,
} from './protocol.js'

export const name = 'dsh-pet-indesktop'
export const inject = ['sessions']
export const CONFIG_ENDPOINT = '/plugins/dsh-pet-indesktop/config'

export const Config = Schema.object({
  enabled: Schema.boolean().default(true).description('启用独立桌宠'),
  scale: Schema.number().min(0.5).max(1.2).step(0.05).default(0.70).role('slider').description('桌宠大小'),
  reducedMotion: Schema.boolean().default(false).description('减少移动和循环动画'),
  cards: Schema.array(Schema.object({
    id: Schema.string().default('card-0').description('卡片 ID'),
    name: Schema.string().default('独立桌宠').description('卡片名称'),
    visible: Schema.boolean().default(true).description('显示桌宠'),
  })).default([]).description('桌宠卡片列表'),
}).description('dsh-pet-indesktop 独立桌面宠物（与 dsh-dafeiyu 共存）')

const defaults = Object.freeze({
  enabled: true,
  scale: 0.70,
  reducedMotion: false,
  cards: [{ id: 'card-0', name: '独立桌宠', visible: true }],
})

function publicConfig(config = {}) {
  const cards = Array.isArray(config.cards) && config.cards.length > 0
    ? config.cards.map((card) => ({
        id: String(card.id || `card-${Math.random().toString(36).slice(2, 8)}`),
        name: String(card.name || '独立桌宠').slice(0, 40),
        visible: card.visible !== false,
      }))
    : defaults.cards.map((card) => ({ ...card }))
  return {
    enabled: config.enabled ?? defaults.enabled,
    scale: config.scale ?? defaults.scale,
    reducedMotion: config.reducedMotion ?? defaults.reducedMotion,
    cards,
  }
}

function localSettingsScope(value) {
  return {
    get: () => value,
    watch: () => () => {},
  }
}

function jsonResponse(res, status, body) {
  const payload = JSON.stringify(body)
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(payload),
  })
  res.end(payload)
}

function isLoopback(address) {
  return address === '127.0.0.1' || address === '::1' || address === '::ffff:127.0.0.1'
}

async function readPatch(req) {
  const chunks = []
  let bytes = 0
  for await (const chunk of req) {
    bytes += chunk.length
    if (bytes > 8192) throw new Error('request body is too large')
    chunks.push(chunk)
  }
  const value = JSON.parse(Buffer.concat(chunks).toString('utf8'))
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error('patch must be an object')
  const allowed = new Set(Object.keys(defaults))
  if (Object.keys(value).some((key) => !allowed.has(key))) throw new Error('patch contains an unknown setting')
  return value
}

export function createConfigHandler(settings) {
  return async (req, res) => {
    if (!isLoopback(req.socket?.remoteAddress)) {
      jsonResponse(res, 403, { error: 'local access only' })
      return
    }
    const origin = req.headers?.origin
    if (origin) {
      let originHost
      try { originHost = new URL(origin).host } catch {}
      if (!originHost || originHost !== req.headers.host) {
        jsonResponse(res, 403, { error: 'origin mismatch' })
        return
      }
    }
    if (req.method === 'GET') {
      jsonResponse(res, 200, settings.get())
      return
    }
    if (req.method !== 'PATCH') {
      jsonResponse(res, 405, { error: 'method not allowed' })
      return
    }
    try {
      await settings.update(await readPatch(req))
      jsonResponse(res, 200, settings.get())
    } catch (error) {
      jsonResponse(res, 400, { error: error instanceof Error ? error.message : String(error) })
    }
  }
}

function mount(ctx, config = {}, eventCtx = ctx) {
  const logger = ctx.logger ?? console
  const base = publicConfig(config)
  const settings = ctx.settings?.register?.('dsh-pet-indesktop', Config, {
    base,
    applies: 'live',
  }) ?? localSettingsScope(base)

  const bridges = new Map()
  let reducer = new CompanionReducer({ includeSubagents: false })

  async function stopBridge(cardId, reason = 'settings-change') {
    const bridge = bridges.get(cardId)
    if (!bridge) return
    bridge.stop(reason)
    bridges.delete(cardId)
    // Wait until the old window actually exits before allowing a replacement
    // card with the same id to spawn; otherwise two pets can be visible at
    // once during settings changes / hot reloads.
    await bridge.waitForExit(4000)
  }

  function startBridge(resolved, card, index) {
    if (resolved.enabled === false) return
    if (card.visible === false) return
    if (bridges.has(card.id)) return
    const bridge = new HelperProcess({
      env: {
        DSH_PET_CARD_ID: String(card.id),
        DSH_PET_VISIBLE: card.visible === false ? '0' : '1',
        DSH_PET_SCALE: String(resolved.scale ?? defaults.scale),
        DSH_PET_REDUCED_MOTION: resolved.reducedMotion === true ? '1' : '0',
        DSH_PET_CARD_OFFSET: String(index * 72),
      },
    }, logger)
    bridges.set(card.id, bridge)
    bridge.start()
    bridge.send(createMessage(CompanionMessageKind.HELLO, {
      state: CompanionState.IDLE,
      host: 'deepseek-harness',
      pluginVersion: '0.1.0',
      visible: card.visible !== false,
      message: '独立桌宠已连接到 EAC',
    }))
    bridge.send(createMessage(CompanionMessageKind.STATE, {
      state: CompanionState.IDLE,
      phase: 'plugin-start',
      stage: '等待任务',
      visible: card.visible !== false,
      message: '我在这里待命，等待新任务。',
      detail: 'EAC · dsh-pet-indesktop',
    }))
    logger.info?.(`dsh-pet-indesktop card ${card.id} started`)
  }

  async function syncRuntimes(resolved) {
    const stops = []
    for (const cardId of [...bridges.keys()]) {
      const card = resolved.cards.find((entry) => entry.id === cardId)
      if (!card || resolved.enabled === false || card.visible === false) stops.push(stopBridge(cardId))
    }
    await Promise.all(stops)
    if (resolved.enabled === false) return
    resolved.cards.forEach((card, index) => startBridge(resolved, card, index))
  }

  syncRuntimes(settings.get())

  const offEvent = eventCtx.on('session/event', (session, event) => {
    const messages = reducer.handle(session, event)
    if (messages.length === 0) return
    for (const bridge of bridges.values()) {
      for (const message of messages) bridge.send(message)
    }
  }, { global: true })

  const offDisposed = eventCtx.on('session/disposed', (session) => {
    const messages = reducer.disposeSession(session)
    for (const bridge of bridges.values()) {
      for (const message of messages) bridge.send(message)
    }
  }, { global: true })

  const unwatch = settings.watch((next) => {
    reducer = new CompanionReducer({ includeSubagents: false })
    void syncRuntimes(publicConfig(next)).catch((error) => {
      logger.warn?.(`dsh-pet-indesktop runtime sync failed: ${String(error)}`)
    })
  })

  if (typeof ctx.inject === 'function') {
    ctx.inject(['webServer'], (httpCtx) => {
      httpCtx.effect(
        () => httpCtx.webServer.register({
          kind: 'exact',
          path: CONFIG_ENDPOINT,
          handler: createConfigHandler(settings),
        }),
        'dsh-pet-indesktop: local settings endpoint',
      )
    })
  }

  ctx.effect(() => () => {
    offEvent?.()
    offDisposed?.()
    unwatch()
    for (const bridge of bridges.values()) bridge.stop('dsh-host-stop')
    bridges.clear()
  })
}

export function apply(ctx, config = {}) {
  if (typeof ctx.inject === 'function') {
    ctx.inject(['settings'], (settingsCtx) => mount(settingsCtx, config, ctx))
    return
  }
  mount(ctx, config)
}

export {
  CompanionMessageKind,
  CompanionReducer,
  CompanionState,
  HelperProcess,
}
