"""WebSocket 长连接:握手鉴权、心跳、事件推送。

对应需求文档 Phase 3:推送携带 prev_seq,客户端校验连续性,发现缺口调用 GET /api/v1/sync 补拉。
业务上行动作一律走 REST,WS 仅承载下行推送与 ping/pong 心跳。
"""

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from app.core import security
from app.db.base import SessionLocal
from app.models import User
from app.services.connection_manager import manager

router = APIRouter(tags=["WebSocket"])


class Ping(BaseModel):
    type: str


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default="")):
    db = SessionLocal()
    user_id = 0
    try:
        if not token:
            await websocket.close(code=4401)
            return
        try:
            user_id = security.decode_token(token)
        except jwt.InvalidTokenError:
            await websocket.close(code=4401)
            return
        user = db.get(User, user_id)
        if user is None:
            await websocket.close(code=4401)
            return

        await manager.connect(user_id, websocket)
        await websocket.send_json({"type": "connected", "data": {"user_id": user_id}})
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = Ping.model_validate_json(raw)
                except ValidationError:
                    await websocket.send_json({"type": "error", "message": "仅支持 {\"type\":\"ping\"}"})
                    continue
                if msg.type == "ping":
                    await websocket.send_json({"type": "pong"})
                else:
                    await websocket.send_json({"type": "error", "message": "未知消息类型,业务操作请走 REST 接口"})
        except WebSocketDisconnect:
            pass
    finally:
        if user_id:
            manager.disconnect(user_id, websocket)
        db.close()