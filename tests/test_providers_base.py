# Tests for provider-agnostic helpers: diff extraction + the agent factory.
#
# Fast and offline, no SDKs imported, no network, no keys.

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.harness.providers import build_agents  # noqa: E402
from agenclave.harness.providers.base import extract_diff  # noqa: E402
from agenclave.harness.providers.blackbox import BlackBoxAgent  # noqa: E402
from agenclave.harness.providers.direct import DirectAgent  # noqa: E402


# --- extract_diff -------------------------------------------------------------
def test_extract_diff_from_fence():
    text = "Here is the fix:\n```diff\n--- a/f.py\n+++ b/f.py\n@@\n-x\n+y\n```\nDone."
    out = extract_diff(text)
    assert out.startswith("--- a/f.py")
    assert "+y" in out
    assert "Here is the fix" not in out
    assert "Done." not in out


def test_extract_diff_from_marker_without_fence():
    text = "Sure!\ndiff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@\n-x\n+y\n"
    out = extract_diff(text)
    assert out.startswith("diff --git a/f.py")
    assert "Sure!" not in out


def test_extract_diff_empty():
    assert extract_diff("") == ""


# --- build_agents factory -----------------------------------------------------
def test_build_agents_direct():
    agents = build_agents("direct", ["claude-sonnet-4-6", "gpt-4o-mini"])
    assert [a.name for a in agents] == ["claude-sonnet-4-6", "gpt-4o-mini"]
    assert all(isinstance(a, DirectAgent) for a in agents)


def test_build_agents_blackbox():
    agents = build_agents("blackbox", ["blackbox-coder"])
    assert isinstance(agents[0], BlackBoxAgent)
    assert agents[0].name == "blackbox:blackbox-coder"


def test_build_agents_unknown_provider_raises():
    with pytest.raises(ValueError):
        build_agents("nope", ["claude-sonnet-4-6"])


def test_build_agents_empty_models_raises():
    with pytest.raises(ValueError):
        build_agents("direct", [])


def test_direct_agent_unknown_model_raises():
    with pytest.raises(ValueError):
        DirectAgent("not-a-real-model")
