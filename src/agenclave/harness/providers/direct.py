# Direct provider adapter: Claude (Anthropic) and OpenAI behind one Agent.
#
# Model routing is by name: `claude*` -> Anthropic, `gpt*`/`o1*`/`o3*` ->
# OpenAI. The vendor SDKs are imported lazily and the async clients are cached, so
# importing this module (e.g. in tests) costs nothing and needs no API key.
#
# Two low-level helpers are exposed and reused by the Chairman judge:
# - `complete_text`  -> a plain text completion.
# - `complete_json`  -> a completion constrained to a JSON object matching a
#   schema (Claude: forced tool use; OpenAI: JSON response format).
#
# These deliberately use only the stable `messages.create` /
# `chat.completions.create` surface so they work with the pinned SDKs
# (anthropic 0.40.0, openai 1.57.4). Adaptive thinking is intentionally NOT sent:
# it post-dates the pinned anthropic SDK. If the SDK is upgraded, pass
# `thinking={"type": "adaptive"}` to the judge call for better reasoning.

from __future__ import annotations

import functools
import json
from typing import Any

from ..interfaces import Agent, PatchResult, Task
from .base import AGENT_SYSTEM_PROMPT, build_task_prompt, extract_diff


def is_anthropic_model(model: str) -> bool:
    return model.lower().startswith("claude")


def is_openai_model(model: str) -> bool:
    m = model.lower()
    return m.startswith(("gpt", "o1", "o3", "o4", "chatgpt"))


# --- Cached async clients (created on first use; need keys only then) ----------
@functools.lru_cache(maxsize=1)
def _anthropic_client():
    import anthropic  # lazy: avoid import cost / key lookup at module load

    from ...config import settings

    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None)


@functools.lru_cache(maxsize=1)
def _openai_client():
    import openai  # lazy

    from ...config import settings

    return openai.AsyncOpenAI(api_key=settings.openai_api_key or None)


# ------------------------------------------------------------------------------
# Low-level completions (provider-routed by model name)
# ------------------------------------------------------------------------------
async def complete_text(
    model: str,
    system: str,
    user: str,
    *,
    max_tokens: int = 4096,
) -> str:
    # Single text completion. Routes to Anthropic or OpenAI by model name.
    if is_anthropic_model(model):
        client = _anthropic_client()
        resp = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")
    if is_openai_model(model):
        client = _openai_client()
        resp = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""
    raise ValueError(
        f"unknown model {model!r}: not a recognised Anthropic or OpenAI model"
    )


async def complete_json(
    model: str,
    system: str,
    user: str,
    schema: dict[str, Any],
    *,
    tool_name: str = "submit",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    # Completion constrained to a JSON object matching `schema`.
    #
    #     Anthropic: a single forced tool whose `input_schema` is `schema`, the
    #     model must call it, and we return the validated tool input. OpenAI: JSON
    #     response format, with the schema embedded in the prompt, then `json.loads`.
    if is_anthropic_model(model):
        client = _anthropic_client()
        resp = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=[
                {
                    "name": tool_name,
                    "description": "Submit the structured result.",
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": user}],
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == tool_name:
                return dict(block.input)
        raise ValueError("Anthropic response contained no tool_use block")

    if is_openai_model(model):
        client = _openai_client()
        user_with_schema = (
            f"{user}\n\nRespond with a JSON object matching this schema:\n"
            f"{json.dumps(schema)}"
        )
        resp = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_with_schema},
            ],
        )
        return json.loads(resp.choices[0].message.content or "{}")

    raise ValueError(
        f"unknown model {model!r}: not a recognised Anthropic or OpenAI model"
    )


# ------------------------------------------------------------------------------
# Agent
# ------------------------------------------------------------------------------
class DirectAgent(Agent):
    # A coding agent backed directly by a Claude or OpenAI model.
    #
    #     `propose_patch` never raises for normal failures (network/API errors,
    #     empty output): it captures them in `PatchResult.error` so dispatch can
    #     keep the other candidates. `ValueError` for an unknown model is a config
    #     error and surfaces at construction, not here.

    def __init__(self, model: str, *, max_tokens: int = 4096) -> None:
        if not (is_anthropic_model(model) or is_openai_model(model)):
            raise ValueError(
                f"unknown model {model!r}: not a recognised Anthropic/OpenAI model"
            )
        self.model = model
        self.name = model  # agent name == model id (unique within a dispatch)
        self._max_tokens = max_tokens

    async def propose_patch(self, task: Task) -> PatchResult:
        prompt = build_task_prompt(task)
        try:
            text = await complete_text(
                self.model,
                AGENT_SYSTEM_PROMPT,
                prompt,
                max_tokens=self._max_tokens,
            )
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
