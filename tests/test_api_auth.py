# -*- coding: utf-8 -*-
"""Ajustado na Fase A1 (v1.0.64): o bootstrap administrativo passou a ser
protegido por token forte via ambiente (OFP_SEED_ADMIN_TOKEN)."""
import os

os.environ["OFP_SEED_ADMIN_TOKEN"] = "ofp-teste-seed-admin-token-nao-usar-em-producao"

from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402


client = TestClient(app)


def test_login_and_protected_routes_work():
    headers = {"Authorization": f"Bearer {os.environ['OFP_SEED_ADMIN_TOKEN']}"}
    seed_resp = client.post(
        "/seed/admin",
        json={"nome": "Admin Teste", "email": "admin@teste.local", "senha": "123456", "perfil": "admin"},
        headers=headers,
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
