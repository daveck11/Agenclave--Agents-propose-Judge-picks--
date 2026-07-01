# Mocked unit tests for the BlackBox AI adapter (OpenAI-compatible).
#
# BlackBox's `/chat/completions` endpoint is mocked with respx, so these run
# offline with no `bb_` key. They cover the happy path (diff extracted), a
# non-fenced diff, an API error (captured, not raised), and the missing-key guard.

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.harness.interfaces import Task  # noqa: E402
from agenclave.harness.providers.blackbox import BlackBoxAgent  # noqa: E402

BASE = "https://blackbox.test/v1"


def _task():
    return Task(instance_id="proj__1", repo="proj/lib", problem_statement="null deref")


def _agent():
    return BlackBoxAgent("blackbox/claude-sonnet", api_key="bb_test", api_base=BASE)


def _completion(content: str) -> dict:
    # Minimal OpenAI-compatible chat.completion body the SDK can parse.
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "blackbox/claude-sonnet",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


@respx.mock
async def test_completion_success_fenced_diff():
    respx.post(f"{BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json=_completion("```diff\n--- a/f.py\n+++ b/f.py\n@@\n-x\n+y\n```"),
        )
    )
    res = await _agent().propose_patch(_task())
    assert res.ok
    assert res.error is None
    assert res.patch.startswith("--- a/f.py")
    assert "+y" in res.patch


@respx.mock
async def test_completion_success_raw_diff():
    respx.post(f"{BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200, json=_completion("--- a/x\n+++ b/x\n@@\n-1\n+2\n")
        )
    )
    res = await _agent().propose_patch(_task())
    assert res.ok
    assert "+2" in res.patch


@respx.mock
async def test_api_error_captured():
    # 400 is not retried by the OpenAI SDK, so this captures cleanly and fast.
    respx.post(f"{BASE}/chat/completions").mock(
        return_value=httpx.Response(400, json={"error": {"message": "bad model"}})
    )
    res = await _agent().propose_patch(_task())
    assert not res.ok
    assert res.error  # an APIStatusError string, not a crash


async def test_missing_key_guarded():
    agent = BlackBoxAgent("blackbox/claude-sonnet", api_key="", api_base=BASE)
    res = await agent.propose_patch(_task())
    assert not res.ok
    assert "BLACKBOX_API_KEY" in (res.error or "")
