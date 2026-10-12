"""WebSocket 长连接管理:userId → 活动连接集合。

对应需求文档"长连接系统"的 registerClient / pushMessage:
- registerClient: connect() 时维护映射;
- pushMessage: push_to_user() 向指定用户的所有端推送(支持多端登录)。
"""

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        # 同一用户可能多端登录,故为连接列表
        self._connections: dict[int, list[WebSocket]] = {}

    @staticmethod
    def _key(user_id: int) -> int:
        return user_id

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(user_id, []).append(websocket)
        logger.info("WS 已连接 user=%s,当前在线连接数=%s", user_id, len(self._connections[user_id]))

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        conns = self._connections.get(user_id)
        if conns and websocket in conns:
            conns.remove(websocket)
        if conns is not None and not conns:
            self._connections.pop(user_id, None)

    def is_online(self, user_id: int) -> bool:
        return bool(self._connections.get(user_id))

    async def push_to_user(self, user_id: int, payload: dict[str, Any]) -> None:
        """向用户所有在线端推送事件;失败连接静默移除(断线由 REST /sync 兜底)。"""
        conns = list(self._connections.get(user_id, []))
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001 - 推送失败不影响业务事务
                logger.warning("推送失败 user=%s,移除连接", user_id)
                self.disconnect(user_id, ws)

    async def push_to_users(self, user_ids: list[int], payload_for: dict[int, dict[str, Any]]) -> None:
        """向多个用户推送各自的事件(payload_for: user_id → 事件体)。"""
        tasks = [self.push_to_user(uid, payload_for[uid]) for uid in user_ids if uid in payload_for]
        if tasks:
            await asyncio.gather(*tasks)


# 全局单例
manager = ConnectionManager()