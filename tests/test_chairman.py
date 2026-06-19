# Tests for the Chairman judge.
#
# The LLM call (`complete_json`) is monkeypatched, so these are offline and
# deterministic. They verify: the degenerate short-circuits (0 / 1 usable
# candidate make no LLM call), and that the judge coerces a model answer to valid
# agent names.

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.harness import chairman as chairman_mod  # noqa: E402
from agenclave.harness.chairman import Chairman  # noqa: E402
from agenclave.harness.interfaces import PatchResult, Task  # noqa: E402


def _task():
    return Task(instance_id="i1", repo="o/r", problem_statement="fix it")


def _patch(name, ok=True):
    return PatchResult(
        agent_name=name,
        instance_id="i1",
        patch="--- a\n+++ b\n" if ok else "",
        error=None if ok else "failed",
    )


async def test_no_usable_candidates_selects_none(monkeypatch):
    called = False

    async def _should_not_call(*a, **k):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(chairman_mod, "complete_json", _should_not_call)
    decision = await Chairman("claude-opus-4-8").judge(
        _task(), [_patch("a", ok=False), _patch("b", ok=False)]
    )
    assert decision.selected_agent is None
    assert decision.ranking == []
    assert not called  # no LLM call for the degenerate case


async def test_single_usable_candidate_short_circuits(monkeypatch):
    async def _should_not_call(*a, **k):
        raise AssertionError("judge should not call the LLM for one candidate")

    monkeypatch.setattr(chairman_mod, "complete_json", _should_not_call)
    decision = await Chairman("claude-opus-4-8").judge(
        _task(), [_patch("a"), _patch("b", ok=False)]
    )
    assert decision.selected_agent == "a"
    assert decision.ranking == ["a"]


async def test_judge_ranks_and_selects(monkeypatch):
    async def _fake_json(model, system, user, schema, **k):
        return {
            "ranking": ["b", "a"],
            "selected_agent": "b",
            "rationale": "b is more targeted.",
            "synthesized_patch": None,
        }

    monkeypatch.setattr(chairman_mod, "complete_json", _fake_json)
    decision = await Chairman("claude-opus-4-8").judge(
        _task(), [_patch("a"), _patch("b")]
    )
    assert decision.selected_agent == "b"
    assert decision.ranking == ["b", "a"]
    assert "targeted" in decision.rationale


async def test_judge_coerces_invalid_selection(monkeypatch):
    # Model returns a hallucinated agent name and a ranking with a bogus entry.
    async def _fake_json(model, system, user, schema, **k):
        return {
            "ranking": ["ghost", "a"],
            "selected_agent": "ghost",
            "rationale": "x",
            "synthesized_patch": "  ",  # whitespace -> treated as none
        }

    monkeypatch.setattr(chairman_mod, "complete_json", _fake_json)
    decision = await Chairman("claude-opus-4-8").judge(
        _task(), [_patch("a"), _patch("b")]
    )
    # "ghost" filtered out; selection coerced to the top valid ranked name.
    assert decision.selected_agent == "a"
    assert "ghost" not in decision.ranking
    assert decision.synthesized_patch is None
