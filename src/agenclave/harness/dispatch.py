# Parallel dispatch: one coding task -> N agents concurrently.
#
# This is the fan-out half of the Chairman best-of-N pattern. Every agent gets the
# same `Task` at the same time (`asyncio.gather`); each returns a
# `PatchResult`. Agents are contracted not to raise for normal failures, but we
# still defensively convert any escaped exception into an error `PatchResult` so
# one bad agent can never sink the others.

from __future__ import annotations

import asyncio

from .interfaces import Agent, PatchResult, Task


async def dispatch(task: Task, agents: list[Agent]) -> list[PatchResult]:
    # Send `task` to every agent concurrently and collect their patches.
    #
    #     The returned list is in the same order as `agents`. Failures are captured
    #     as `PatchResult` objects with `.error` set (and `.ok` False), never
    #     raised, so the Chairman always sees one result per agent.
    if not agents:
        raise ValueError("dispatch requires at least one agent")

    async def _run(agent: Agent) -> PatchResult:
        try:
            return await agent.propose_patch(task)
        except Exception as exc:  # noqa: BLE001 - belt-and-suspenders
            return PatchResult(
                agent_name=getattr(agent, "name", "unknown"),
                instance_id=task.instance_id,
                patch="",
                error=f"{type(exc).__name__}: {exc}",
            )

    return await asyncio.gather(*(_run(a) for a in agents))
