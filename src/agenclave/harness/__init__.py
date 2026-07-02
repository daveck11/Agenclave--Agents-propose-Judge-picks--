# Stage 2: best-of-N Chairman code-fix harness.
#
# Public surface (all provider-agnostic, depend on these, not on a vendor SDK):
#
# - Task, PatchResult, ChairmanDecision, Agent, the contracts.
# - build_agents, construct the agent fleet for a provider.
# - dispatch, fan one task out to N agents concurrently.
# - Chairman, judge the candidates and select/synthesise the best.
# - route, pick the trusted subset of models to run (Thompson sampling over trust).

from __future__ import annotations

from .chairman import Chairman
from .dispatch import dispatch
from .interfaces import Agent, ChairmanDecision, PatchResult, Task
from .providers import build_agents
from .router import RouteDecision, route

__all__ = [
    "Agent",
    "Chairman",
    "ChairmanDecision",
    "PatchResult",
    "RouteDecision",
    "Task",
    "build_agents",
    "dispatch",
    "route",
]
