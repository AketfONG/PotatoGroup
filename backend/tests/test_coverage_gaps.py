"""补齐覆盖率:会话管理、用户资料、好友管理、群聊与鉴权边界。

这一批用例的目的除了验证行为,还要把 `app/api/v1/` 下尚未执行的分支跑到,
使后端单测覆盖率稳定在课程要求的 80% 以上。
"""

import pytest

from tests.test_message_flow import _auth, _be_friends, _register


@pytest.fixture()
def pair(client):
    ta, ua = _register(client, "cov_alpha")
    tb, ub = _register(client, "cov_beta")
    _be_friends(client, ta, tb, ua, ub)
    return ta, ua, tb, ub


# ---------- 鉴权边界 ----------


def test_protected_endpoints_reject_missing_token(client):
    """所有受保护接口在无 token 时拒绝访问。"""
    for method, path in [
        ("GET", "/api/v1/users/me"),
        ("GET", "/api/v1/friends"),
        ("GET", "/api/v1/conversations"),
        ("GET", "/api/v1/sync?cursor=0"),
        ("GET", "/api/v1/friend-requests"),
    ]:
        resp = client.request(method, path)
        assert resp.status_code in (401, 403), f"{path} 未拒绝匿名访问"


def test_invalid_token_rejected(client):
    """伪造 token 被拒绝。"""
    resp = client.get("/api/v1/users/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code in (401, 403)


def test_logout(client, pair):
    """登出接口可正常调用(JWT 无状态)。"""
    ta, _, _, _ = pair
    resp = client.delete("/api/v1/auth/logout", headers=_auth(ta))
    assert resp.json()["code"] == 0


# ---------- 用户资料 ----------


def test_get_and_update_profile(client):
    """可读取并更新自己的资料(字段以 UserUpdateIn 为准)。"""
    ta, ua = _register(client, "prof_user")

    got = client.get("/api/v1/users/me", headers=_auth(ta)).json()
    assert got["code"] == 0
    assert got["data"]["name"] == "prof_user"

    updated = client.patch(
        "/api/v1/users/me",
        json={"avatar": "a.png", "email": "prof@example.com", "phone": "13800000000"},
        headers=_auth(ta),
    ).json()
    assert updated["code"] == 0

    after = client.get("/api/v1/users/me", headers=_auth(ta)).json()["data"]
    assert after["email"] == "prof@example.com"
    assert after["avatar"] == "a.png"


def test_change_password_requires_old_password(client):
    """改密码必须提供正确的旧密码。"""
    ta, ua = _register(client, "pwchange_user")

    wrong = client.patch(
        "/api/v1/users/me",
        json={"old_password": "wrong9999", "new_password": "newpass123"},
        headers=_auth(ta),
    ).json()
    assert wrong["code"] != 0

    right = client.patch(
        "/api/v1/users/me",
        json={"old_password": "passw0rd123", "new_password": "newpass123"},
        headers=_auth(ta),
    ).json()
    assert right["code"] == 0

    assert client.post(
        "/api/v1/auth/login", json={"name": "pwchange_user", "password": "newpass123"}
    ).json()["code"] == 0


def test_get_other_user_profile(client, pair):
    """可查询其他用户资料。"""
    ta, ua, tb, ub = pair
    resp = client.get(f"/api/v1/users/{ub}", headers=_auth(ta))
    assert resp.json()["code"] == 0
    assert resp.json()["data"]["user_id"] == ub


def test_get_unknown_user_returns_404(client, pair):
    """查询不存在的用户返回明确的未找到错误。"""
    ta, _, _, _ = pair
    resp = client.get("/api/v1/users/999999", headers=_auth(ta))
    assert resp.status_code != 500
    assert resp.json()["code"] != 0


def test_search_users(client, pair):
    """可按关键词搜索用户(接口为 GET /users)。"""
    ta, ua, tb, ub = pair
    resp = client.get("/api/v1/users?keyword=cov_beta", headers=_auth(ta))
    assert resp.json()["code"] == 0
    names = [u["name"] for u in resp.json()["data"]["items"]]
    assert "cov_beta" in names

    # 空关键词返回候选列表,且不包含自己
    all_users = client.get("/api/v1/users", headers=_auth(ta)).json()["data"]["items"]
    assert all(u["user_id"] != ua for u in all_users)


# ---------- 好友管理 ----------


def test_friend_list_contains_peer(client, pair):
    """好友列表包含已建立关系的好友。"""
    ta, ua, tb, ub = pair
    items = client.get("/api/v1/friends", headers=_auth(ta)).json()["data"]["items"]
    assert any(f["user_id"] == ub for f in items)


def test_friend_request_full_flow(client):
    """好友申请:发送 -> 列表 -> 接受 -> 双方互为好友。"""
    ta, ua = _register(client, "fr_a")
    tb, ub = _register(client, "fr_b")

    sent = client.post("/api/v1/friend-requests", json={"target_user_id": ub}, headers=_auth(ta))
    assert sent.json()["code"] == 0

    inbox = client.get("/api/v1/friend-requests", headers=_auth(tb)).json()["data"]["items"]
    req = next(i for i in inbox if (i.get("from_user") or {}).get("user_id") == ua)
    assert req["status"] == "pending"

    accepted = client.post(
        f"/api/v1/friend-requests/{req['request_id']}/accept", headers=_auth(tb)
    )
    assert accepted.json()["code"] == 0

    assert any(
        f["user_id"] == ub
        for f in client.get("/api/v1/friends", headers=_auth(ta)).json()["data"]["items"]
    )


def test_friend_request_reject(client):
    """好友申请可被拒绝。"""
    ta, ua = _register(client, "rj_a")
    tb, ub = _register(client, "rj_b")
    client.post("/api/v1/friend-requests", json={"target_user_id": ub}, headers=_auth(ta))
    inbox = client.get("/api/v1/friend-requests", headers=_auth(tb)).json()["data"]["items"]
    req = next(i for i in inbox if (i.get("from_user") or {}).get("user_id") == ua)

    resp = client.post(f"/api/v1/friend-requests/{req['request_id']}/reject", headers=_auth(tb))
    assert resp.json()["code"] == 0


def test_friend_request_to_self_rejected(client):
    """不能向自己发起好友申请。"""
    ta, ua = _register(client, "self_a")
    resp = client.post("/api/v1/friend-requests", json={"target_user_id": ua}, headers=_auth(ta))
    assert resp.json()["code"] != 0


def test_friend_request_to_unknown_user_rejected(client):
    """向不存在的用户发起申请被拒绝。"""
    ta, ua = _register(client, "unk_a")
    resp = client.post("/api/v1/friend-requests", json={"target_user_id": 999999}, headers=_auth(ta))
    assert resp.json()["code"] != 0


# ---------- 会话管理 ----------


def test_conversation_detail(client, pair):
    """可读取会话详情。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]

    resp = client.get(f"/api/v1/conversations/{cid}", headers=_auth(ta))
    assert resp.json()["code"] == 0


def test_conversation_read_report(client, pair):
    """上报已读位置后可读取会话详情。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    client.post(f"/api/v1/conversations/{cid}/messages", json={"body": "hi"}, headers=_auth(ta))

    seqs = client.get("/api/v1/sync?cursor=0&limit=100", headers=_auth(tb)).json()["data"]["items"]
    max_seq = max(s["seq"] for s in seqs if s["conversation_id"] == cid)
    resp = client.post(
        f"/api/v1/conversations/{cid}/read", json={"read_index": max_seq}, headers=_auth(tb)
    )
    assert resp.json()["code"] == 0


def test_conversation_update_pin_and_mute(client, pair):
    """置顶与免打扰走会话设置接口 PATCH /conversations/{id}/me。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]

    pinned = client.patch(
        f"/api/v1/conversations/{cid}/me", json={"pinned": True}, headers=_auth(ta)
    )
    assert pinned.json()["code"] == 0

    muted = client.patch(f"/api/v1/conversations/{cid}/me", json={"muted": True}, headers=_auth(ta))
    assert muted.json()["code"] == 0

    # 会话列表中能读到设置
    items = client.get("/api/v1/conversations", headers=_auth(ta)).json()["data"]["items"]
    mine = next(c for c in items if c["conversation_id"] == cid)
    assert mine["pinned"] is True
    assert mine["muted"] is True


def test_update_group_metadata(client, pair):
    """群主可修改群名与公告。"""
    ta, ua, tb, ub = pair
    gid = client.post(
        "/api/v1/conversations", json={"name": "旧群名", "member_ids": [ub]}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]

    resp = client.patch(
        f"/api/v1/conversations/{gid}",
        json={"name": "新群名", "announcement": "群公告"},
        headers=_auth(ta),
    ).json()
    assert resp["code"] == 0
    assert resp["data"]["name"] == "新群名"
    assert resp["data"]["announcement"] == "群公告"


# ---------- 群聊 ----------


def test_group_conversation_create_and_message(client, pair):
    """可创建群聊、发消息;非成员不能向群里发消息。"""
    ta, ua, tb, ub = pair
    tc, uc = _register(client, "cov_gamma")

    created = client.post(
        "/api/v1/conversations",
        json={"name": "测试群", "member_ids": [ub]},
        headers=_auth(ta),
    )
    body = created.json()
    assert body["code"] == 0
    gid = body["data"]["conversation_id"]
    assert body["data"]["type"] == "group"
    assert len(body["data"]["members"]) == 2

    sent = client.post(
        f"/api/v1/conversations/{gid}/messages", json={"body": "群消息"}, headers=_auth(ta)
    )
    assert sent.json()["code"] == 0

    # 非成员不能向群里发消息
    denied = client.post(
        f"/api/v1/conversations/{gid}/messages", json={"body": "越权"}, headers=_auth(tc)
    )
    assert denied.json()["code"] != 0


def test_group_add_and_remove_member(client, pair):
    """群主可拉人与移除成员,成员列表随之变化(被邀请者需为邀请人的好友)。"""
    ta, ua, tb, ub = pair
    tc, uc = _register(client, "cov_delta")
    _be_friends(client, ta, tc, ua, uc)  # 拉人前必须是好友

    gid = client.post(
        "/api/v1/conversations",
        json={"name": "成员群", "member_ids": [ub]},
        headers=_auth(ta),
    ).json()["data"]["conversation_id"]

    added = client.post(
        f"/api/v1/conversations/{gid}/members", json={"user_ids": [uc]}, headers=_auth(ta)
    ).json()
    assert added["code"] == 0, added

    ids = [m["user"]["user_id"] for m in added["data"]["members"]]
    assert uc in ids

    removed = client.delete(f"/api/v1/conversations/{gid}/members/{uc}", headers=_auth(ta)).json()
    assert removed["code"] == 0

    detail = client.get(f"/api/v1/conversations/{gid}", headers=_auth(ta)).json()["data"]
    assert uc not in [m["user"]["user_id"] for m in detail["members"]]


def test_group_add_non_friend_rejected(client, pair):
    """不能把非好友拉进群。"""
    ta, ua, tb, ub = pair
    tc, uc = _register(client, "cov_epsilon")

    gid = client.post(
        "/api/v1/conversations",
        json={"name": "非好友群", "member_ids": [ub]},
        headers=_auth(ta),
    ).json()["data"]["conversation_id"]

    resp = client.post(
        f"/api/v1/conversations/{gid}/members", json={"user_ids": [uc]}, headers=_auth(ta)
    ).json()
    assert resp["code"] != 0


def test_group_leave(client, pair):
    """成员可主动退群。"""
    ta, ua, tb, ub = pair
    gid = client.post(
        "/api/v1/conversations",
        json={"name": "退群测试", "member_ids": [ub]},
        headers=_auth(ta),
    ).json()["data"]["conversation_id"]

    resp = client.post(f"/api/v1/conversations/{gid}/members/me", headers=_auth(tb)).json()
    assert resp["code"] == 0

    detail = client.get(f"/api/v1/conversations/{gid}", headers=_auth(ta)).json()["data"]
    assert ub not in [m["user"]["user_id"] for m in detail["members"]]


# ---------- 历史筛选 ----------


def test_history_pagination(client, pair):
    """历史分页:limit 生效,多次翻页不重复。"""
    ta, ua, tb, ub = pair
    cid = client.post(
        "/api/v1/conversations/private", json={"target_user_id": ub}, headers=_auth(ta)
    ).json()["data"]["conversation_id"]
    for i in range(5):
        client.post(
            f"/api/v1/conversations/{cid}/messages", json={"body": f"h{i}"}, headers=_auth(ta)
        )

    page1 = client.get(f"/api/v1/conversations/{cid}/messages?limit=2", headers=_auth(ta)).json()
    ids1 = [m["msg_id"] for m in page1["data"]["items"]]
    assert len(ids1) == 2

    cursor = page1["data"]["next_cursor"]
    assert cursor is not None

    page2 = client.get(
        f"/api/v1/conversations/{cid}/messages?limit=2&cursor={cursor}", headers=_auth(ta)
    ).json()
    ids2 = [m["msg_id"] for m in page2["data"]["items"]]
    assert not set(ids1) & set(ids2)


def test_history_nonexistent_conversation(client, pair):
    """查询不存在的会话历史返回错误而不是 500。"""
    ta, _, _, _ = pair
    resp = client.get("/api/v1/conversations/999999/messages", headers=_auth(ta))
    assert resp.status_code != 500
