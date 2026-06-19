# Provider adapters implementing the Agent interface.
#
# build_agents is the single switch point between the two backends:
#
# - provider="direct"   -> one DirectAgent per model in agent_models
#   (Claude via Anthropic, GPT via OpenAI).
# - provider="blackbox" -> one BlackBoxAgent per model, all routed through
#   the BlackBox Agents API.
#
# Everything downstream (dispatch, Chairman, eval) depends only on the Agent
# interface, never on which branch ran here.

from __future__ import annotations

from ..interfaces import Agent
from .base import build_task_prompt, extract_diff
from .blackbox import BlackBoxAgent
from .direct import DirectAgent

__all__ = [
    "Agent",
    "BlackBoxAgent",
    "DirectAgent",
    "build_agents",
    "build_task_prompt",
    "extract_diff",
]


def build_agents(provider: str, models: list[str]) -> list[Agent]:
    # Construct the agent fleet for provider over models.
    #
    # Raises ValueError for an unknown provider or an empty model list so
    # misconfiguration fails loudly at startup, not mid-run.
    if not models:
        raise ValueError("no agent models configured (AGENCLAVE_AGENT_MODELS)")
    provider = provider.lower().strip()
    if provider == "direct":
        return [DirectAgent(m) for m in models]
    if provider == "blackbox":
        return [BlackBoxAgent(m) for m in models]
    raise ValueError(
        f"unknown provider {provider!r}; expected 'direct' or 'blackbox'"
    )
