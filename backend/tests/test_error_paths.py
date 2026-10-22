"""补齐错误路径与边界分支的用例。

这些用例不是为了"凑覆盖率",而是把此前**从未被执行过**的错误处理跑一遍:
错误分支里藏着真实缺陷(例如畸形哈希让 500 而不是 401),不跑就发现不了。

覆盖目标(此前未执行的分支行):
- friends.py    删除好友、好友申请的「不存在 / 已处理 / 非好友」拒绝
- security.py   bcrypt 遇到畸形哈希时的 ValueError 兜底
- errors.py     StarletteHTTPException 的 405 映射
- messages.py   回复目标校验、历史过滤、非法参数
- sync.py       用户链中的非 message 记录(kind=read)
"""

import pytest

from tests.test_message_flow import _auth, _be_friends, _register


@pytest.fixture()
def pair(client):
    """一对好友,返回 (ta, ua, tb, ub)。"""
    ta, ua = _register(client, "err_alpha")
    tb, ub = _register(client, "err_beta")
    _be_friends(client, ta, tb, ua, ub)
    return ta, ua, tb, ub


@pytest.fixture()
def conv(client, pair):
    """pair 之间的单聊 id。"""
    ta, _, _, ub = pair
    resp = client.post("/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta))
    assert resp.json()["code"] == 0, resp.text
    return resp.json()["data"]["conversation_id"]


# ---------- 好友:删除 ----------


def test_delete_friend_removes_both_directions(client, pair):
    """删除好友后,双向关系都消失。"""
    ta, ua, tb, ub = pair

    resp = client.delete(f"/api/v1/friends/{ub}", headers=_auth(ta))
    assert resp.status_code == 200
    assert resp.json()["code"] == 0

    # 两个方向的列表都不应再有对方
    names_a = {f["name"] for f in client.get("/api/v1/friends", headers=_auth(ta)).json()["data"]["items"]}
    names_b = {f["name"] for f in client.get("/api/v1/friends", headers=_auth(tb)).json()["data"]["items"]}
    assert "err_beta" not in names_a
    assert "err_alpha" not in names_b


def test_delete_non_friend_rejected(client, pair):
    """对非好友调用删除返回 404,而不是静默成功。"""
    ta, ua, _, _ = pair
    stranger_token, stranger_id = _register(client, "err_stranger")

    resp = client.delete(f"/api/v1/friends/{stranger_id}", headers=_auth(ta))
    assert resp.status_code == 404
    assert resp.json()["code"] == 1004


# ---------- 好友:申请的错误分支 ----------


def test_friend_request_to_self_rejected(client, pair):
    """不能加自己为好友。"""
    ta, ua, _, _ = pair
    resp = client.post("/api/v1/friend-requests", json={"target_user_id": ua}, headers=_auth(ta))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1001


def test_friend_request_to_missing_user_rejected(client, pair):
    """向不存在的用户发申请返回 404。"""
    ta, _, _, _ = pair
    resp = client.post("/api/v1/friend-requests", json={"target_user_id": 999999}, headers=_auth(ta))
    assert resp.status_code == 404
    assert resp.json()["code"] == 1004


def test_friend_request_to_existing_friend_rejected(client, pair):
    """已是好友时重复申请返回 409。"""
    ta, _, _, ub = pair
    resp = client.post("/api/v1/friend-requests", json={"target_user_id": ub}, headers=_auth(ta))
    assert resp.status_code == 409
    assert resp.json()["code"] == 2002


def test_duplicate_pending_friend_request_rejected(client):
    """已有待处理申请时再次发送返回 409。"""
    ta, _ = _register(client, "err_dup_a")
    tb, ub = _register(client, "err_dup_b")

    first = client.post("/api/v1/friend-requests", json={"target_user_id": ub}, headers=_auth(ta))
    assert first.json()["code"] == 0

    second = client.post("/api/v1/friend-requests", json={"target_user_id": ub}, headers=_auth(ta))
    assert second.status_code == 409
    assert second.json()["code"] == 2002


def test_accept_missing_friend_request_rejected(client, pair):
    """处理不存在的申请返回 404。"""
    _, _, tb, _ = pair
    resp = client.post("/api/v1/friend-requests/999999/accept", headers=_auth(tb))
    assert resp.status_code == 404
    assert resp.json()["code"] == 1004


def test_reject_missing_friend_request_rejected(client, pair):
    """拒绝不存在的申请返回 404。"""
    _, _, tb, _ = pair
    resp = client.post("/api/v1/friend-requests/999999/reject", headers=_auth(tb))
    assert resp.status_code == 404
    assert resp.json()["code"] == 1004


def test_accept_already_handled_request_rejected(client):
    """重复同意同一申请返回 409。"""
    ta, ua = _register(client, "err_again_a")
    tb, ub = _register(client, "err_again_b")

    client.post("/api/v1/friend-requests", json={"target_user_id": ub}, headers=_auth(ta))
    items = client.get("/api/v1/friend-requests", headers=_auth(tb)).json()["data"]["items"]
    req_id = next(i["request_id"] for i in items if i["status"] == "pending")

    first = client.post(f"/api/v1/friend-requests/{req_id}/accept", headers=_auth(tb))
    assert first.json()["code"] == 0

    second = client.post(f"/api/v1/friend-requests/{req_id}/accept", headers=_auth(tb))
    assert second.status_code == 409
    assert second.json()["code"] == 2002


def test_reject_already_handled_request_rejected(client):
    """拒绝已处理的申请返回 409。"""
    ta, _ = _register(client, "err_rj_a")
    tb, ub = _register(client, "err_rj_b")

    client.post("/api/v1/friend-requests", json={"target_user_id": ub}, headers=_auth(ta))
    items = client.get("/api/v1/friend-requests", headers=_auth(tb)).json()["data"]["items"]
    req_id = next(i["request_id"] for i in items if i["status"] == "pending")

    assert client.post(f"/api/v1/friend-requests/{req_id}/reject", headers=_auth(tb)).json()["code"] == 0

    again = client.post(f"/api/v1/friend-requests/{req_id}/reject", headers=_auth(tb))
    assert again.status_code == 409
    assert again.json()["code"] == 2002


# ---------- 安全:畸形哈希 ----------


def test_login_with_corrupt_password_hash_fails_cleanly(client):
    """库中密码哈希损坏时应返回 401,而不是 500。

    bcrypt.checkpw 遇到非 bcrypt 格式的哈希会抛 ValueError;
    security.verify_password 的 except 分支负责把它转成 False。
    """
    from sqlalchemy import select

    from app.core import security
    from app.db.base import engine
    from app.models import User

    from sqlalchemy.orm import Session

    _register(client, "err_corrupt")

    # 直接把哈希改成非法值,模拟数据损坏
    with Session(engine) as s:
        user = s.scalar(select(User).where(User.name == "err_corrupt"))
        assert user is not None
        user.password = "not-a-valid-bcrypt-hash"
        s.commit()

    # 直接验证工具函数的兜底行为,不依赖 HTTP 层
    assert security.verify_password("passw0rd123", "not-a-valid-bcrypt-hash") is False

    resp = client.post("/api/v1/auth/login", json={"name": "err_corrupt", "password": "passw0rd123"})
    assert resp.status_code == 401, f"畸形哈希应返回 401,实际 {resp.status_code}: {resp.text}"
    assert resp.json()["code"] == 1002


# ---------- 框架异常映射 ----------


def test_method_not_allowed_mapped_by_http_handler(client, conv, pair):
    """方法不允许(405)走 StarletteHTTPException 处理器,而不是漏成 500。

    /read 只注册了 POST,用 GET 访问会触发 405。
    """
    ta, _, _, _ = pair
    resp = client.get(f"/api/v1/conversations/{conv}/read", headers=_auth(ta))
    assert resp.status_code == 405, f"期望 405,实际 {resp.status_code}: {resp.text}"
    assert "code" in resp.json()


# ---------- 消息:校验与过滤 ----------


def test_reply_to_missing_message_rejected(client, conv, pair):
    """回复一条不存在的消息返回 400。"""
    ta, _, _, _ = pair
    resp = client.post(
        f"/api/v1/conversations/{conv}/messages",
        json={"body": "回复一条不存在的消息", "reply_to": 999999},
        headers=_auth(ta),
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 1001


def test_reply_to_message_in_other_conversation_rejected(client, pair):
    """不能回复其它会话里的消息。"""
    ta, ua, tb, ub = pair

    conv1 = client.post("/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)).json()["data"]["conversation_id"]
    sent = client.post(f"/api/v1/conversations/{conv1}/messages", json={"body": "第一条"}, headers=_auth(ta)).json()
    msg_id = sent["data"]["msg_id"]

    # 换一个会话
    tc, uc = _register(client, "err_gamma")
    _be_friends(client, ta, tc, ua, uc)
    conv2 = client.post("/api/v1/conversations/private", json={"target_user_id": uc}, headers=_auth(ta)).json()["data"]["conversation_id"]
    assert conv2 != conv1

    resp = client.post(
        f"/api/v1/conversations/{conv2}/messages",
        json={"body": "跨会话回复", "reply_to": msg_id},
        headers=_auth(ta),
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 1001


def test_history_with_all_filters(client, conv, pair):
    """历史接口的 sender_id / 时间过滤分支可执行且结果正确。"""
    ta, ua, tb, ub = pair
    client.post(f"/api/v1/conversations/{conv}/messages", json={"body": "来自 alpha"}, headers=_auth(ta))
    client.post(f"/api/v1/conversations/{conv}/messages", json={"body": "来自 beta"}, headers=_auth(tb))

    by_sender = client.get(f"/api/v1/conversations/{conv}/messages?sender_id={ub}", headers=_auth(ta)).json()
    assert by_sender["code"] == 0
    assert [m["body"] for m in by_sender["data"]["items"]] == ["来自 beta"]

    now = 2**31 - 1
    within = client.get(
        f"/api/v1/conversations/{conv}/messages?start_time=0&end_time={now}&limit=1", headers=_auth(ta)
    ).json()
    assert within["code"] == 0
    assert len(within["data"]["items"]) == 1
    # limit=1 且还有更早消息时,应给出 next_cursor
    assert within["data"]["next_cursor"] is not None

    empty = client.get(f"/api/v1/conversations/{conv}/messages?start_time={now}", headers=_auth(ta)).json()
    assert empty["code"] == 0
    assert empty["data"]["items"] == []


def test_history_cursor_and_invalid_limit(client, conv, pair):
    """游标翻页可用;limit 越界被 schema 拒绝。"""
    ta, _, _, _ = pair
    client.post(f"/api/v1/conversations/{conv}/messages", json={"body": "m1"}, headers=_auth(ta))
    client.post(f"/api/v1/conversations/{conv}/messages", json={"body": "m2"}, headers=_auth(ta))

    page1 = client.get(f"/api/v1/conversations/{conv}/messages?limit=1", headers=_auth(ta)).json()
    cursor = page1["data"]["next_cursor"]
    assert cursor is not None

    page2 = client.get(f"/api/v1/conversations/{conv}/messages?cursor={cursor}&limit=1", headers=_auth(ta)).json()
    assert page2["code"] == 0
    assert page2["data"]["items"][0]["msg_id"] < cursor

    too_big = client.get(f"/api/v1/conversations/{conv}/messages?limit=9999", headers=_auth(ta))
    assert too_big.status_code == 400
    assert too_big.json()["code"] == 1001


def test_read_index_negative_rejected(client, conv, pair):
    """已读位置为负时被 schema 拒绝。"""
    ta, _, _, _ = pair
    resp = client.post(f"/api/v1/conversations/{conv}/read", json={"read_index": -1}, headers=_auth(ta))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1001


def test_read_index_beyond_my_chain_rejected(client, conv, pair):
    """已读位置超过我的用户链最新 seq 时拒绝(块 A 的上限校验,不截断)。

    伪造一个很大的 read_index 若被接受,会把未读一次性清零;而调用方只可能读到
    确实投递给它的条目,越界必然是客户端状态异常或伪造。
    """
    ta, _, _, _ = pair
    resp = client.post(f"/api/v1/conversations/{conv}/read", json={"read_index": 999999999}, headers=_auth(ta))
    assert resp.status_code == 400, resp.text
    assert resp.json()["code"] == 1001


def test_read_index_zero_on_empty_chain_accepted(client, conv, pair):
    """全新会话(我的用户链为空)上报 0 是合法的:0 表示「一条都还没读」。"""
    ta, _, _, _ = pair
    resp = client.post(f"/api/v1/conversations/{conv}/read", json={"read_index": 0}, headers=_auth(ta))
    assert resp.json()["code"] == 0, resp.text


def test_recall_other_users_message_forbidden(client, conv, pair):
    """不能撤回别人发的消息。"""
    ta, _, tb, _ = pair
    sent = client.post(f"/api/v1/conversations/{conv}/messages", json={"body": "alpha 发的"}, headers=_auth(ta)).json()
    msg_id = sent["data"]["msg_id"]

    resp = client.post(f"/api/v1/conversations/{conv}/messages/{msg_id}/recall", headers=_auth(tb))
    assert resp.status_code == 403
    assert resp.json()["code"] == 1003


def test_recall_missing_message_rejected(client, conv, pair):
    """撤回不存在的消息返回 404。"""
    ta, _, _, _ = pair
    resp = client.post(f"/api/v1/conversations/{conv}/messages/999999/recall", headers=_auth(ta))
    assert resp.status_code == 404
    assert resp.json()["code"] == 1004


# ---------- 同步:非 message 记录 ----------


def test_sync_returns_read_command_payload(client, pair, conv):
    """用户链里的 read 记录应带 payload 返回,而不是被当成消息去查 message 表。

    这条专门覆盖 sync.py 中 kind != "message" 的分支。

    注意两点(块 A 语义):
    1. read_index 不得超过我的用户链最新 seq,所以要用**对方发来的**那条的 seq 上报;
    2. 发送方自己的已读位置在发消息时就已推进到该条,因此不能拿自己发的消息来上报。
    """
    ta, _, tb, _ = pair
    assert client.post(f"/api/v1/conversations/{conv}/messages", json={"body": "先来一条"}, headers=_auth(ta)).json()["code"] == 0
    incoming = client.post(f"/api/v1/conversations/{conv}/messages", json={"body": "对方回一条"}, headers=_auth(tb)).json()
    assert incoming["code"] == 0, incoming

    my_seq = client.get("/api/v1/sync?cursor=0&limit=100", headers=_auth(ta)).json()["data"]["items"]
    read_index = max(it["seq"] for it in my_seq if it["conversation_id"] == conv)
    assert client.post(f"/api/v1/conversations/{conv}/read", json={"read_index": read_index}, headers=_auth(ta)).json()["code"] == 0

    resp = client.get("/api/v1/sync?cursor=0", headers=_auth(ta))
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0

    read_items = [i for i in body["data"]["items"] if i["kind"] == "read"]
    assert read_items, f"未在 /sync 结果中找到 read 记录: {body['data']['items']}"

    item = read_items[-1]
    assert item["data"] is not None, "read 记录应带 payload"
    assert item["data"]["conversation_id"] == conv
    assert item["data"]["read_index"] == read_index


# ---------- 会话:建群与权限 ----------


def _make_group(client, owner_token, member_ids, name="测试群"):
    resp = client.post("/api/v1/conversations", json={"name": name, "member_ids": member_ids}, headers=_auth(owner_token))
    assert resp.json()["code"] == 0, resp.text
    return resp.json()["data"]["conversation_id"]


def test_create_group_with_non_friend_rejected(client, pair):
    """拉非好友进群返回 400。"""
    ta, _, _, _ = pair
    _, stranger_id = _register(client, "err_g_stranger")
    resp = client.post(
        "/api/v1/conversations",
        json={"name": "非法群", "member_ids": [stranger_id]},
        headers=_auth(ta),
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 1001


def test_non_admin_cannot_update_group(client, pair):
    """普通成员改群名被拒(403)。"""
    ta, _, tb, ub = pair
    group = _make_group(client, ta, [ub])

    resp = client.patch(f"/api/v1/conversations/{group}", json={"name": "改名试试"}, headers=_auth(tb))
    assert resp.status_code == 403
    assert resp.json()["code"] == 1003

    # 群主可以改
    ok_resp = client.patch(f"/api/v1/conversations/{group}", json={"name": "正式群名"}, headers=_auth(ta))
    assert ok_resp.json()["code"] == 0
    assert ok_resp.json()["data"]["name"] == "正式群名"


def test_add_member_requires_friendship(client, pair):
    """邀请非好友入群返回 400。"""
    ta, _, _, ub = pair
    group = _make_group(client, ta, [ub])
    _, stranger_id = _register(client, "err_add_stranger")

    resp = client.post(f"/api/v1/conversations/{group}/members", json={"user_ids": [stranger_id]}, headers=_auth(ta))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1001


def test_add_duplicate_member_rejected(client, pair):
    """重复邀请已在群中的成员返回 409。"""
    ta, _, _, ub = pair
    group = _make_group(client, ta, [ub])

    resp = client.post(f"/api/v1/conversations/{group}/members", json={"user_ids": [ub]}, headers=_auth(ta))
    assert resp.status_code == 409
    assert resp.json()["code"] == 2003


def test_add_members_to_private_chat_rejected(client, conv, pair):
    """单聊不能加成员。"""
    ta, _, _, _ = pair
    resp = client.post(f"/api/v1/conversations/{conv}/members", json={"user_ids": [1]}, headers=_auth(ta))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1001


def test_remove_missing_member_rejected(client, pair):
    """移出不在群中的用户返回 404。"""
    ta, _, _, ub = pair
    group = _make_group(client, ta, [ub])
    _, outsider_id = _register(client, "err_outsider")

    resp = client.delete(f"/api/v1/conversations/{group}/members/{outsider_id}", headers=_auth(ta))
    assert resp.status_code == 404
    assert resp.json()["code"] == 1004


def test_leave_group_owner_forbidden(client, pair):
    """群主不能退群,必须先转让。"""
    ta, _, _, ub = pair
    group = _make_group(client, ta, [ub])

    resp = client.post(f"/api/v1/conversations/{group}/members/me", headers=_auth(ta))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1001


def test_update_settings_and_leave_group(client, pair):
    """普通成员可改自己的置顶/免打扰,并可退群。"""
    ta, _, tb, ub = pair
    group = _make_group(client, ta, [ub])

    settings = client.patch(
        f"/api/v1/conversations/{group}/me", json={"pinned": True, "muted": True}, headers=_auth(tb)
    )
    assert settings.json()["code"] == 0

    detail = client.get(f"/api/v1/conversations/{group}", headers=_auth(tb)).json()["data"]
    assert len(detail["members"]) == 2

    left = client.post(f"/api/v1/conversations/{group}/members/me", headers=_auth(tb))
    assert left.json()["code"] == 0

    # 退群后不再能访问该会话
    after = client.get(f"/api/v1/conversations/{group}", headers=_auth(tb))
    assert after.status_code == 403
    assert after.json()["code"] == 1003


def test_group_detail_missing_conversation(client, pair):
    """访问不存在的会话返回 404。"""
    ta, _, _, _ = pair
    resp = client.get("/api/v1/conversations/999999", headers=_auth(ta))
    assert resp.status_code == 404
    assert resp.json()["code"] == 1004


def test_non_member_cannot_read_conversation(client, pair):
    """非成员访问会话返回 403。"""
    ta, _, _, ub = pair
    group = _make_group(client, ta, [ub])
    tc, _ = _register(client, "err_nonmember")

    resp = client.get(f"/api/v1/conversations/{group}/messages", headers=_auth(tc))
    assert resp.status_code == 403
    assert resp.json()["code"] == 1003


# ---------- 注册:用户名空白(已定位的缺陷,见下) ----------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "已知缺陷(属 B 的域,未被修复):errors.py 的 RequestValidationError 处理器把 "
        "exc.errors() 原样塞进响应,而自定义 field_validator 抛 ValueError 时 "
        "ctx['error'] 是 ValueError 对象,JSON 序列化失败 -> 用户收到 500/9001 而非 400/1001。"
        "修复后本用例会 XPASS,届时删掉这个 xfail 标记即可。"
    ),
)
def test_register_blank_name_rejected(client):
    """用户名不能全为空白字符(触发 schema 的 strip 校验)。

    期望 400/1001;当前因上述缺陷返回 500/9001,故标记为 xfail。
    """
    resp = client.post("/api/v1/auth/register", json={"name": "   ", "password": "passw0rd123"})
    assert resp.status_code == 400, f"当前实现返回 {resp.status_code}(缺陷):{resp.text}"
    assert resp.json()["code"] == 1001


def test_register_short_password_rejected(client):
    """密码过短被 schema 拒绝。

    这条与上面形成对照:纯 schema 约束(不含自定义 ValueError)时,
    校验处理器工作正常,返回 400/1001。
    """
    resp = client.post("/api/v1/auth/register", json={"name": "err_shortpw", "password": "x"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 1001
    assert resp.json()["data"], "校验失败时应返回字段级错误详情"

