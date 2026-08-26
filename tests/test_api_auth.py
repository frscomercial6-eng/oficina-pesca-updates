from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_login_and_protected_routes_work():
    seed_resp = client.post(
        "/seed/admin",
        json={"nome": "Admin Teste", "email": "admin@teste.local", "senha": "123456", "perfil": "admin"},
    )
    assert seed_resp.status_code == 200

    login_resp = client.post(
        "/auth/login",
        json={"email": "admin@teste.local", "senha": "123456"},
    )
    assert login_resp.status_code == 200
    payload = login_resp.json()
    assert "access_token" in payload
    assert payload["token_type"] == "bearer"

    protected_resp = client.get(
        "/clientes",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert protected_resp.status_code == 200

    no_auth_resp = client.get("/clientes")
    assert no_auth_resp.status_code == 401
