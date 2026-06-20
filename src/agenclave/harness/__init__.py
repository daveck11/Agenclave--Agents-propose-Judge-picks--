# Stage 2: best-of-N Chairman code-fix harness.
#
# Public surface (all provider-agnostic, depend on these, not on a vendor SDK):
#
# - Task, PatchResult, ChairmanDecision, Agent, the contracts.
# - build_agents, construct the agent fleet for a provider.
# - dispatch, fan one task out to N agents concurrently.
# - Chairman, judge the candidates and select/synthesise the best.

from __future__ import annotations

from .chairman import Chairman
from .dispatch import dispatch
from .interfaces import Agent, ChairmanDecision, PatchResult, Task
from .providers import build_agents

__all__ = [
    "Agent",
    "Chairman",
    "ChairmanDecision",
    "PatchResult",
    "Task",
    "build_agents",
    "dispatch",
]
