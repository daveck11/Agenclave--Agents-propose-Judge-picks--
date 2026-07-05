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
# Only the stable `messages.create` / `chat.completions.create` surface is
# used, so this works with the pinned SDKs (anthropic 0.40.0, openai
# 1.57.4). Adaptive thinking isn't sent because it post-dates the pinned
# anthropic SDK.

from __future__ import annotations

import functools
import json
import re
from typing import Any

from ..interfaces import Agent, PatchResult, Task
from .base import AGENT_SYSTEM_PROMPT, build_task_prompt, extract_diff


def is_anthropic_model(model: str) -> bool:
    return model.lower().startswith("claude")


def is_openai_model(model: str) -> bool:
    m = model.lower()
    return m.startswith(("gpt", "o1", "o3", "o4", "chatgpt"))


# clients are created on first use so importing this module needs no keys
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


@functools.lru_cache(maxsize=1)
def _blackbox_client():
    # BlackBox is OpenAI-compatible: same SDK, different base_url + key. Used when
    # provider="blackbox" so the Chairman judge can also route through BlackBox.
    import openai  # lazy

    from ...config import settings

    return openai.AsyncOpenAI(
        api_key=settings.blackbox_api_key or "",
        base_url=settings.blackbox_api_base,
    )


async def complete_text(
    model: str,
    system: str,
    user: str,
    *,
    max_tokens: int = 4096,
    provider: str = "direct",
) -> str:
    # Single text completion. provider="blackbox" routes through BlackBox's
    # OpenAI-compatible endpoint; otherwise routes to Anthropic/OpenAI by name.
    if provider == "blackbox":
        client = _blackbox_client()
        resp = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""
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


def _parse_json_object(text: str) -> dict[str, Any]:
    # Best-effort JSON extraction for endpoints without a JSON mode: the model is
    # asked for JSON in the prompt but may still wrap it in prose or a ```json
    # fence. Strip a fence, then fall back to the outermost {...} block. Returns
    # {} if nothing parses (the Chairman handles an empty decision gracefully).
    text = (text or "").strip()
    if not text:
        return {}
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


async def complete_json(
    model: str,
    system: str,
    user: str,
    schema: dict[str, Any],
    *,
    tool_name: str = "submit",
    max_tokens: int = 4096,
    provider: str = "direct",
) -> dict[str, Any]:
    """Completion constrained to a JSON object matching `schema`.

    For Anthropic this is a single forced tool call whose input_schema is
    the schema. For OpenAI (and BlackBox, which speaks the same protocol)
    it's JSON response format with the schema pasted into the prompt.
    """
    if provider == "blackbox":
        client = _blackbox_client()
        user_with_schema = (
            f"{user}\n\nRespond with ONLY a JSON object matching this schema - no "
            f"prose, no markdown fences:\n{json.dumps(schema)}"
        )
        # BlackBox's open-source endpoint rejects response_format=json_object, so
        # ask for JSON in the prompt and parse it tolerantly from the text.
        resp = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_with_schema},
            ],
        )
        return _parse_json_object(resp.choices[0].message.content or "")

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


class DirectAgent(Agent):
    # An agent backed directly by a Claude or OpenAI model. propose_patch
    # catches normal failures into PatchResult.error; an unknown model name
    # is a config mistake and fails at construction instead.

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
