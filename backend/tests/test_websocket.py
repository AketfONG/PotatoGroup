"""WebSocket 测试:握手鉴权、心跳、消息推送与连接生命周期。

对应块 T 要求的「WebSocket 测试能力」,同时为块 C(死连接清理)提供验证手段。

关键约束:连接管理器是**模块级单例**(app.services.connection_manager.manager),
必须与 app 共用同一实例,否则推送与连接不在同一个 manager 上,测试会假失败。
本文件因此只通过 `client` 夹具访问应用,不自行构造 app。

推送事件契约(见 message_service, docs/02):
    {"type": "message.new", "seq": <本端新 seq>, "prev_seq": <上一条 seq>, "data": {...}}
客户端比对 prev_seq 与本地游标,不一致即调 GET /api/v1/sync 补拉。
"""

import pytest
from fastapi import WebSocketDisconnect

WS_PATH = "/ws"


def _register(client, name):
    """注册并返回 (token, user_id)。"""
    resp = client.post("/api/v1/auth/register", json={"name": name, "password": "passw0rd123"})
    assert resp.json()["code"] == 0, resp.text
    resp = client.post("/api/v1/auth/login", json={"name": name, "password": "passw0rd123"})
    body = resp.json()
    assert body["code"] == 0, resp.text
    return body["data"]["token"], body["data"]["user"]["user_id"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _be_friends(client, ta, tb, ua, ub):
    """建立好友关系。"""
    client.post("/api/v1/friend-requests", json={"target_user_id": ub}, headers=_auth(ta))
    resp = client.get("/api/v1/friend-requests", headers=_auth(tb))
    for item in resp.json()["data"]["items"]:
        from_user = item.get("from_user") or {}
        if item["status"] == "pending" and from_user.get("user_id") == ua:
            client.post(f"/api/v1/friend-requests/{item['request_id']}/accept", headers=_auth(tb))
            return
    raise AssertionError(f"未找到待处理好友请求: {resp.text}")


def _private_conversation(client, ta, ub):
    """建立单聊,返回 conversation_id。"""
    resp = client.post("/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta))
    assert resp.json()["code"] == 0, resp.text
    return resp.json()["data"]["conversation_id"]


def _send(client, cid, token, body):
    resp = client.post(
        f"/api/v1/conversations/{cid}/messages", json={"body": body}, headers=_auth(token)
    )
    assert resp.json()["code"] == 0, resp.text
    return resp.json()["data"]


@pytest.fixture()
def pair(client):
    ta, ua = _register(client, "ws_alpha")
    tb, ub = _register(client, "ws_beta")
    _be_friends(client, ta, tb, ua, ub)
    return ta, ua, tb, ub


# ---------- 握手鉴权 ----------


def test_ws_rejects_missing_token(client):
    """无 token 时以 4401 关闭,不建立连接。"""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(WS_PATH) as ws:
            ws.receive_json()
    assert exc.value.code == 4401


def test_ws_rejects_invalid_token(client):
    """token 非法时以 4401 关闭。"""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"{WS_PATH}?token=not-a-real-token") as ws:
            ws.receive_json()
    assert exc.value.code == 4401


def test_ws_rejects_token_of_deleted_user(client):
    """token 合法但用户已不存在时,同样以 4401 关闭(不能只验签名)。"""
    token, _uid = _register(client, "ws_ghost")
    assert client.delete("/api/v1/users/me", headers=_auth(token)).json()["code"] == 0
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"{WS_PATH}?token={token}") as ws:
            ws.receive_json()
    assert exc.value.code == 4401


def test_ws_connect_sends_connected_event(client):
    """握手成功后先下发 connected,携带 user_id。"""
    token, uid = _register(client, "ws_conn")
    with client.websocket_connect(f"{WS_PATH}?token={token}") as ws:
        first = ws.receive_json()
    assert first["type"] == "connected"
    assert first["data"]["user_id"] == uid


# ---------- 心跳与非法上行 ----------


def test_ws_ping_pong(client):
    """ping 回 pong(客户端每 30s 发一次,见 docs/02)。"""
    token, _uid = _register(client, "ws_ping")
    with client.websocket_connect(f"{WS_PATH}?token={token}") as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_ws_unknown_type_returns_error(client):
    """未知上行类型返回 error,且连接保持可用(业务动作走 REST)。"""
    token, _uid = _register(client, "ws_unknown")
    with client.websocket_connect(f"{WS_PATH}?token={token}") as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "send_message"})
        assert ws.receive_json()["type"] == "error"
        # 连接未被关闭:仍能收到 pong
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_ws_malformed_json_returns_error(client):
    """非 JSON 或结构不符时返回 error,不崩溃、不断连。"""
    token, _uid = _register(client, "ws_badjson")
    with client.websocket_connect(f"{WS_PATH}?token={token}") as ws:
        ws.receive_json()  # connected
        ws.send_text("not json at all")
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


# ---------- 消息推送 ----------


def test_send_pushes_message_to_recipient(client, pair):
    """A 发消息,B 的在线连接应立刻收到 message.new,且 seq/prev_seq 正确。

    prev_seq 必须等于 B 在本会话链上的上一条 seq:
    客户端靠它发现缺口并调 /sync 补拉,这是可靠性的核心。
    """
    ta, _ua, tb, _ub = pair
    cid = _private_conversation(client, ta, _ub)

    with client.websocket_connect(f"{WS_PATH}?token={tb}") as ws:
        ws.receive_json()  # connected

        sent = _send(client, cid, ta, "推送测试")
        event = ws.receive_json()

    assert event["type"] == "message.new"
    assert event["data"]["body"] == "推送测试"
    assert event["data"]["msg_id"] == sent["msg_id"]
    assert isinstance(event["seq"], int) and event["seq"] > 0
    assert isinstance(event["prev_seq"], int)
    assert event["seq"] > event["prev_seq"], "seq 必须严格递增"


def test_push_prev_seq_is_contiguous_across_messages(client, pair):
    """连续两条消息的 prev_seq 应接上前一条的 seq,不得出现空洞。

    这是客户端连续性校验的依据:prev_seq != 本地游标 时才补拉。
    """
    ta, _ua, tb, _ub = pair
    cid = _private_conversation(client, ta, _ub)

    with client.websocket_connect(f"{WS_PATH}?token={tb}") as ws:
        ws.receive_json()  # connected
        _send(client, cid, ta, "第一条")
        first = ws.receive_json()
        _send(client, cid, ta, "第二条")
        second = ws.receive_json()

    assert second["prev_seq"] == first["seq"], (
        f"prev_seq({second['prev_seq']}) 未接上一条 seq({first['seq']}),"
        "客户端会误判为丢消息而反复全量补拉"
    )
    assert second["seq"] > second["prev_seq"]


def test_sender_also_receives_push(client, pair):
    """发送者在线的其他端也应收到推送(写扩散对每个成员都生效)。"""
    ta, _ua, tb, _ub = pair
    cid = _private_conversation(client, ta, _ub)

    with client.websocket_connect(f"{WS_PATH}?token={ta}") as ws:
        ws.receive_json()  # connected
        _send(client, cid, ta, "自己发的")
        event = ws.receive_json()

    assert event["type"] == "message.new"
    assert event["data"]["body"] == "自己发的"


def test_multidevice_both_connections_receive_push(client, pair):
    """同一用户两端在线时,两端都应收到同一条推送(多端登录)。"""
    ta, ua, tb, _ub = pair
    cid = _private_conversation(client, ta, _ub)

    with client.websocket_connect(f"{WS_PATH}?token={ta}") as ws1:
        ws1.receive_json()  # connected
        with client.websocket_connect(f"{WS_PATH}?token={ta}") as ws2:
            ws2.receive_json()  # connected
            _send(client, cid, tb, "多端推送")
            e1 = ws1.receive_json()
            e2 = ws2.receive_json()

    assert e1["type"] == "message.new"
    assert e2["type"] == "message.new"
    assert e1["data"]["body"] == "多端推送"
    # 两端拿到的是同一条 seq(同一个用户链位置)
    assert e1["seq"] == e2["seq"]


def test_offline_recipient_gets_no_push_and_can_sync(client, pair):
    """对方不在线时不推送,但消息仍在用户链上,可通过 /sync 拉到。

    /sync 是断线补齐的兜底路径,必须覆盖。
    """
    ta, _ua, tb, _ub = pair
    cid = _private_conversation(client, ta, _ub)

    # tb 未连接,直接发送
    _send(client, cid, ta, "离线消息")

    resp = client.get("/api/v1/sync?cursor=0", headers=_auth(tb))
    body = resp.json()
    assert body["code"] == 0, resp.text
    # /sync 条目结构为 {seq, kind, conversation_id, data}(见 app/api/v1/sync.py)
    items = body["data"]["items"]
    assert any(i["kind"] == "message" for i in items), f"离线消息未出现在同步结果中: {items}"
    bodies = [i["data"]["body"] for i in items if i["kind"] == "message" and i["data"]]
    assert "离线消息" in bodies


# ---------- 连接生命周期 ----------


def test_disconnect_removes_connection(client, pair):
    """断开后连接应被移除,不再向其推送(避免死连接长期占用)。

    这里验证的是正常断开路径;块 C 要解决的是「不响应但未断开」的静默死连接。
    """
    from app.services.connection_manager import manager

    ta, ua, tb, _ub = pair
    cid = _private_conversation(client, ta, _ub)

    with client.websocket_connect(f"{WS_PATH}?token={tb}") as ws:
        ws.receive_json()  # connected
        assert manager.is_online(_ub), "连接后应记录为在线"

    assert not manager.is_online(_ub), "断开后不应仍标记为在线"

    # 断开后发送仍应成功(REST 不受影响),只是没有推送
    _send(client, cid, ta, "断开后的消息")


def test_recall_pushes_to_recipient(client, pair):
    """撤回应推送 message.recall 给在线成员。"""
    ta, _ua, tb, _ub = pair
    cid = _private_conversation(client, ta, _ub)

    with client.websocket_connect(f"{WS_PATH}?token={tb}") as ws:
        ws.receive_json()  # connected
        sent = _send(client, cid, ta, "待撤回")
        ws.receive_json()  # 消费 message.new

        recall = client.post(
            f"/api/v1/conversations/{cid}/messages/{sent['msg_id']}/recall", headers=_auth(ta)
        )
        assert recall.json()["code"] == 0, recall.text
        event = ws.receive_json()

    assert event["type"] == "message.recall"
    assert "seq" in event and "prev_seq" in event


# ---------- 推送失败与批量推送(连接管理器直接行为) ----------


def test_push_failure_removes_connection(client, pair):
    """推送抛异常时该连接被静默移除,且不影响其他连接。

    这是当前唯一的死连接回收路径:只有在推送失败时才移除。
    块 C(X9)要补的正是「不响应但未抛错」的静默死连接——
    那些连接目前不会被回收,长期占用连接数。
    """
    import asyncio

    from app.services.connection_manager import manager

    ta, ua, tb, ub = pair
    cid = _private_conversation(client, ta, ub)

    with client.websocket_connect(f"{WS_PATH}?token={ta}") as ws:
        ws.receive_json()  # connected
        assert manager.is_online(ua)

        # 模拟一个已失效的连接:发送时抛错
        class _BrokenWebSocket:
            async def send_json(self, _payload):
                raise RuntimeError("连接已失效")

        manager._connections.setdefault(ua, []).append(_BrokenWebSocket())
        assert len(manager._connections[ua]) == 2, "应有一个正常连接与一个失效连接"

        # 直接触发推送:失效连接被移除,正常连接仍收到
        events = {
            ua: {"type": "message.new", "seq": 1, "prev_seq": 0, "data": {"body": "x"}},
        }
        asyncio.run(manager.push_to_user(ua, events[ua]))

        assert len(manager._connections[ua]) == 1, "失效连接应已被移除"
        assert manager.is_online(ua), "正常连接不应被误删"
        assert ws.receive_json()["type"] == "message.new"


def test_push_to_users_delivers_each_payload(client, pair):
    """push_to_users 按 user_id 分发各自的事件体,两端互不串内容。"""
    import asyncio

    from app.services.connection_manager import manager

    ta, ua, tb, ub = pair
    _cid = _private_conversation(client, ta, ub)

    with client.websocket_connect(f"{WS_PATH}?token={ta}") as ws_a:
        ws_a.receive_json()  # connected
        with client.websocket_connect(f"{WS_PATH}?token={tb}") as ws_b:
            ws_b.receive_json()  # connected

            payloads = {
                ua: {"type": "message.new", "seq": 10, "prev_seq": 9, "data": {"body": "给A"}},
                ub: {"type": "message.new", "seq": 20, "prev_seq": 19, "data": {"body": "给B"}},
            }
            asyncio.run(manager.push_to_users([ua, ub], payloads))

            got_a = ws_a.receive_json()
            got_b = ws_b.receive_json()

    assert got_a["data"]["body"] == "给A" and got_a["seq"] == 10
    assert got_b["data"]["body"] == "给B" and got_b["seq"] == 20
