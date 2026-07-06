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


CHAIRMAN_EXPLAIN_SYSTEM = (
    "You are the Chairman: a senior engineer explaining a code-fix decision to a "
    "developer, plainly and honestly. You are given several candidate patches for "
    "an issue, each labelled with its VERIFIED test result (did it apply? did the "
    "tests pass?), and told which candidate is the verified winner. Verification "
    "decided the winner - do not override it. Explain in a way the developer can "
    "trust: say whether the candidates took SIMILAR or DIFFERENT approaches (call "
    "out anything one did notably differently), note which passed or failed the "
    "tests, and explain why the winner is the one to trust. Also state which "
    "candidate you would have preferred by reading the diffs alone."
)

EXPLAIN_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "read_preferred": {
            "type": "string",
            "description": "The agent whose patch you'd pick by reading alone.",
        },
        "rationale": {
            "type": "string",
            "description": "3-6 sentences: approaches taken, test results, and why the winner is trustworthy.",
        },
    },
    "required": ["read_preferred", "rationale"],
    "additionalProperties": False,
}


def _verify_status(vr) -> str:
    if vr is None:
        return "no test result"
    if not vr.applies:
        return "PATCH DID NOT APPLY"
    if vr.tests_passed:
        return f"PASSED all tests ({vr.passed}/{vr.total})"
    return f"applied but FAILED tests ({vr.passed}/{vr.total})"


def _build_explain_prompt(
    task: Task, candidates: list[PatchResult], verifications: dict, winner: str
) -> str:
    parts = [
        "Issue / problem statement:",
        task.problem_statement.strip(),
        "",
        f"The verified winner (decided by running the tests) is: {winner}",
        "",
        f"The {len(candidates)} candidate patches and their test results:",
        "",
    ]
    for c in candidates:
        status = _verify_status(verifications.get(c.agent_name))
        parts.append(f"=== agent: {c.agent_name}  [{status}] ===")
        parts.append(c.patch.strip() or "(empty patch)")
        parts.append("")
    parts.append(
        "Write 3 to 6 sentences for the developer: did the candidates take similar "
        "or different approaches (name anything notably different)? which passed or "
        f"failed? and why is the verified winner ({winner}) the one to trust? Also "
        "give read_preferred: the agent you would pick by reading the diffs alone."
    )
    return "\n".join(parts)


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
        """Rank the candidates and pick the best one.

        The model's answer gets coerced to valid agent names, so a
        hallucinated name falls back to the top of the ranking.
        """
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

    async def explain(
        self,
        task: Task,
        candidates: list[PatchResult],
        verifications: dict,
        winner: str,
    ) -> ChairmanDecision:
        """Explain a verified fixture decision in the Chairman's own words: compare
        the candidates' approaches and say why the already-decided winner is the one
        to trust. Never raises; an empty rationale falls back to a templated one in
        the UI. selected_agent is the reading preference (for the read contrast);
        the ranking leads with the verified winner.
        """
        usable = [c for c in candidates if c.ok]
        valid = {c.agent_name for c in usable}
        if not usable or winner not in valid:
            return ChairmanDecision(
                instance_id=task.instance_id,
                selected_agent=winner if winner in valid else None,
                ranking=[winner] if winner in valid else [],
                rationale="",
            )
        prompt = _build_explain_prompt(task, usable, verifications, winner)
        try:
            result = await complete_json(
                self.model,
                CHAIRMAN_EXPLAIN_SYSTEM,
                prompt,
                EXPLAIN_SCHEMA,
                tool_name="explain",
                max_tokens=self._max_tokens,
                provider=settings.provider,
            )
        except Exception:  # noqa: BLE001 - the explanation is best-effort
            result = {}
        read_pref = result.get("read_preferred")
        if read_pref not in valid:
            read_pref = winner
        return ChairmanDecision(
            instance_id=task.instance_id,
            selected_agent=read_pref,
            ranking=[winner],
            rationale=str(result.get("rationale", "")).strip(),
            raw_response=str(result),
        )
