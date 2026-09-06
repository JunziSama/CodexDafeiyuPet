#!/usr/bin/env node
/**
 * Install dsh-pet-indesktop into a local dsh profile:
 * copy the project into <profile>/node_modules and add an idempotent
 * patch entry. The host plugin then owns the Python helper process.
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const NAME = 'dsh-pet-indesktop'
const ENTRY_ID = 'pet-indesktop'
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const profile = process.env.DSH_PROFILE || 'web-desktop'
const profileDir = path.join(dshHome, 'profiles', profile)
const targetDir = path.join(profileDir, 'node_modules', NAME)
const patchPath = path.join(profileDir, 'cordis.patch.yml')

if (!fs.existsSync(path.join(profileDir, 'package.json'))) {
  throw new Error(`dsh profile not found: ${profileDir}`)
}

const SKIP = new Set(['.git', 'node_modules', 'backup', 'verification'])
fs.rmSync(targetDir, { recursive: true, force: true })
fs.mkdirSync(targetDir, { recursive: true })
fs.cpSync(projectRoot, targetDir, {
  recursive: true,
  filter: (src) => {
    const rel = path.relative(projectRoot, src)
    if (rel === '') return true
    return !rel.split(path.sep).some((part) => SKIP.has(part))
  },
})

let patch = ''
if (fs.existsSync(patchPath)) patch = fs.readFileSync(patchPath, 'utf8')
if (/^\s*-?\s*id:\s*pet-indesktop\s*$/m.test(patch)) {
  console.log(`patch already contains ${ENTRY_ID}: ${patchPath}`)
} else {
  const block = `\n- insert:\n    - id: ${ENTRY_ID}\n      name: ${NAME}\n`
  patch = patch.replace(/\s*$/, '') + block
  fs.writeFileSync(patchPath, patch, 'utf8')
  console.log(`registered ${ENTRY_ID} in ${patchPath}`)
}

console.log(`installed ${NAME} -> ${targetDir}`)
console.log('restart dsh and refresh the browser page to load the plugin')
