# Provider-agnostic contracts for the Chairman harness.
#
# The whole point of Stage 2 is that *any* coding agent, Claude, OpenAI, or the
# BlackBox Agents API, is interchangeable behind `Agent`. Dispatch, the Chairman
# judge, and evaluation all depend only on these types, never on a vendor SDK.

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Task:
    # A coding task handed to the agents.
    #
    #     `triage_label`/`triage_severity` are populated by the Stage 1 classifier
    #     (the "front door") so agents get the issue annotated, not raw.

    instance_id: str
    repo: str
    problem_statement: str
    base_commit: str | None = None
    hints: str | None = None
    triage_label: str | None = None
    triage_severity: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class PatchResult:
    # A single candidate patch produced by one agent.

    agent_name: str
    instance_id: str
    patch: str  # unified diff
    raw_response: str = ""
    usage: dict = field(default_factory=dict)  # tokens / cost, if available
    error: str | None = None  # set if the agent failed to produce a patch

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.patch.strip())


@dataclass
class ChairmanDecision:
    # The judge's verdict over all candidate patches.

    instance_id: str
    selected_agent: str | None
    ranking: list[str]  # agent names, best-first
    rationale: str
    synthesized_patch: str | None = None  # set when the judge merges candidates
    raw_response: str = ""


class Agent(ABC):
    # A coding agent that proposes a patch for a task.

    name: str

    @abstractmethod
    async def propose_patch(self, task: Task) -> PatchResult:
        # Produce a candidate patch. Must not raise for normal failures  - 
        #         capture them in `PatchResult.error` so dispatch can keep the others.
        raise NotImplementedError
