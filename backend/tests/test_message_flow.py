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
    """本地删除:只对我生效,且删除动作本身能被 /sync 表达出来(多端一致)。"""
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
    # 删除后不再以 kind="message" 下发,改由 kind="delete" 墓碑表达
    assert not any(it["kind"] == "message" and (it.get("data") or {}).get("msg_id") == mid for it in sync)
    tombstones = [it for it in sync if it["kind"] == "delete"]
    assert tombstones, f"应能在 /sync 里看到删除标记: {sync}"
    payload = tombstones[-1]["data"]
    assert payload["msg_id"] == mid
    assert payload["conversation_id"] == cid


def test_delete_message_is_local_only(client, pair):
    """本地删除只影响自己:历史、未读、/sync 三处口径一致,对方完全不受影响。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    keep = client.post(
        f"/api/v1/conversations/{cid}/messages", json={"body": "保留"}, headers=_auth(ta)
    ).json()["data"]["msg_id"]
    doomed = client.post(
        f"/api/v1/conversations/{cid}/messages", json={"body": "删掉"}, headers=_auth(ta)
    ).json()["data"]["msg_id"]
    assert client.delete(f"/api/v1/conversations/{cid}/messages/{doomed}", headers=_auth(tb)).json()["code"] == 0

    # 我的历史:删掉的不在,保留的还在
    my_history = client.get(f"/api/v1/conversations/{cid}/messages", headers=_auth(tb)).json()["data"]["items"]
    bodies = [m["body"] for m in my_history]
    assert "删掉" not in bodies
    assert "保留" in bodies

    # 我的未读:只算没删的那条
    items = client.get("/api/v1/conversations", headers=_auth(tb)).json()["data"]["items"]
    mine = next(c for c in items if c["conversation_id"] == cid)
    assert mine["unread_count"] == 1

    # 发送方视角:两条都在,未读不受影响
    ta_history = client.get(f"/api/v1/conversations/{cid}/messages", headers=_auth(ta)).json()["data"]["items"]
    assert {m["msg_id"] for m in ta_history} == {keep, doomed}
    ta_sync = client.get("/api/v1/sync?cursor=0&limit=200", headers=_auth(ta)).json()["data"]["items"]
    assert not any(it["kind"] == "delete" for it in ta_sync)


def test_delete_message_twice_is_idempotent(client, pair):
    """重复删除不报错,也不重复写墓碑。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    mid = client.post(
        f"/api/v1/conversations/{cid}/messages", json={"body": "删两次"}, headers=_auth(ta)
    ).json()["data"]["msg_id"]

    assert client.delete(f"/api/v1/conversations/{cid}/messages/{mid}", headers=_auth(ta)).json()["code"] == 0
    assert client.delete(f"/api/v1/conversations/{cid}/messages/{mid}", headers=_auth(ta)).json()["code"] == 0

    sync = client.get("/api/v1/sync?cursor=0&limit=200", headers=_auth(ta)).json()["data"]["items"]
    assert len([it for it in sync if it["kind"] == "delete"]) == 1


def test_delete_message_clamps_read_index(client, pair):
    """删除排在已读位置之前的消息时,已读位置被回压到它之前,未读不受影响。

    构造要点(踩过两个坑,记下来):
    - 单聊会话按「用户对」去重,换个人建私聊会拿到同一个 conversation,不能用来制造
      「另一个会话里更靠后的 seq」;
    - 发送方自己的已读位置在发消息时就推进到该条,所以必须用**对方发来的**消息把已读位置抬高。

    于是构造为:ta 先发两条,我读掉(已读位置 = 第二条)-> ta 再发第三条(我未读 1 条)
    -> 我删除第一条(排在已读位置之前)。此时若不回压,已读位置会留在一个已变成墓碑的 seq 上。
    """
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    ids = [
        client.post(f"/api/v1/conversations/{cid}/messages", json={"body": f"m{i}"}, headers=_auth(ta)).json()["data"]["msg_id"]
        for i in range(2)
    ]

    first_two = client.get(f"/api/v1/conversations/{cid}/messages", headers=_auth(tb)).json()["data"]["items"]
    read_to = max(m["seq"] for m in first_two)
    assert client.post(
        f"/api/v1/conversations/{cid}/read", json={"read_index": read_to}, headers=_auth(tb)
    ).json()["code"] == 0

    ids.append(
        client.post(f"/api/v1/conversations/{cid}/messages", json={"body": "m2"}, headers=_auth(ta)).json()["data"]["msg_id"]
    )

    convs = client.get("/api/v1/conversations", headers=_auth(tb)).json()["data"]["items"]
    assert next(c for c in convs if c["conversation_id"] == cid)["unread_count"] == 1

    # 删掉最早那条:它的 seq 排在已读位置之前
    assert client.delete(f"/api/v1/conversations/{cid}/messages/{ids[0]}", headers=_auth(tb)).json()["code"] == 0

    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.models import ConversationMember

    with SessionLocal() as db:
        member = db.scalar(
            select(ConversationMember).where(
                ConversationMember.conversation_id == cid,
                ConversationMember.member_user_id == ub,
            )
        )
    assert member is not None
    assert member.read_index < read_to, f"已读位置应被回压,实际 {member.read_index}"

    # 回压的代价:第二条也会重新变成「未读」(未读数 1 -> 2)。这是刻意选的保守方向 ——
    # 多算一条未读只是界面多一个红点,而少算一条会让人漏看消息。
    convs = client.get("/api/v1/conversations", headers=_auth(tb)).json()["data"]["items"]
    assert next(c for c in convs if c["conversation_id"] == cid)["unread_count"] == 2

    # 历史里第一条已消失,其余两条仍在
    remaining = client.get(f"/api/v1/conversations/{cid}/messages", headers=_auth(tb)).json()["data"]["items"]
    assert sorted(m["msg_id"] for m in remaining) == sorted(ids[1:])


def test_delete_message_without_my_delivery_row(client, pair):
    """删除一条我没有投递记录的消息(入群前历史):补写墓碑,不报错。

    这是一条真实的边界:群成员的投递行只在「成为成员之后」才产生,所以新成员去删除
    入群前的历史消息时,用户链上根本没有对应记录,必须补墓碑才能让历史与 /sync 口径一致。
    """
    ta, ua, tb, ub = pair
    # ta 先建群(此时只有 ta 与 ub)
    group = client.post(
        "/api/v1/conversations", json={"name": "历史群", "member_ids": [ub]}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    # 群主在「新成员入群前」发一条,这条不会投递给后来者
    early = client.post(
        f"/api/v1/conversations/{group}/messages", json={"body": "入群前的消息"}, headers=_auth(ta)
    ).json()["data"]["msg_id"]

    tc, uc = _register(client, "flow_latecomer")
    _be_friends(client, ta, tc, ua, uc)  # 拉人前必须是好友
    client.post(f"/api/v1/conversations/{group}/members", json={"user_ids": [uc]}, headers=_auth(ta))

    # 新成员删除这条自己并没有投递记录的消息:应成功,并留下墓碑
    resp = client.delete(f"/api/v1/conversations/{group}/messages/{early}", headers=_auth(tc))
    assert resp.json()["code"] == 0, resp.text

    sync = client.get("/api/v1/sync?cursor=0&limit=200", headers=_auth(tc)).json()["data"]["items"]
    tombstones = [it for it in sync if it["kind"] == "delete"]
    assert [it["data"]["msg_id"] for it in tombstones] == [early]

    # 之后我仍然能正常上报已读(墓碑不会把已读位置卡死)
    assert client.post(
        f"/api/v1/conversations/{group}/read", json={"read_index": 0}, headers=_auth(tc)
    ).json()["code"] == 0


def test_history_carries_my_seq_for_read_report(client, pair):
    """历史里每条消息带上「我的 seq」,客户端据此上报已读(不能用 msg_id)。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    sent = [
        client.post(f"/api/v1/conversations/{cid}/messages", json={"body": f"h{i}"}, headers=_auth(ta)).json()["data"]
        for i in range(3)
    ]

    items = client.get(f"/api/v1/conversations/{cid}/messages", headers=_auth(tb)).json()["data"]["items"]
    assert len(items) == 3
    for m in items:
        # seq 必须是「我的」用户链序号,与全局 msg_id 是两套编号
        assert m["seq"] is not None
        assert m["msg_id"] in {s["msg_id"] for s in sent}

    # 用历史里的 seq 上报已读,未读应清零(这条正是前端 clearUnread 的路径)
    max_seq = max(m["seq"] for m in items)
    assert client.post(
        f"/api/v1/conversations/{cid}/read", json={"read_index": max_seq}, headers=_auth(tb)
    ).json()["code"] == 0
    items_after = client.get("/api/v1/conversations", headers=_auth(tb)).json()["data"]["items"]
    assert next(c for c in items_after if c["conversation_id"] == cid)["unread_count"] == 0


def test_read_index_is_monotonic(client, pair):
    """已读位置只前进:较小的旧值乱序到达时被忽略,接口仍返回成功。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    for i in range(3):
        client.post(f"/api/v1/conversations/{cid}/messages", json={"body": f"m{i}"}, headers=_auth(ta))

    sync = client.get("/api/v1/sync?cursor=0&limit=200", headers=_auth(tb)).json()["data"]["items"]
    seqs = sorted(it["seq"] for it in sync if it["conversation_id"] == cid)
    assert client.post(f"/api/v1/conversations/{cid}/read", json={"read_index": seqs[-1]}, headers=_auth(tb)).json()["code"] == 0

    # 迟到的旧请求:不报错,但已读位置不得回退
    resp = client.post(f"/api/v1/conversations/{cid}/read", json={"read_index": seqs[0]}, headers=_auth(tb))
    assert resp.json()["code"] == 0

    after = client.get("/api/v1/sync?cursor=0&limit=200", headers=_auth(tb)).json()["data"]["items"]
    read_indexes = [it["data"]["read_index"] for it in after if it["kind"] == "read"]
    assert read_indexes == [seqs[-1]], f"不应为回退的旧值再写一条 read 记录: {read_indexes}"

    # 未读仍为 0:回退没有生效
    items = client.get("/api/v1/conversations", headers=_auth(tb)).json()["data"]["items"]
    assert next(c for c in items if c["conversation_id"] == cid)["unread_count"] == 0


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
