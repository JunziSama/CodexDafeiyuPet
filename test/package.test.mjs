import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

test('package metadata declares a web client and bundle patch', () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'))
  assert.equal(pkg.name, 'dsh-pet-indesktop')
  assert.equal(pkg.dsh.client.platform, 'web')
  assert.equal(pkg.dsh.bundle.patch, './cordis.patch.yml')
  assert.ok(pkg.dsh.client.inject.includes('@deepseek-ai/dsh-client-ui-slots'))
})

test('runtime assets are present for every required animation category', () => {
  const videos = path.join(root, 'runtime', 'assets', 'characters', 'shenshen', 'videos')
  for (const category of ['idle', 'turn', 'move', 'click', 'drag', 'random']) {
    const dir = path.join(videos, category)
    assert.ok(fs.existsSync(dir), `missing category dir ${category}`)
    assert.ok(fs.readdirSync(dir).some((name) => name.endsWith('.webm')), `no webm in ${category}`)
  }
})

test('Python helper entrypoint is present', () => {
  const entry = path.join(root, 'runtime', 'eac_entry.py')
  assert.ok(fs.existsSync(entry))
  assert.ok(fs.readFileSync(entry, 'utf8').includes('DSH_PET_APP_DIR_NAME'))
})
