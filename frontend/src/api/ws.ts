/**
 * WebSocket 客户端:握手鉴权、30s 心跳、断线重连、prev_seq 连续性校验。
 *
 * 一致性校验(需求文档 Phase 3):推送携带 prev_seq,若与本地 cursor 不一致,
 * 说明有推送丢失,立即调用 REST GET /sync 补拉,保证消息不丢。
 */

import { getToken, setToken } from './http'
import * as api from './index'
import type { SyncOut, WsEvent } from './types'

export type WsHandler = (event: WsEvent) => void

const HEARTBEAT_INTERVAL_MS = 30_000
const RECONNECT_BASE_DELAY_MS = 1_000
const RECONNECT_MAX_DELAY_MS = 30_000

export class WsClient {
  private ws: WebSocket | null = null
  private handlers = new Set<WsHandler>()
  private heartbeatTimer: number | null = null
  private reconnectTimer: number | null = null
  private reconnectAttempts = 0
  private closedByUser = false
  /** 本地用户链 cursor:已处理的最新 seq */
  localSeq = 0

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  on(handler: WsHandler): () => void {
    this.handlers.add(handler)
    return () => this.handlers.delete(handler)
  }

  connect(): void {
    const token = getToken()
    if (!token) return
    this.closedByUser = false
    this.clearTimers()

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws?token=${token}`)
    this.ws = ws

    ws.onopen = () => {
      this.reconnectAttempts = 0
      this.startHeartbeat()
    }

    ws.onmessage = (raw) => {
      let event: WsEvent
      try {
        event = JSON.parse(String(raw.data)) as WsEvent
      } catch {
        return
      }
      void this.handleEvent(event)
      for (const h of this.handlers) h(event)
    }

    ws.onclose = () => {
      this.stopHeartbeat()
      if (!this.closedByUser) this.scheduleReconnect()
    }

    ws.onerror = () => {
      // onclose 会跟随触发,重连逻辑在那里处理
    }
  }

  private async handleEvent(event: WsEvent): Promise<void> {
    if (event.type === 'message.new' || event.type === 'message.recall') {
      const { prev_seq, seq } = event
      // 首条消息 prev_seq 为 0;之后必须严格衔接本地 cursor
      if (this.localSeq !== 0 && prev_seq !== this.localSeq) {
        await this.resync()
      } else {
        this.localSeq = seq
      }
    }
  }

  /** 断线补拉:从本地 cursor 起增量同步用户链 */
  async resync(): Promise<SyncOut> {
    const out = await api.sync(this.localSeq)
    return out
  }

  /** 登录后拉取全量链,初始化 localSeq */
  async initialSync(): Promise<SyncOut> {
    const out = await api.sync(0)
    let cursor: number | null = out.next_cursor
    while (cursor !== null) {
      const more = await api.sync(cursor)
      out.items.push(...more.items)
      cursor = more.next_cursor
    }
    if (out.items.length > 0) this.localSeq = out.items[out.items.length - 1].seq
    return out
  }

  private startHeartbeat(): void {
    this.heartbeatTimer = window.setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, HEARTBEAT_INTERVAL_MS)
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  private scheduleReconnect(): void {
    const delay = Math.min(RECONNECT_BASE_DELAY_MS * 2 ** this.reconnectAttempts, RECONNECT_MAX_DELAY_MS)
    this.reconnectAttempts += 1
    this.reconnectTimer = window.setTimeout(() => this.connect(), delay)
  }

  private clearTimers(): void {
    this.stopHeartbeat()
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  disconnect(): void {
    this.closedByUser = true
    this.clearTimers()
    this.ws?.close()
    this.ws = null
  }
}

/** 全局单例 */
export const wsClient = new WsClient()