import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import vm from 'node:vm'
import { fileURLToPath } from 'node:url'

const clientPath = fileURLToPath(new URL('../lib/client.js', import.meta.url))
const source = fs.readFileSync(clientPath, 'utf8')

test('settings client registers the independent pet section and card controls', () => {
  let payload = null
  const previousWindow = globalThis.window
  globalThis.window = {
    __ModuleLoader__: {
      load(value) {
        payload = value
      },
    },
  }
  try {
    vm.runInThisContext(source, { filename: path.basename(clientPath) })
  } finally {
    if (previousWindow === undefined) delete globalThis.window
    else globalThis.window = previousWindow
  }

  assert.ok(payload)
  assert.equal(payload.id, 'dsh-pet-indesktop')
  const react = {
    useEffect() {},
    useState(value) { return [value, () => {}] },
    createElement(type, props, ...children) { return { type, props, children } },
  }
  const mod = payload.factory((id) => (id === 'react' ? react : null))
  const registered = []
  const ctx = {
    slots: {
      inject(_name, factory) { factory() },
      register(spec, component) { registered.push({ spec, component }) },
    },
  }
  mod.apply(ctx)
  assert.equal(registered.length, 1)
  assert.deepEqual(registered[0].spec, {
    name: 'settings.section',
    id: 'pet-indesktop-settings',
    order: 9,
    label: registered[0].spec.label,
  })
  assert.equal(registered[0].spec.label(), '独立桌宠')
})
