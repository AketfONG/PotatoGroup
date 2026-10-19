"""冒烟测试:验证测试环境本身可用(表已建、客户端可用、健康检查通过)。"""


def test_health_ok(client):
    """健康检查返回统一包络且状态为 up。"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "up"


def test_database_is_isolated():
    """确认测试没有连到开发库:库文件路径应为临时文件。"""
    from app.core.config import settings

    assert "potato-test-" in settings.database_url
    assert settings.database_url.endswith(".db")
