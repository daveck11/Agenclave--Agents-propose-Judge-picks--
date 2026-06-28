# Auth flow tests: register -> login -> /auth/me, plus the error paths.
#
# Uses the in-memory `client` fixture (see conftest.py); no real network/DB.

from __future__ import annotations


def _register(client, email="alice@example.com", password="supersecret1"):
    return client.post("/auth/register", json={"email": email, "password": password})


def test_register_login_me_roundtrip(client):
    # Register issues a token + user; login returns one; /auth/me echoes the user.
    resp = _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "alice@example.com"
    assert "id" in body["user"]

    login = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "supersecret1"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"


def test_duplicate_email_conflicts(client):
    assert _register(client).status_code == 201
    dup = _register(client)
    assert dup.status_code == 409


def test_login_bad_password_unauthorized(client):
    assert _register(client).status_code == 201
    resp = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )
    assert resp.status_code == 401


def test_login_unknown_email_unauthorized(client):
    resp = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "whatever12"},
    )
    assert resp.status_code == 401


def test_me_requires_token(client):
    # No Authorization header on a protected route -> 401.
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_garbage_token(client):
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
