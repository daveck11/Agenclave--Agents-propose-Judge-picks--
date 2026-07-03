# Fan-out: send one task to every agent at once with asyncio.gather.
# Agents shouldn't raise, but any exception that escapes still gets turned
# into an error PatchResult so one bad agent can't sink the others.

from __future__ import annotations

import asyncio

from .interfaces import Agent, PatchResult, Task


async def dispatch(task: Task, agents: list[Agent]) -> list[PatchResult]:
    # Results come back in the same order as `agents`, one per agent,
    # failures included (error set, ok False).
    if not agents:
        raise ValueError("dispatch requires at least one agent")

    async def _run(agent: Agent) -> PatchResult:
        try:
            return await agent.propose_patch(task)
        except Exception as exc:  # noqa: BLE001
            return PatchResult(
                agent_name=getattr(agent, "name", "unknown"),
                instance_id=task.instance_id,
                patch="",
                error=f"{type(exc).__name__}: {exc}",
            )

    return await asyncio.gather(*(_run(a) for a in agents))
