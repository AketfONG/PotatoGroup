"""B 角色第一轮：注册、登录、JWT 鉴权、登出、健康检查。"""

API = "/api/v1"


def _register(client, name: str = "土豆", password: str = "abc12345"):
    return client.post(f"{API}/auth/register", json={"name": name, "password": password})


def _login(client, name: str = "土豆", password: str = "abc12345"):
    return client.post(f"{API}/auth/login", json={"name": name, "password": password})


def _auth(client, name: str = "土豆", password: str = "abc12345") -> dict[str, str]:
    assert _register(client, name, password).status_code == 201
    response = _login(client, name, password)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['token']}"}


def test_health(client):
    response = client.get(f"{API}/health")
    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["status"] == "up"


def test_register_login_me_and_logout(client):
    response = _register(client)
    assert response.status_code == 201
    assert response.json()["code"] == 0
    assert response.json()["data"]["user_id"] > 0

    # 重复用户名走业务码 2001
    duplicate = _register(client)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == 2001

    # 自定义校验器的 ValueError 必须被安全序列化，不能变成 500
    weak = _register(client, name="弱密码", password="abcdefgh")
    assert weak.status_code == 400
    assert weak.json()["code"] == 1001
    assert isinstance(weak.json()["data"], list)

    blank_name = _register(client, name="  ", password="abc12345")
    assert blank_name.status_code == 400
    assert blank_name.json()["code"] == 1001

    wrong = _login(client, password="wrong1234")
    assert wrong.status_code == 401
    assert wrong.json()["code"] == 1002

    login = _login(client)
    assert login.status_code == 200
    body = login.json()["data"]
    assert body["token"]
    assert body["user"]["name"] == "土豆"
    assert "password" not in body["user"]

    headers = {"Authorization": f"Bearer {body['token']}"}
    me = client.get(f"{API}/users/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["data"]["name"] == "土豆"
    assert "password" not in me.json()["data"]

    # 未带 token / token 非法都统一返回 1002
    assert client.get(f"{API}/users/me").status_code == 401
    assert client.get(f"{API}/users/me", headers={"Authorization": "Bearer bad-token"}).status_code == 401

    assert client.delete(f"{API}/auth/logout", headers=headers).status_code == 200


def test_websocket_handshake_and_ping(client):
    headers = _auth(client)
    token = headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws?token={token}") as websocket:
        assert websocket.receive_json()["type"] == "connected"
        websocket.send_json({"type": "ping"})
        assert websocket.receive_json()["type"] == "pong"


def test_signed_token_without_valid_sub_is_rejected(client):
    import jwt

    from app.core.config import settings

    # 签名合法但 sub 缺失/为 null/非整数，不能把 KeyError/TypeError/ValueError 变成 500
    for payload in (
        {"exp": 9999999999},
        {"sub": None, "exp": 9999999999},
        {"sub": "not-an-int", "exp": 9999999999},
    ):
        token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
        response = client.get(
            f"{API}/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == 1002
