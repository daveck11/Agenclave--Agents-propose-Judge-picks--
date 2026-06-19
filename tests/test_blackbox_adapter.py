# Mocked unit tests for the BlackBox Agents API adapter.
#
# The two endpoints (`POST /tasks` and `GET /tasks/{id}`) are mocked with
# respx, so these run offline with no `bb_` key. They cover the submit -> poll
# -> result happy path, the failed-task path (error captured, not raised), the
# missing-key guard, and HTTP errors.

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.harness.interfaces import Task  # noqa: E402
from agenclave.harness.providers.blackbox import BlackBoxAgent  # noqa: E402

BASE = "https://blackbox.test/api"


def _task():
    return Task(instance_id="proj__1", repo="proj/lib", problem_statement="null deref")


def _agent():
    # poll_interval=0 keeps the test fast (no real waiting).
    return BlackBoxAgent(
        "blackbox-coder", api_key="bb_test", api_base=BASE, poll_interval=0
    )


@respx.mock
async def test_submit_poll_success():
    respx.post(f"{BASE}/tasks").mock(
        return_value=httpx.Response(200, json={"id": "t1"})
    )
    respx.get(f"{BASE}/tasks/t1").mock(
        side_effect=[
            httpx.Response(200, json={"status": "running"}),
            httpx.Response(
                200,
                json={
                    "status": "completed",
                    "result": "```diff\n--- a/f.py\n+++ b/f.py\n@@\n-x\n+y\n```",
                },
            ),
        ]
    )
    res = await _agent().propose_patch(_task())
    assert res.ok
    assert res.error is None
    assert res.patch.startswith("--- a/f.py")
    assert "+y" in res.patch


@respx.mock
async def test_failed_task_captures_error():
    respx.post(f"{BASE}/tasks").mock(
        return_value=httpx.Response(200, json={"task_id": "t2"})
    )
    respx.get(f"{BASE}/tasks/t2").mock(
        return_value=httpx.Response(200, json={"status": "failed", "error": "OOM"})
    )
    res = await _agent().propose_patch(_task())
    assert not res.ok
    assert "OOM" in (res.error or "")


@respx.mock
async def test_http_error_captured():
    respx.post(f"{BASE}/tasks").mock(return_value=httpx.Response(500, text="boom"))
    res = await _agent().propose_patch(_task())
    assert not res.ok
    assert res.error  # an HTTPStatusError string, not a crash


async def test_missing_key_guarded():
    agent = BlackBoxAgent("blackbox-coder", api_key="", api_base=BASE)
    res = await agent.propose_patch(_task())
    assert not res.ok
    assert "BLACKBOX_API_KEY" in (res.error or "")


@respx.mock
async def test_nested_result_field_extracted():
    respx.post(f"{BASE}/tasks").mock(
        return_value=httpx.Response(200, json={"id": "t3"})
    )
    respx.get(f"{BASE}/tasks/t3").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "done",
                "result": {"output": "--- a/x\n+++ b/x\n@@\n-1\n+2\n"},
            },
        )
    )
    res = await _agent().propose_patch(_task())
    assert res.ok
    assert "+2" in res.patch
