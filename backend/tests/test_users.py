"""B 角色：个人资料、搜索、注销、置顶/免打扰接口。"""

API = "/api/v1"


def _create_user(client, name: str, password: str = "abc12345") -> tuple[int, dict[str, str]]:
    register = client.post(f"{API}/auth/register", json={"name": name, "password": password})
    assert register.status_code == 201, register.text
    user_id = register.json()["data"]["user_id"]
    login = client.post(f"{API}/auth/login", json={"name": name, "password": password})
    assert login.status_code == 200, login.text
    return user_id, {"Authorization": f"Bearer {login.json()['data']['token']}"}


def _make_friends(client, a: tuple[int, dict[str, str]], b: tuple[int, dict[str, str]]) -> None:
    a_id, a_headers = a
    b_id, b_headers = b
    request = client.post(
        f"{API}/friend-requests",
        headers=a_headers,
        json={"target_user_id": b_id},
    )
    assert request.status_code == 201, request.text
    requests = client.get(f"{API}/friend-requests", headers=b_headers)
    assert requests.status_code == 200
    pending = next(item for item in requests.json()["data"]["items"] if item["status"] == "pending")
    accepted = client.post(
        f"{API}/friend-requests/{pending['request_id']}/accept",
        headers=b_headers,
    )
    assert accepted.status_code == 200, accepted.text


def test_profile_update_password_and_search(client):
    user_id, headers = _create_user(client, "土豆")

    updated = client.patch(
        f"{API}/users/me",
        headers=headers,
        json={"name": "土豆二号", "email": "potato@example.com", "phone": "13800000000"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "土豆二号"
    assert updated.json()["data"]["email"] == "potato@example.com"

    # 改密必须校验旧密码，并且新密码要满足与注册相同的强度
    weak = client.patch(
        f"{API}/users/me",
        headers=headers,
        json={"old_password": "abc12345", "new_password": "abcdefgh"},
    )
    assert weak.status_code == 400
    assert weak.json()["code"] == 1001

    no_old = client.patch(
        f"{API}/users/me",
        headers=headers,
        json={"new_password": "newpass123"},
    )
    assert no_old.status_code == 400

    wrong_old = client.patch(
        f"{API}/users/me",
        headers=headers,
        json={"old_password": "wrong1234", "new_password": "newpass123"},
    )
    assert wrong_old.status_code == 400

    changed = client.patch(
        f"{API}/users/me",
        headers=headers,
        json={"old_password": "abc12345", "new_password": "newpass123"},
    )
    assert changed.status_code == 200
    assert client.post(
        f"{API}/auth/login", json={"name": "土豆二号", "password": "abc12345"}
    ).status_code == 401
    assert client.post(
        f"{API}/auth/login", json={"name": "土豆二号", "password": "newpass123"}
    ).status_code == 200

    # 另一个用户不能改成已存在的用户名
    other_id, other_headers = _create_user(client, "地瓜")
    duplicate = client.patch(
        f"{API}/users/me",
        headers=other_headers,
        json={"name": "土豆二号"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == 2001

    found = client.get(f"{API}/users", headers=headers, params={"keyword": "地瓜"})
    assert found.status_code == 200
    assert found.json()["data"]["items"][0]["user_id"] == other_id
    detail = client.get(f"{API}/users/{other_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["name"] == "地瓜"
    assert client.get(f"{API}/users/99999", headers=headers).status_code == 404


def test_settings_and_private_chat_are_scoped_to_members(client):
    a = _create_user(client, "阿土")
    b = _create_user(client, "小豆")
    c = _create_user(client, "路人")
    _make_friends(client, a, b)

    conversation = client.post(
        f"{API}/conversations/private",
        headers=a[1],
        json={"target_user_id": b[0]},
    )
    assert conversation.status_code == 201, conversation.text
    conversation_id = conversation.json()["data"]["conversation_id"]

    settings = client.patch(
        f"{API}/conversations/{conversation_id}/me",
        headers=a[1],
        json={"pinned": True, "muted": True},
    )
    assert settings.status_code == 200

    mine = client.get(f"{API}/conversations", headers=a[1]).json()["data"]["items"]
    item = next(item for item in mine if item["conversation_id"] == conversation_id)
    assert item["pinned"] is True
    assert item["muted"] is True

    forbidden = client.patch(
        f"{API}/conversations/{conversation_id}/me",
        headers=c[1],
        json={"pinned": True},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == 1003


def test_delete_account_requires_password_and_removes_private_chat(client):
    a = _create_user(client, "注销者")
    b = _create_user(client, "保留者")
    _make_friends(client, a, b)

    conversation = client.post(
        f"{API}/conversations/private",
        headers=a[1],
        json={"target_user_id": b[0]},
    )
    conversation_id = conversation.json()["data"]["conversation_id"]
    sent = client.post(
        f"{API}/conversations/{conversation_id}/messages",
        headers=a[1],
        json={"body": "注销前的消息"},
    )
    assert sent.status_code == 201

    no_body = client.delete(f"{API}/users/me", headers=a[1])
    assert no_body.status_code == 400
    assert no_body.json()["code"] == 1001

    wrong = client.request(
        "DELETE", f"{API}/users/me", headers=a[1], json={"password": "wrong1234"}
    )
    assert wrong.status_code == 400
    assert wrong.json()["code"] == 1001

    deleted = client.request(
        "DELETE", f"{API}/users/me", headers=a[1], json={"password": "abc12345"}
    )
    assert deleted.status_code == 200
    assert deleted.json()["code"] == 0

    # 被注销用户不能再次登录；好友关系与私聊都被清理
    assert client.post(
        f"{API}/auth/login", json={"name": "注销者", "password": "abc12345"}
    ).status_code == 401
    assert client.get(f"{API}/friends", headers=b[1]).json()["data"]["items"] == []
    assert client.get(f"{API}/conversations", headers=b[1]).json()["data"]["items"] == []


def test_group_owner_is_transferred_when_account_is_deleted(client):
    a = _create_user(client, "群主")
    b = _create_user(client, "成员")
    _make_friends(client, a, b)

    group = client.post(
        f"{API}/conversations",
        headers=a[1],
        json={"name": "交接测试群", "member_ids": [b[0]]},
    )
    assert group.status_code == 201, group.text
    group_id = group.json()["data"]["conversation_id"]
    sent = client.post(
        f"{API}/conversations/{group_id}/messages",
        headers=a[1],
        json={"body": "群历史保留"},
    )
    assert sent.status_code == 201

    deleted = client.request(
        "DELETE", f"{API}/users/me", headers=a[1], json={"password": "abc12345"}
    )
    assert deleted.status_code == 200

    detail = client.get(f"{API}/conversations/{group_id}", headers=b[1])
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["owner_id"] == b[0]
    assert len(body["members"]) == 1
    assert body["members"][0]["role"] == "owner"

    history = client.get(f"{API}/conversations/{group_id}/messages", headers=b[1])
    assert history.status_code == 200
    assert history.json()["data"]["items"][0]["body"] == "群历史保留"
    assert history.json()["data"]["items"][0]["sender_id"] is None
