import assert from 'node:assert/strict'
import test from 'node:test'

import { HelperProcess } from '../src/helper-process.js'
import { CompanionMessageKind, CompanionState, createMessage } from '../src/protocol.js'

test('Python helper starts offscreen and speaks the protocol', { timeout: 60000 }, async () => {
  const bridge = new HelperProcess({
    env: {
      QT_QPA_PLATFORM: 'offscreen',
      DSH_PET_VISIBLE: '1',
      DSH_PET_CARD_ID: 'card-test',
      DSH_PET_SCALE: '0.72',
    },
    startupTimeoutMs: 30000,
  })
  bridge.start()
  await bridge.waitForReady(30000)
  bridge.send(createMessage(CompanionMessageKind.HELLO, {
    state: CompanionState.IDLE,
    visible: true,
    message: 'test hello',
  }))
  bridge.send(createMessage(CompanionMessageKind.STATE, {
    state: CompanionState.WORKING,
    message: 'test working',
  }))
  bridge.send(createMessage(CompanionMessageKind.PING))
  await new Promise((resolve) => setTimeout(resolve, 600))
  bridge.stop('test-complete')
  const deadline = Date.now() + 15000
  while (bridge.spawned && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  assert.equal(bridge.spawned, false)
})
