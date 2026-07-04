# Shared types for the harness. Dispatch, the judge and evaluation only
# depend on these, so any agent (Claude, OpenAI, BlackBox) can sit behind
# the Agent interface without the rest of the code caring.

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Task:
    # One coding task handed to the agents. triage_label/triage_severity come
    # from the stage 1 classifier when it has run.

    instance_id: str
    repo: str
    problem_statement: str
    base_commit: str | None = None
    hints: str | None = None
    triage_label: str | None = None
    triage_severity: str | None = None
    # Current contents of the file(s) the agent should edit, {path: source}. When
    # present, the agent is shown the exact code (so it diffs against real content
    # instead of guessing the file). Empty for the issue-text-only web path.
    files: dict = field(default_factory=dict)
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
        # shouldn't raise for normal failures; put them in PatchResult.error
        # so dispatch can keep the other candidates
        raise NotImplementedError
