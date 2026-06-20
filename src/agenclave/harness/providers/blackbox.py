# BlackBox Agents API adapter.
#
# Targets the BlackBox Agents API (`cloud.blackbox.ai/api`) using the documented
# async task pattern: `POST /tasks` to submit a coding task, then poll
# `GET /tasks/{id}` until the task reaches a terminal state, and read the patch
# out of the result.
#
# This is **real, config-selectable** code (select via `AGENCLAVE_PROVIDER=blackbox`)
# but it ships with mocked unit tests rather than live ones: a real `bb_` key is
# only needed to exercise it against the live service. All network I/O goes through
# `httpx` and is isolated in small methods so `respx` can mock the two
# endpoints in tests.
#
# Note on the wire contract: response field names vary, so result parsing is
# defensive (it accepts `result` / `output` / `response` / `patch` and a
# few status spellings). If the live API differs, adjust `_SUBMIT_PATH` /
# `_extract_*` here, the rest of the harness is unaffected.

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from ...config import settings
from ..interfaces import Agent, PatchResult, Task
from .base import AGENT_SYSTEM_PROMPT, build_task_prompt, extract_diff

# Terminal status spellings we treat as success / failure.
_DONE_STATUSES = {"completed", "complete", "done", "succeeded", "success", "finished"}
_FAILED_STATUSES = {"failed", "error", "errored", "cancelled", "canceled"}


class BlackBoxAgent(Agent):
    # A coding agent backed by the BlackBox Agents API.
    #
    #     Like `DirectAgent`, `propose_patch` never raises for normal failures
    #     (HTTP errors, timeouts, a failed/blank task), they are captured in
    #     `PatchResult.error`.

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        poll_interval: float = 2.0,
        max_polls: int = 60,
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self.name = f"blackbox:{model}"
        self._api_key = api_key if api_key is not None else settings.blackbox_api_key
        self._api_base = (api_base or settings.blackbox_api_base).rstrip("/")
        self._poll_interval = poll_interval
        self._max_polls = max_polls
        self._timeout = timeout

    # --- HTTP boundary (mock these two in tests) -----------------------------
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key or ''}",
            "Content-Type": "application/json",
        }

    async def _submit_task(self, client: httpx.AsyncClient, task: Task) -> str:
        # POST the coding task; return the BlackBox task id.
        payload = {
            "model": self.model,
            "system": AGENT_SYSTEM_PROMPT,
            "prompt": build_task_prompt(task),
            "metadata": {
                "instance_id": task.instance_id,
                "repo": task.repo,
                "triage_label": task.triage_label,
            },
        }
        resp = await client.post(
            f"{self._api_base}/tasks", json=payload, headers=self._headers()
        )
        resp.raise_for_status()
        data = resp.json()
        task_id = data.get("id") or data.get("task_id") or data.get("taskId")
        if not task_id:
            raise ValueError(f"submit response had no task id: {data!r}")
        return str(task_id)

    async def _poll_task(self, client: httpx.AsyncClient, task_id: str) -> dict[str, Any]:
        # Poll until the task reaches a terminal state; return the final body.
        for _ in range(self._max_polls):
            resp = await client.get(
                f"{self._api_base}/tasks/{task_id}", headers=self._headers()
            )
            resp.raise_for_status()
            body = resp.json()
            status = str(body.get("status", "")).lower()
            if status in _DONE_STATUSES:
                return body
            if status in _FAILED_STATUSES:
                raise RuntimeError(
                    f"BlackBox task {task_id} failed: "
                    f"{body.get('error') or status}"
                )
            await asyncio.sleep(self._poll_interval)
        raise TimeoutError(
            f"BlackBox task {task_id} did not finish within "
            f"{self._max_polls} polls"
        )

    @staticmethod
    def _extract_text(body: dict[str, Any]) -> str:
        # Pull the model's text output from a terminal task body (defensive).
        for key in ("result", "output", "response", "patch", "content", "text"):
            val = body.get(key)
            if isinstance(val, str) and val.strip():
                return val
            # Some APIs nest under result: {output: "..."} etc.
            if isinstance(val, dict):
                for k2 in ("output", "text", "content", "patch"):
                    inner = val.get(k2)
                    if isinstance(inner, str) and inner.strip():
                        return inner
        return ""

    # --- Agent interface ------------------------------------------------------
    async def propose_patch(self, task: Task) -> PatchResult:
        if not self._api_key:
            return PatchResult(
                agent_name=self.name,
                instance_id=task.instance_id,
                patch="",
                error="BLACKBOX_API_KEY not set; cannot call the BlackBox API",
            )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                task_id = await self._submit_task(client, task)
                body = await self._poll_task(client, task_id)
            text = self._extract_text(body)
        except Exception as exc:  # noqa: BLE001 - capture, never crash dispatch
            return PatchResult(
                agent_name=self.name,
                instance_id=task.instance_id,
                patch="",
                error=f"{type(exc).__name__}: {exc}",
            )
        return PatchResult(
            agent_name=self.name,
            instance_id=task.instance_id,
            patch=extract_diff(text),
            raw_response=text,
        )
