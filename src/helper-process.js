import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createInterface } from 'node:readline'

import {
  CompanionMessageKind,
  createMessage,
  encodeMessage,
} from './protocol.js'

const here = dirname(fileURLToPath(import.meta.url))
const packageRoot = resolve(here, '..')
const defaultHelperPath = resolve(packageRoot, 'runtime', 'eac_entry.py')
const runtimePath = resolve(packageRoot, 'runtime')
const vendorPath = resolve(runtimePath, 'vendor')

function defaultCommand() {
  if (process.platform !== 'win32') return process.env.DSH_PET_PYTHON || 'python3'
  return process.env.DSH_PET_PYTHON || 'py'
}

function defaultArgs(command, helperPath) {
  if (process.platform === 'win32' && /(^|[\\/])py(?:\.exe)?$/i.test(command)) {
    return ['-3', helperPath]
  }
  return [helperPath]
}

export class HelperProcess {
  constructor(options = {}, logger = console) {
    this.options = options
    this.logger = logger
    this.child = undefined
    this.queue = []
    this.snapshot = new Map()
    this.spawned = false
    this.hasEverSpawned = false
    this.stopping = false
    this.restartSuppressed = false
    this.restartTimer = undefined
    this.heartbeatTimer = undefined
    this.startupTimer = undefined
    this.lastPongAt = 0
    this.readyWaiters = []
    this.exitWaiters = []
  }

  waitForReady(timeoutMs = 30000) {
    if (this.spawned) return Promise.resolve()
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.readyWaiters = this.readyWaiters.filter((entry) => entry !== waiter)
        reject(new Error('helper readiness timed out'))
      }, timeoutMs)
      const waiter = {
        resolve: () => {
          clearTimeout(timer)
          this.readyWaiters = this.readyWaiters.filter((entry) => entry !== waiter)
          resolve()
        },
        reject: (error) => {
          clearTimeout(timer)
          this.readyWaiters = this.readyWaiters.filter((entry) => entry !== waiter)
          reject(error)
        },
      }
      this.readyWaiters.push(waiter)
    })

    }
  waitForExit(timeoutMs = 5000) {
    if (!this.child && !this.spawned) return Promise.resolve()
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.exitWaiters = this.exitWaiters.filter((entry) => entry !== waiter)
        if (this.child) this.child.kill()
        reject(new Error('helper exit timed out'))
      }, timeoutMs)
      const waiter = {
        resolve: () => {
          clearTimeout(timer)
          this.exitWaiters = this.exitWaiters.filter((entry) => entry !== waiter)
          resolve()
        },
      }
      this.exitWaiters.push(waiter)
    })
  }

  start() {
    if (this.child || this.stopping || this.restartSuppressed) return this.child
    const command = this.options.command || defaultCommand()
    const helperPath = this.options.helperPath || defaultHelperPath
    const args = this.options.args || defaultArgs(command, helperPath)
    if (!existsSync(helperPath)) {
      this.logger.warn?.(`dsh-pet-indesktop helper not found: ${helperPath}`)
      return undefined
    }
    const env = { ...process.env, ...this.options.env }
    const pathSeparator = process.platform === 'win32' ? ';' : ':'
    env.PYTHONPATH = [vendorPath, runtimePath, env.PYTHONPATH].filter(Boolean).join(pathSeparator)
    const child = spawn(command, args, {
      cwd: this.options.cwd || packageRoot,
      env,
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    })
    this.child = child
    child.once('spawn', () => {
      const startupTimeoutMs = this.options.startupTimeoutMs ?? 60000
      this.startupTimer = setTimeout(() => {
        if (this.child === child && !this.spawned) {
          this.logger.warn?.('dsh-pet-indesktop helper readiness timed out')
          child.kill()
        }
      }, startupTimeoutMs)
      this.startupTimer.unref?.()
    })
    child.once('error', (error) => {
      this.logger.error?.(`dsh-pet-indesktop helper failed to start: ${error.message}`)
    })
    child.once('exit', (code, signal) => {
      if (this.child !== child) return
            const exitWaiters = this.exitWaiters.splice(0)
      for (const waiter of exitWaiters) waiter.resolve()
this.child = undefined
      this.spawned = false
      this.#clearHeartbeat()
      this.#clearStartupTimer()
      const waiters = this.readyWaiters.splice(0)
      for (const waiter of waiters) waiter.reject(new Error(`helper exited (code=${String(code)}, signal=${String(signal)})`))
      if (!this.stopping && !this.restartSuppressed) {
        this.logger.warn?.(`dsh-pet-indesktop helper exited (code=${String(code)}, signal=${String(signal)}); restarting`)
        this.#scheduleRestart()
      }
    })
    createInterface({ input: child.stdout }).on('line', (line) => this.#handleReply(line))
    createInterface({ input: child.stderr }).on('line', (line) => {
      if (line.trim()) this.logger.warn?.(`dsh-pet-indesktop helper: ${line}`)
    })
    return child
  }

  send(message) {
    this.#remember(message)
    const line = encodeMessage(message)
    if (!this.child || !this.spawned || !this.child.stdin.writable || this.child.stdin.destroyed) {
      this.queue.push(line)
      return
    }
    this.child.stdin.write(line)
  }

  stop(reason = 'plugin-disposed') {
    this.stopping = true
    this.#clearHeartbeat()
    if (this.restartTimer) clearTimeout(this.restartTimer)
    this.restartTimer = undefined
    const child = this.child
    if (!child) return
    if (this.spawned && child.stdin.writable && !child.stdin.destroyed) {
      child.stdin.write(encodeMessage(createMessage(CompanionMessageKind.SHUTDOWN, { reason })))
      child.stdin.end()
    }
    const timer = setTimeout(() => {
      if (this.child === child) child.kill()
    }, this.options.shutdownTimeoutMs ?? 5000)
    timer.unref?.()
  }

  #remember(message) {
    if (message.kind === CompanionMessageKind.HELLO) this.snapshot.set('hello', encodeMessage(message))
    if (message.kind === CompanionMessageKind.STATE) this.snapshot.set('state', encodeMessage(message))
    if (message.kind === CompanionMessageKind.TASK) this.snapshot.set('task', encodeMessage(message))
  }

  #flushSnapshot() {
    const child = this.child
    if (!this.spawned || !child?.stdin.writable || child.stdin.destroyed) return
    const payload = [...this.snapshot.values()].join('')
    if (payload) child.stdin.write(payload)
  }

  #flushQueue() {
    const child = this.child
    if (!this.spawned || !child?.stdin.writable || child.stdin.destroyed) return
    const payload = this.queue.splice(0).join('')
    if (payload) child.stdin.write(payload)
  }

  #handleReply(line) {
    if (!line.trim()) return
    try {
      const reply = JSON.parse(line)
      if (reply?.protocolVersion === 1 && reply.kind === CompanionMessageKind.READY) {
        if (this.spawned) return
        const firstSpawn = !this.hasEverSpawned
        this.hasEverSpawned = true
        this.spawned = true
        this.lastPongAt = Date.now()
        this.#clearStartupTimer()
        const waiters = this.readyWaiters.splice(0)
        for (const waiter of waiters) waiter.resolve()
        if (firstSpawn) this.#flushQueue()
        else {
          this.#flushSnapshot()
          this.#flushQueue()
        }
        this.#startHeartbeat()
        if (this.stopping) this.#endInput(this.child)
        return
      }
      if (reply?.protocolVersion === 1 && reply.kind === CompanionMessageKind.PONG) {
        this.lastPongAt = Date.now()
        return
      }
      if (reply?.protocolVersion === 1 && reply.kind === CompanionMessageKind.CLOSED) {
        this.restartSuppressed = true
        return
      }
      if (reply?.protocolVersion === 1 && reply.kind === CompanionMessageKind.FAREWELL_COMPLETE) {
        return
      }
    } catch {
      // Non-protocol stdout is useful in development logs.
    }
    this.logger.debug?.(`dsh-pet-indesktop helper: ${line}`)
  }

  #startHeartbeat() {
    const heartbeatMs = this.options.heartbeatMs ?? 5000
    if (heartbeatMs <= 0) return
    const timeoutMs = this.options.heartbeatTimeoutMs ?? Math.max(heartbeatMs * 3, 12000)
    this.heartbeatTimer = setInterval(() => {
      const child = this.child
      if (!child || !this.spawned) return
      if (Date.now() - this.lastPongAt > timeoutMs) {
        this.logger.warn?.('dsh-pet-indesktop helper heartbeat timed out')
        child.kill()
        return
      }
      this.send(createMessage(CompanionMessageKind.PING))
    }, heartbeatMs)
    this.heartbeatTimer.unref?.()
  }

  #clearHeartbeat() {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer)
    this.heartbeatTimer = undefined
  }

  #clearStartupTimer() {
    if (this.startupTimer) clearTimeout(this.startupTimer)
    this.startupTimer = undefined
  }

  #scheduleRestart() {
    if (this.restartTimer || this.stopping || this.restartSuppressed) return
    const delay = this.options.restartDelayMs ?? 750
    this.restartTimer = setTimeout(() => {
      this.restartTimer = undefined
      this.start()
    }, delay)
    this.restartTimer.unref?.()
  }

  #endInput(child) {
    if (child.stdin.writable && !child.stdin.destroyed) child.stdin.end()
  }
}
