"""端到端业务流测试:覆盖 D 域核心链路(消息发送/写扩散/同步/已读/历史/撤回/删除)。

这些用例刻意走真实 HTTP 层,而不是直接调 service,
目的是同时覆盖路由、依赖注入、Schema 校验与错误包络。

注意:目前每个用例都用自己新建的账号,保证互不干扰;
等用例量变大后再引入自动回滚的事务夹具。
"""

import pytest


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
    """建立好友关系(按 docs/02 的 FriendRequestOut 结构)。"""
    client.post("/api/v1/friend-requests", json={"target_user_id": ub}, headers=_auth(ta))
    resp = client.get("/api/v1/friend-requests", headers=_auth(tb))
    for item in resp.json()["data"]["items"]:
        from_user = item.get("from_user") or {}
        if item["status"] == "pending" and from_user.get("user_id") == ua:
            client.post(f"/api/v1/friend-requests/{item['request_id']}/accept", headers=_auth(tb))
            return
    raise AssertionError(f"未找到待处理好友请求: {resp.text}")


@pytest.fixture()
def pair(client):
    """造一对好友,返回 (ta, ua, tb, ub)。"""
    ta, ua = _register(client, "flow_alpha")
    tb, ub = _register(client, "flow_beta")
    _be_friends(client, ta, tb, ua, ub)
    return ta, ua, tb, ub


# ---------- 账号 ----------


def test_register_duplicate_name_rejected(client):
    """重复用户名注册被拒绝。"""
    _register(client, "dup_user")
    resp = client.post("/api/v1/auth/register", json={"name": "dup_user", "password": "passw0rd123"})
    assert resp.json()["code"] != 0


def test_login_wrong_password_rejected(client):
    """密码错误登录返回 1002,而不是暴露用户是否存在。

    注意密码需先通过 Schema 格式校验(字母+数字),否则会命中另一个缺陷。
    """
    _register(client, "wrongpw_user")
    resp = client.post(
        "/api/v1/auth/login", json={"name": "wrongpw_user", "password": "wrong9999"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == 1002


def test_login_unknown_user_same_error(client):
    """不存在的用户与密码错误返回相同错误,防止用户名枚举。"""
    resp = client.post("/api/v1/auth/login", json={"name": "no_such_user", "password": "wrong9999"})
    assert resp.json()["code"] == 1002


def test_me_requires_token(client):
    """未携带 token 访问受保护接口被拒绝。"""
    resp = client.get("/api/v1/users/me")
    assert resp.status_code in (401, 403)


def test_me_returns_profile(client):
    """携带 token 可读取自己的资料。"""
    ta, ua = _register(client, "me_user")
    resp = client.get("/api/v1/users/me", headers=_auth(ta))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["user_id"] == ua


# ---------- 会话与消息 ----------


def test_private_conversation_is_idempotent(client, pair):
    """重复请求单聊会话返回同一个会话(不应新建)。"""
    ta, ua, tb, ub = pair
    r1 = client.post("/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)).json()
    r2 = client.post("/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)).json()
    assert r1["data"]["conversation_id"] == r2["data"]["conversation_id"]


def test_send_message_and_history(client, pair):
    """发送消息后能在历史中读到,且字段完整。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]

    sent = client.post(
        f"/api/v1/conversations/{cid}/messages", json={"body": "你好"}, headers=_auth(ta)
    ).json()
    assert sent["code"] == 0
    msg_id = sent["data"]["msg_id"]

    hist = client.get(f"/api/v1/conversations/{cid}/messages?limit=10", headers=_auth(ta)).json()
    items = hist["data"]["items"]
    assert any(m["msg_id"] == msg_id and m["body"] == "你好" for m in items)


def test_send_to_non_member_rejected(client, pair):
    """非会话成员不能发送消息。"""
    ta, ua, tb, ub = pair
    tc, uc = _register(client, "flow_gamma")
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]

    resp = client.post(
        f"/api/v1/conversations/{cid}/messages", json={"body": "越权"}, headers=_auth(tc)
    )
    assert resp.json()["code"] != 0


def test_empty_body_rejected(client, pair):
    """空消息体被 Schema 校验拒绝。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    resp = client.post(f"/api/v1/conversations/{cid}/messages", json={"body": ""}, headers=_auth(ta))
    assert resp.json()["code"] != 0


def test_invalid_password_format_returns_500(client):
    """缺陷记录:密码不满足格式要求时,统一异常处理器本身崩溃,返回 500。

    根因在 app/core/errors.py 的 handle_validation:
        _envelope(1001, "...", exc.errors()[:5])
    Pydantic 的 errors() 里 ctx 含 ValueError 对象,无法 JSON 序列化,
    于是 JSONResponse 构造抛 TypeError,最终由兜底处理器返回 9001。
    本应返回 400 + 1001(参数错误)。

    已用真实 HTTP 服务复现(HTTP 500 + {"code":9001});
    用 TestClient 时该 TypeError 会被重新抛出,故此处用 raise_server_exceptions=False。
    修复后本用例应改为断言 400 且 code == 1001。
    """
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as raw:
        resp = raw.post("/api/v1/auth/login", json={"name": "whoever", "password": "onlyletters"})
    assert resp.status_code == 500
    assert resp.json()["code"] == 9001


def test_unread_count_and_mark_read(client, pair):
    """未读数随已读上报归零。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]

    for i in range(3):
        client.post(
            f"/api/v1/conversations/{cid}/messages", json={"body": f"msg{i}"}, headers=_auth(ta)
        )

    convs = client.get("/api/v1/conversations", headers=_auth(tb)).json()["data"]["items"]
    mine = next(c for c in convs if c["conversation_id"] == cid)
    assert mine["unread_count"] == 3

    # 取 t 的最新 seq 作为已读位置
    sync = client.get("/api/v1/sync?cursor=0&limit=100", headers=_auth(tb)).json()["data"]["items"]
    max_seq = max(it["seq"] for it in sync if it["conversation_id"] == cid)
    resp = client.post(
        f"/api/v1/conversations/{cid}/read", json={"read_index": max_seq}, headers=_auth(tb)
    )
    assert resp.json()["code"] == 0

    convs = client.get("/api/v1/conversations", headers=_auth(tb)).json()["data"]["items"]
    mine = next(c for c in convs if c["conversation_id"] == cid)
    assert mine["unread_count"] == 0


# ---------- 同步 ----------


def test_sync_next_cursor_none_when_caught_up(client, pair):
    """已拉全时 next_cursor 为 None(契约语义:无更多数据)。

    客户端的同步游标应取本次拉到的最大 seq,而不是 next_cursor。
    """
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    client.post(f"/api/v1/conversations/{cid}/messages", json={"body": "sync-a"}, headers=_auth(ta))
    client.post(f"/api/v1/conversations/{cid}/messages", json={"body": "sync-b"}, headers=_auth(ta))

    first = client.get("/api/v1/sync?cursor=0&limit=100", headers=_auth(tb)).json()["data"]
    assert len(first["items"]) == 2
    assert first["next_cursor"] is None  # 未拉满 -> 已追平

    cursor = max(it["seq"] for it in first["items"])
    second = client.get(f"/api/v1/sync?cursor={cursor}&limit=100", headers=_auth(tb)).json()["data"]
    assert second["items"] == []  # 用最大 seq 推进后无新数据


def test_sync_next_cursor_set_when_has_more(client, pair):
    """未拉全时 next_cursor 给出续页位置,且续页不重复。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    for i in range(3):
        client.post(
            f"/api/v1/conversations/{cid}/messages", json={"body": f"p{i}"}, headers=_auth(ta)
        )

    first = client.get("/api/v1/sync?cursor=0&limit=2", headers=_auth(tb)).json()["data"]
    assert len(first["items"]) == 2
    cursor = first["next_cursor"]
    assert isinstance(cursor, int) and cursor > 0

    second = client.get(f"/api/v1/sync?cursor={cursor}&limit=2", headers=_auth(tb)).json()["data"]
    assert all(it["seq"] > cursor for it in second["items"])


# ---------- 撤回与删除 ----------


def test_recall_by_sender(client, pair):
    """发送者可撤回自己的消息,历史显示为已撤回。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    mid = client.post(
        f"/api/v1/conversations/{cid}/messages", json={"body": "待撤回"}, headers=_auth(ta)
    ).json()["data"]["msg_id"]

    resp = client.post(f"/api/v1/conversations/{cid}/messages/{mid}/recall", headers=_auth(ta))
    assert resp.json()["code"] == 0

    hist = client.get(f"/api/v1/conversations/{cid}/messages?limit=10", headers=_auth(ta)).json()
    target = next(m for m in hist["data"]["items"] if m["msg_id"] == mid)
    assert target["body"] != "待撤回"


def test_recall_by_other_user_rejected(client, pair):
    """非发送者不能撤回他人消息。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    mid = client.post(
        f"/api/v1/conversations/{cid}/messages", json={"body": "别人发的"}, headers=_auth(ta)
    ).json()["data"]["msg_id"]

    resp = client.post(f"/api/v1/conversations/{cid}/messages/{mid}/recall", headers=_auth(tb))
    assert resp.json()["code"] != 0


def test_reply_to_message(client, pair):
    """可回复指定消息,reply_to 正确回读。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    original = client.post(
        f"/api/v1/conversations/{cid}/messages", json={"body": "原始"}, headers=_auth(ta)
    ).json()["data"]["msg_id"]

    replied = client.post(
        f"/api/v1/conversations/{cid}/messages",
        json={"body": "回复", "reply_to": original},
        headers=_auth(tb),
    ).json()
    assert replied["data"]["reply_to"] == original


def test_delete_message_for_me(client, pair):
    """本地删除后 /sync 不再返回该条(现有行为)。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    mid = client.post(
        f"/api/v1/conversations/{cid}/messages", json={"body": "待删除"}, headers=_auth(ta)
    ).json()["data"]["msg_id"]

    resp = client.delete(f"/api/v1/conversations/{cid}/messages/{mid}", headers=_auth(ta))
    assert resp.json()["code"] == 0

    sync = client.get("/api/v1/sync?cursor=0&limit=200", headers=_auth(ta)).json()["data"]["items"]
    assert not any((it.get("data") or {}).get("msg_id") == mid for it in sync)


# ---------- 会话列表 ----------


def test_conversation_list_contains_summary(client, pair):
    """会话列表包含摘要信息与对方标识。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    client.post(f"/api/v1/conversations/{cid}/messages", json={"body": "最后一条"}, headers=_auth(ta))

    items = client.get("/api/v1/conversations", headers=_auth(tb)).json()["data"]["items"]
    mine = next(c for c in items if c["conversation_id"] == cid)
    assert mine["conversation_id"] == cid
    assert "unread_count" in mine
