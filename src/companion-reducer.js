import {
  CompanionMessageKind,
  CompanionState,
  createMessage,
} from './protocol.js'

const stateCopy = Object.freeze({
  [CompanionState.IDLE]: '我在这里待命，等待新任务。',
  [CompanionState.THINKING]: '正在分析和规划下一步。',
  [CompanionState.WORKING]: '正在使用工具执行任务。',
  [CompanionState.WAITING]: '任务需要你确认，我先在这里等着。',
  [CompanionState.SUCCESS]: '这一步完成了。',
  [CompanionState.ERROR]: '刚刚遇到了一点小问题。',
  [CompanionState.DISCONNECTED]: '暂时和 DSH 断开了。',
})

function toolName(event) {
  return String(event?.data?.name ?? event?.data?.message?.name ?? 'tool')
}

function sessionIdOf(session) {
  return String(session?.header?.id ?? session?.id ?? 'unknown-session')
}

function isSubagent(session) {
  return session?.header?.origin === 'subagent'
    || Number(session?.header?.delegationDepth ?? 0) > 0
}

function projectNameOf(session) {
  const cwd = String(session?.header?.cwd ?? session?.cwd ?? '')
  const parts = cwd.split(/[\\/]/).filter(Boolean)
  const candidate = parts.length > 0 ? parts[parts.length - 1] : String(session?.header?.title ?? '')
  return candidate.slice(0, 60) || undefined
}

/**
 * Minimal EAC session-event reducer for the independent desktop pet.
 * It intentionally does not depend on dsh-dafeiyu.
 */
export class CompanionReducer {
  constructor({ includeSubagents = false } = {}) {
    this.includeSubagents = includeSubagents
    this.sessions = new Map()
    this.clock = 0
  }

  handle(session, event) {
    if (!event || typeof event.type !== 'string') return []
    if (!this.includeSubagents && isSubagent(session)) return []

    const sessionId = sessionIdOf(session)
    let record = this.sessions.get(sessionId)
    if (!record) {
      record = { id: sessionId, openTools: new Set(), project: projectNameOf(session) }
      this.sessions.set(sessionId, record)
    }
    record.lastSeq = Number(event.seq ?? record.lastSeq ?? 0)
    record.project = projectNameOf(session) || record.project

    switch (event.type) {
      case 'turn/start':
        record.turnActive = true
        if (!(record.openTools instanceof Set)) record.openTools = new Set()
        record.openTools.clear()
        record.task = undefined
        return [this.#state(sessionId, record, CompanionState.THINKING, 'turn-start', '准备阶段')]

      case 'step/start':
      case 'assistant/chunk':
      case 'assistant/message':
        if (!record.turnActive || record.openTools.size > 0) return []
        return [this.#state(sessionId, record, CompanionState.THINKING, event.type, '分析阶段')]

      case 'tool/call': {
        if (!(record.openTools instanceof Set)) record.openTools = new Set()
        const callId = String(event.data?.callId ?? `seq-${String(event.seq ?? 'unknown')}`)
        record.openTools.add(callId, toolName(event))
        return [this.#state(sessionId, record, CompanionState.WORKING, 'tool-call', '执行工具')]
      }

      case 'tool/result': {
        const callId = String(event.data?.message?.toolCallId
          ?? event.data?.message?.callId
          ?? event.data?.callId
          ?? '')
        if (callId) record.openTools.delete(callId)
        const state = record.openTools.size > 0 ? CompanionState.WORKING : CompanionState.THINKING
        if (event.data?.error) {
          return [
            createMessage(CompanionMessageKind.PULSE, {
              sessionId,
              sourceSeq: event.seq,
              state: CompanionState.ERROR,
              ttlMs: 1800,
              resumeState: state,
              message: stateCopy[CompanionState.ERROR],
              detail: record.project,
            }),
          ]
        }
        return [this.#state(sessionId, record, state, 'tool-result', '整理阶段')]
      }

      case 'todo/write': {
        const todos = Array.isArray(event.data?.todos) ? event.data.todos : []
        const current = todos.find((todo) => todo?.status === 'in_progress')
          ?? todos.find((todo) => todo?.status === 'pending')
        const task = current?.content ? String(current.content).slice(0, 120) : undefined
        if (!task || task === record.task) return []
        record.task = task
        return [createMessage(CompanionMessageKind.TASK, {
          sessionId,
          sourceSeq: event.seq,
          task,
          message: task,
          detail: record.project,
        })]
      }

      case 'turn/end': {
        record.turnActive = false
        record.openTools.clear()
        const kind = String(event.data?.reason?.kind ?? 'completed')
        if (kind === 'blocked') {
          return [this.#state(sessionId, record, CompanionState.WAITING, 'turn-end', '等待确认')]
        }
        if (kind === 'aborted') {
          return [this.#state(sessionId, record, CompanionState.IDLE, 'turn-end', '已停止')]
        }
        if (kind !== 'completed') {
          return [this.#state(sessionId, record, CompanionState.ERROR, 'turn-end', '需要处理')]
        }
        return [
          this.#state(sessionId, record, CompanionState.SUCCESS, 'turn-end', '任务完成'),
          createMessage(CompanionMessageKind.STATE, {
            sessionId,
            sourceSeq: event.seq,
            state: CompanionState.IDLE,
            phase: 'turn-end',
            stage: '待命',
            message: stateCopy[CompanionState.IDLE],
            detail: record.project,
            resumeAfterMs: 1600,
          }),
        ]
      }

      default:
        return []
    }
  }

  disposeSession(session) {
    const sessionId = sessionIdOf(session)
    if (!this.sessions.delete(sessionId)) return []
    return [this.#state(sessionId, undefined, CompanionState.IDLE, 'session-disposed', '待命')]
  }

  #state(sessionId, record, state, phase, stage) {
    record = record || { id: sessionId, openTools: new Set() }
    record.state = state
    return createMessage(CompanionMessageKind.STATE, {
      sessionId,
      sourceSeq: record.lastSeq,
      state,
      phase,
      stage,
      message: stateCopy[state],
      detail: record.project,
    })
  }
}
