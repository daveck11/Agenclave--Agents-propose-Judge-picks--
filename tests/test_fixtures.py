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
