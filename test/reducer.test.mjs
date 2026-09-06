import assert from 'node:assert/strict'
import test from 'node:test'

import { CompanionReducer } from '../src/companion-reducer.js'
import { CompanionMessageKind, CompanionState } from '../src/protocol.js'

const session = {
  header: { id: 'session-1', cwd: 'C:\\work\\demo', delegationDepth: 0 },
}

test('tool call maps to WORKING and tool result returns to THINKING', () => {
  const reducer = new CompanionReducer()
  let messages = reducer.handle(session, { type: 'turn/start', seq: 1 })
  assert.equal(messages[0].kind, CompanionMessageKind.STATE)
  assert.equal(messages[0].state, CompanionState.THINKING)

  messages = reducer.handle(session, {
    type: 'tool/call', seq: 2, data: { callId: 'c1', name: 'bash' },
  })
  assert.equal(messages[0].state, CompanionState.WORKING)

  messages = reducer.handle(session, {
    type: 'tool/result', seq: 3, data: { message: { toolCallId: 'c1' } },
  })
  assert.equal(messages[0].state, CompanionState.THINKING)
})

test('turn end states cover completed, blocked and aborted', () => {
  const reducer = new CompanionReducer()
  reducer.handle(session, { type: 'turn/start', seq: 1 })

  let messages = reducer.handle(session, {
    type: 'turn/end', seq: 2, data: { reason: { kind: 'blocked' } },
  })
  assert.equal(messages[0].state, CompanionState.WAITING)

  reducer.handle(session, { type: 'turn/start', seq: 3 })
  messages = reducer.handle(session, {
    type: 'turn/end', seq: 4, data: { reason: { kind: 'aborted' } },
  })
  assert.equal(messages[0].state, CompanionState.IDLE)

  reducer.handle(session, { type: 'turn/start', seq: 5 })
  messages = reducer.handle(session, {
    type: 'turn/end', seq: 6, data: { reason: { kind: 'completed' } },
  })
  assert.equal(messages[0].state, CompanionState.SUCCESS)
  assert.equal(messages[1].state, CompanionState.IDLE)
})
