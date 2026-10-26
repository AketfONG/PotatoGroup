/**
 * WebSocket 客户端:握手鉴权、30s 心跳、断线重连、prev_seq 连续性校验。
 *
 * 缺口时调用 /sync 补拉,并通过 onResync 把结果交给 chat store 合并。
 */

import { getToken } from './http'
import { isMockMode } from './index'
import * as api from './index'
import type { SyncOut, WsEvent } from './types'

export type WsHandler = (event: WsEvent) => void
export type ResyncHandler = (out: SyncOut) => void

const HEARTBEAT_INTERVAL_MS = 30_000
const RECONNECT_BASE_DELAY_MS = 1_000
const RECONNECT_MAX_DELAY_MS = 30_000

export class WsClient {
  private ws: WebSocket | null = null
  private handlers = new Set<WsHandler>()
  private resyncHandlers = new Set<ResyncHandler>()
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

  /** 订阅补拉结果(chat store 用此合并消息) */
  onResync(handler: ResyncHandler): () => void {
    this.resyncHandlers.add(handler)
    return () => this.resyncHandlers.delete(handler)
  }

  connect(): void {
    // mock 模式无后端:跳过 WS 连接(数据经 mock REST /sync 轮询语义一致)
    if (isMockMode) return
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
      // 重连后补拉,避免断线期间漏消息
      if (this.localSeq > 0) void this.resync()
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
      /* onclose 会跟随触发 */
    }
  }

  private async handleEvent(event: WsEvent): Promise<void> {
    // docs/02:连续性校验覆盖 message.new / message.recall / read.sync
    if (event.type === 'message.new' || event.type === 'message.recall' || event.type === 'read.sync') {
      const { prev_seq, seq } = event
      if (this.localSeq !== 0 && prev_seq !== this.localSeq) {
        await this.resync()
      } else {
        this.localSeq = seq
      }
    }
  }

  async resync(): Promise<SyncOut> {
    const out = await api.sync(this.localSeq)
    let cursor = out.next_cursor
    while (cursor !== null) {
      const more = await api.sync(cursor)
      out.items.push(...more.items)
      cursor = more.next_cursor
    }
    if (out.items.length > 0) {
      this.localSeq = out.items[out.items.length - 1].seq
    }
    for (const h of this.resyncHandlers) h(out)
    return out
  }

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
    this.localSeq = 0
  }
}

export const wsClient = new WsClient()
