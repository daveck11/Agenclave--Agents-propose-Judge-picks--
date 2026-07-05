# The curated practice-bug fixtures + their API. These are the self-contained
# bugs the demo loads into the pipeline (Stage 1 triage -> Stage 2 code-fix) as a
# stand-in for a real codebase. Fast and offline.

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.fixtures import get_fixture, list_fixtures  # noqa: E402


def test_registry_has_ten_unique_bug_fixtures():
    fx = list_fixtures()
    assert len(fx) == 10
    assert len({f.id for f in fx}) == 10
    assert all(f.category == "bug" for f in fx)
    assert all(f.title and f.body for f in fx)


def test_each_fixture_points_at_real_files():
    for f in list_fixtures():
        assert f.repo.is_dir(), f.id
        assert (f.repo / f.module).is_file(), f.id
        assert (f.repo / f.test).is_file(), f.id


def test_get_fixture_serves_the_buggy_code():
    f = get_fixture("mutable-default")
    assert f is not None
    assert "into=[]" in f.buggy_code()  # the shipped file is genuinely buggy
    assert get_fixture("does-not-exist") is None


# --- API --------------------------------------------------------------------
def test_fixtures_api_list_and_detail(client):
    listing = client.get("/fixtures")
    assert listing.status_code == 200
    data = listing.json()
    assert len(data) == 10
    assert {"id", "title", "body", "category"} <= set(data[0])

    one = client.get("/fixtures/calc-add")
    assert one.status_code == 200
    body = one.json()
    assert body["module"] == "calc.py"
    assert body["code"].strip()  # the buggy file content is returned

    assert client.get("/fixtures/nope").status_code == 404


def test_fixture_run_feeds_the_file_and_verifies(client, monkeypatch):
    # A fixture run shows the agent the file and verifies each candidate against
    # the fixture's real tests. Triage is forced to `bug` so the gate opens; the
    # dispatch is faked to return a genuinely-correct calc-add patch, and the real
    # verify_patch runs the fixture's tests (no provider call, no reliability write).
    from agenclave.api.routes import runs as runs_mod
    from agenclave.harness.interfaces import PatchResult

    monkeypatch.setattr(
        runs_mod,
        "predict_triage",
        lambda title, body="": {
            "label": "bug",
            "label_confidence": 0.9,
            "severity": None,
            "top_tokens": ["bug"],
        },
    )
    monkeypatch.setattr(runs_mod, "build_agents", lambda provider, models: ["agent"])

    correct = (
        "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n-    return a - b\n+    return a + b\n"
    )

    async def _fake_dispatch(task, agents):
        # The agent must have been shown the fixture's file.
        assert "return a - b" in task.files.get("calc.py", "")
        return [PatchResult(agent_name="gpt", instance_id=task.instance_id, patch=correct)]

    class _FakeChairman:
        def __init__(self, model, **kwargs):
            self.model = model

        async def judge(self, task, candidates):
            from types import SimpleNamespace

            return SimpleNamespace(
                selected_agent="gpt",
                ranking=["gpt"],
                rationale="looks right",
                synthesized_patch=None,
            )

    monkeypatch.setattr(runs_mod, "dispatch", _fake_dispatch)
    monkeypatch.setattr(runs_mod, "Chairman", _FakeChairman)
    recorded = []
    monkeypatch.setattr(
        runs_mod,
        "record_outcome",
        lambda model, category, passed, **k: recorded.append((model, category, passed)),
    )

    resp = client.post(
        "/runs",
        json={
            "title": "add is wrong",
            "body": "add returns a - b",
            "live": True,
            "fixture_id": "calc-add",
        },
    )
    assert resp.status_code == 200
    out = resp.json()
    assert out["fixture"]["id"] == "calc-add"
    verification = out["verification"]
    assert verification and verification[0]["agent"] == "gpt"
    assert verification[0]["applies"] is True
    assert verification[0]["tests_passed"] is True
    assert out["verified_winner"] == "gpt"
    # a fixture run records its verified outcome, so the router builds a real
    # track record as the app is used (non-fixture runs still record nothing).
    assert ("gpt", "bug", True) in recorded
