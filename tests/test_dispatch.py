# Tests for parallel dispatch: order preserved, failures captured not raised.

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.harness.dispatch import dispatch  # noqa: E402
from agenclave.harness.interfaces import Agent, PatchResult, Task  # noqa: E402


class _FakeAgent(Agent):
    def __init__(self, name, *, patch="", error=None, raises=False):
        self.name = name
        self._patch = patch
        self._error = error
        self._raises = raises

    async def propose_patch(self, task: Task) -> PatchResult:
        if self._raises:
            raise RuntimeError("boom")
        return PatchResult(
            agent_name=self.name,
            instance_id=task.instance_id,
            patch=self._patch,
            error=self._error,
        )


def _task():
    return Task(instance_id="i1", repo="o/r", problem_statement="fix it")


async def test_dispatch_preserves_order_and_results():
    agents = [
        _FakeAgent("a", patch="--- a\n+++ b\n"),
        _FakeAgent("b", error="api down"),
        _FakeAgent("c", patch="--- c\n+++ d\n"),
    ]
    results = await dispatch(_task(), agents)
    assert [r.agent_name for r in results] == ["a", "b", "c"]
    assert results[0].ok
    assert not results[1].ok  # error captured
    assert results[2].ok


async def test_dispatch_captures_raised_exception():
    agents = [_FakeAgent("a", patch="--- a\n+++ b\n"), _FakeAgent("bad", raises=True)]
    results = await dispatch(_task(), agents)
    assert results[0].ok
    assert not results[1].ok
    assert "boom" in (results[1].error or "")
    assert results[1].agent_name == "bad"


async def test_dispatch_requires_agents():
    with pytest.raises(ValueError):
        await dispatch(_task(), [])
