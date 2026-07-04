# BlackBox AI provider adapter (OpenAI-compatible).
#
# BlackBox exposes an OpenAI-compatible inference API - "all models, one endpoint"
# (Claude, GPT, Gemini, Grok, DeepSeek, ...). So this adapter reuses the OpenAI
# Async SDK pointed at BlackBox's base URL with a `bb_` key, exactly mirroring the
# OpenAI branch of DirectAgent. Every agent in the best-of-N panel is then
# dispatched THROUGH BlackBox, and the Chairman judges between them.
#
# Activate it with env (no code change needed):
#     AGENCLAVE_PROVIDER=blackbox
#     AGENCLAVE_BLACKBOX_API_KEY=bb_...
#     AGENCLAVE_BLACKBOX_API_BASE=<from BlackBox API docs; OpenAI-compatible root>
#     AGENCLAVE_AGENT_MODELS=<comma-separated BlackBox model ids>
#
# `propose_patch` never raises for normal failures (network/API errors, empty
# output): they are captured in `PatchResult.error` so dispatch keeps the other
# candidates - same contract as DirectAgent.
#
# NOTE: confirm the exact base URL + model ids against BlackBox's current API docs.
# They are config values precisely so wiring a real key needs no code change.

from __future__ import annotations

from ...config import settings
from ..interfaces import Agent, PatchResult, Task
from .base import AGENT_SYSTEM_PROMPT, build_task_prompt, extract_diff


class BlackBoxAgent(Agent):
    # A coding agent backed by BlackBox's OpenAI-compatible API.
    #
    #     api_key / api_base default to settings (the env-configured values); they
    #     are constructor args mainly so tests can inject a mock endpoint. The
    #     async client is built lazily on first use and cached on the instance, so
    #     constructing an agent costs nothing and needs no key.

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.name = f"blackbox:{model}"  # unique within a dispatch; flags the source
        self._api_key = api_key if api_key is not None else settings.blackbox_api_key
        self._api_base = (api_base or settings.blackbox_api_base).rstrip("/")
        self._max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        # Build (once) an OpenAI Async client pointed at BlackBox. Only reached
        # when a key is present (propose_patch guards first), so api_key is set.
        if self._client is None:
            import openai  # lazy: avoid import cost / key lookup at module load

            self._client = openai.AsyncOpenAI(
                api_key=self._api_key or "",
                base_url=self._api_base,
            )
        return self._client

    async def propose_patch(self, task: Task) -> PatchResult:
        if not self._api_key:
            return PatchResult(
                agent_name=self.name,
                instance_id=task.instance_id,
                patch="",
                error="BLACKBOX_API_KEY not set; cannot call the BlackBox API",
            )
        try:
            client = self._get_client()
            resp = await client.chat.completions.create(
                model=self.model,
                max_tokens=self._max_tokens,
                messages=[
                    {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": build_task_prompt(task)},
                ],
            )
            text = resp.choices[0].message.content or ""
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
