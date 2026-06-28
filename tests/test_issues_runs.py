# Persistence + ownership tests for issues and runs.
#
# Uses the in-memory `client` fixture. The Stage 2 dispatch + Chairman judge are
# monkeypatched so no provider APIs are ever hit.

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _auth(client, email):
    # Register a user and return an Authorization header dict.
    resp = client.post("/auth/register", json={"email": email, "password": "supersecret1"})
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


_ISSUE_PAYLOAD = {
    "title": "App crashes on launch",
    "body": "Null pointer on startup.",
    "label": "bug",
    "confidence": 0.91,
    "severity": None,
    "top_tokens": ["crash", "null"],
    "recommendations": [
        {"title": "Reproduce", "detail": "Confirm steps.", "kind": "action"}
    ],
}


# --- issues -------------------------------------------------------------------
def test_save_issue_and_owner_isolation(client):
    alice = _auth(client, "alice@example.com")
    bob = _auth(client, "bob@example.com")

    created = client.post("/issues", json=_ISSUE_PAYLOAD, headers=alice)
    assert created.status_code == 201
    issue = created.json()
    assert issue["label"] == "bug"
    assert issue["recommendations"][0]["kind"] == "action"
    issue_id = issue["id"]

    # Alice sees it; Bob does not.
    assert [i["id"] for i in client.get("/issues", headers=alice).json()] == [issue_id]
    assert client.get("/issues", headers=bob).json() == []

    # Bob can't read or delete Alice's issue (404, not 403, to avoid leaking ids).
    assert client.get(f"/issues/{issue_id}", headers=bob).status_code == 404
    assert client.delete(f"/issues/{issue_id}", headers=bob).status_code == 404

    # Alice can fetch and then delete it.
    assert client.get(f"/issues/{issue_id}", headers=alice).status_code == 200
    assert client.delete(f"/issues/{issue_id}", headers=alice).status_code == 204
    assert client.get("/issues", headers=alice).json() == []


def test_anonymous_cannot_save_issue(client):
    assert client.post("/issues", json=_ISSUE_PAYLOAD).status_code == 401


# --- runs ---------------------------------------------------------------------
def _patch_stage2(monkeypatch):
    # Force a deterministic bug triage + fake out the live Stage 2 dispatch/judge.
    from agenclave.api.routes import runs as runs_mod

    monkeypatch.setattr(
        runs_mod,
        "predict_triage",
        lambda title, body="": {
            "label": "bug",
            "label_confidence": 0.9,
            "severity": None,
            "top_tokens": ["crash"],
        },
    )
    monkeypatch.setattr(runs_mod, "build_agents", lambda provider, models: ["agent"])

    async def _fake_dispatch(task, agents):
        return [
            SimpleNamespace(agent_name="claude-sonnet-4-6", ok=True, error=None, patch="diff")
        ]

    class _FakeChairman:
        def __init__(self, model, **kwargs):
            self.model = model

        async def judge(self, task, candidates):
            return SimpleNamespace(
                selected_agent="claude-sonnet-4-6",
                ranking=["claude-sonnet-4-6"],
                rationale="best",
                synthesized_patch=None,
            )

    monkeypatch.setattr(runs_mod, "dispatch", _fake_dispatch)
    monkeypatch.setattr(runs_mod, "Chairman", _FakeChairman)


def test_authenticated_run_persists_and_lists(client, monkeypatch):
    _patch_stage2(monkeypatch)
    alice = _auth(client, "alice@example.com")

    resp = client.post(
        "/runs", json={"title": "Crash", "body": "boom", "live": True}, headers=alice
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ran_live"] is True
    assert body["gate"]["passed"] is True
    assert "run_id" in body
    run_id = body["run_id"]

    listed = client.get("/runs", headers=alice).json()
    assert [r["id"] for r in listed] == [run_id]
    assert listed[0]["ran_live"] is True
    assert listed[0]["gate_passed"] is True

    one = client.get(f"/runs/{run_id}", headers=alice)
    assert one.status_code == 200
    assert one.json()["result"]["selected_patch"] == "diff"


def test_anonymous_run_works_without_persisting(client, monkeypatch):
    # Preserve existing behaviour: anonymous /runs returns the pipeline result and
    # never persists (no run_id, and a fresh user has an empty run list).
    _patch_stage2(monkeypatch)
    resp = client.post("/runs", json={"title": "Crash", "body": "boom", "live": False})
    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" not in body
    assert body["ran_live"] is False

    alice = _auth(client, "alice@example.com")
    assert client.get("/runs", headers=alice).json() == []


def test_run_owner_isolation(client, monkeypatch):
    _patch_stage2(monkeypatch)
    alice = _auth(client, "alice@example.com")
    bob = _auth(client, "bob@example.com")

    resp = client.post(
        "/runs", json={"title": "Crash", "body": "boom", "live": False}, headers=alice
    )
    run_id = resp.json()["run_id"]

    assert client.get("/runs", headers=bob).json() == []
    assert client.get(f"/runs/{run_id}", headers=bob).status_code == 404
