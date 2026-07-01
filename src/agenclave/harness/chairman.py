# The Chairman judge: scores candidate patches and selects/synthesises the best.
#
# Given a `Task` and the candidate `PatchResult` list from dispatch, the judge
# LLM returns a strict-JSON verdict: a best-first ranking of agent names, the
# selected agent, a written rationale, and (optionally) a synthesised patch that
# merges the strongest ideas. Output is constrained to a JSON schema via
# `complete_json` (forced tool use on Claude), so parsing never guesses.
#
# The judge model is configurable (`AGENCLAVE_CHAIRMAN_MODEL`, default
# `claude-opus-4-8`). It runs through the configured provider, exactly like the
# agents: provider="blackbox" sends the judge call through BlackBox's API too.

from __future__ import annotations

from ..config import settings
from .interfaces import ChairmanDecision, PatchResult, Task
from .providers.direct import complete_json

CHAIRMAN_SYSTEM_PROMPT = (
    "You are the Chairman: a senior engineer judging candidate patches for a "
    "software issue. You are given the issue and several candidate unified "
    "diffs, each labelled with the agent that produced it. Evaluate them on "
    "correctness (does it actually fix the issue?), scope (minimal, no "
    "collateral damage), and quality. Rank them best-first, select the single "
    "best, and explain why concisely. If combining ideas from multiple "
    "candidates yields a clearly better patch, provide it as a synthesised "
    "unified diff; otherwise leave it null and the selected candidate stands."
)

# JSON schema the judge must satisfy (kept simple: no constraints unsupported by
# strict tool-use / JSON mode).
DECISION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "ranking": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Agent names, best first.",
        },
        "selected_agent": {
            "type": "string",
            "description": "The agent whose patch is chosen.",
        },
        "rationale": {
            "type": "string",
            "description": "Concise justification for the ranking and choice.",
        },
        "synthesized_patch": {
            "type": ["string", "null"],
            "description": "Optional merged unified diff, or null.",
        },
    },
    "required": ["ranking", "selected_agent", "rationale"],
    "additionalProperties": False,
}


def _build_judge_prompt(task: Task, candidates: list[PatchResult]) -> str:
    parts = [
        "Issue / problem statement:",
        task.problem_statement.strip(),
        "",
        f"Repository: {task.repo}",
        "",
        f"There are {len(candidates)} candidate patches. Judge them:",
        "",
    ]
    for c in candidates:
        parts.append(f"=== Candidate from agent: {c.agent_name} ===")
        parts.append(c.patch.strip() or "(empty patch)")
        parts.append("")
    parts.append(
        "Return your ranking (best first, using the exact agent names above), "
        "the selected agent, a rationale, and an optional synthesised patch."
    )
    return "\n".join(parts)


class Chairman:
    # Best-patch judge over candidate diffs.

    def __init__(self, model: str, *, max_tokens: int = 4096) -> None:
        self.model = model
        self._max_tokens = max_tokens

    async def judge(
        self, task: Task, candidates: list[PatchResult]
    ) -> ChairmanDecision:
        # Rank candidates and select the best. Strict-JSON, never raises for
        #         an empty field; coerces the model's answer to valid agent names.
        usable = [c for c in candidates if c.ok]

        # Degenerate cases: 0 or 1 usable candidate need no LLM call.
        if not usable:
            return ChairmanDecision(
                instance_id=task.instance_id,
                selected_agent=None,
                ranking=[],
                rationale="No candidate produced a usable patch.",
            )
        if len(usable) == 1:
            only = usable[0]
            return ChairmanDecision(
                instance_id=task.instance_id,
                selected_agent=only.agent_name,
                ranking=[only.agent_name],
                rationale="Only one candidate produced a usable patch; selected by default.",
            )

        prompt = _build_judge_prompt(task, usable)
        result = await complete_json(
            self.model,
            CHAIRMAN_SYSTEM_PROMPT,
            prompt,
            DECISION_SCHEMA,
            tool_name="submit_decision",
            max_tokens=self._max_tokens,
            provider=settings.provider,
        )

        valid_names = {c.agent_name for c in usable}
        ranking = [r for r in result.get("ranking", []) if r in valid_names]
        selected = result.get("selected_agent")
        if selected not in valid_names:
            # Fall back to the top of the (validated) ranking, else first usable.
            selected = ranking[0] if ranking else usable[0].agent_name
        if not ranking:
            ranking = [selected]

        synth = result.get("synthesized_patch")
        synth = synth.strip() if isinstance(synth, str) and synth.strip() else None

        return ChairmanDecision(
            instance_id=task.instance_id,
            selected_agent=selected,
            ranking=ranking,
            rationale=str(result.get("rationale", "")).strip(),
            synthesized_patch=synth,
            raw_response=str(result),
        )
