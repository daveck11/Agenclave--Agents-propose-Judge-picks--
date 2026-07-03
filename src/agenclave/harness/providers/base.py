# Shared helpers for provider adapters.
#
# Provider adapters differ only in how they call a model. The prompt they send and
# the way a unified diff is pulled back out of the response are identical, so those
# two concerns live here and the Claude/OpenAI/BlackBox adapters stay thin.

from __future__ import annotations

import re

from ..interfaces import Task

# System prompt for the coding agents. Kept provider-neutral and deterministic:
# we want a single unified diff back, nothing else, so the Chairman can compare
# candidates on equal footing.
AGENT_SYSTEM_PROMPT = (
    "You are an expert software engineer fixing a bug in an open-source "
    "repository. You are given an issue and must produce a patch that resolves "
    "it.\n\n"
    "Respond with ONE unified diff (git-style, `diff --git` / `---` / `+++` / "
    "`@@` hunks) and NOTHING else: no prose, no explanation, no markdown around "
    "it. If you wrap it in a fence, use ```diff. The diff must apply cleanly "
    "from the repository root with `git apply`."
)


def build_task_prompt(task: Task) -> str:
    # Builds the user prompt for a coding agent. The triage label and
    # severity are included as context when the classifier has run.
    parts: list[str] = []
    parts.append(f"Repository: {task.repo}")
    if task.base_commit:
        parts.append(f"Base commit: {task.base_commit}")
    triage_bits = []
    if task.triage_label:
        triage_bits.append(f"type={task.triage_label}")
    if task.triage_severity:
        triage_bits.append(f"severity={task.triage_severity}")
    if triage_bits:
        parts.append(f"Triage (from Stage 1 classifier): {', '.join(triage_bits)}")
    parts.append("")
    parts.append("Issue / problem statement:")
    parts.append(task.problem_statement.strip())
    if task.hints:
        parts.append("")
        parts.append("Hints:")
        parts.append(task.hints.strip())
    parts.append("")
    parts.append(
        "Produce the unified diff that fixes this issue. Output only the diff."
    )
    return "\n".join(parts)


# Matches a fenced code block, optionally tagged as diff or patch.
_FENCE_RE = re.compile(
    r"```(?:diff|patch)?\s*\n(?P<body>.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def extract_diff(text: str) -> str:
    """Pull a unified diff out of a model response.

    Tries a fenced code block first, then the first diff marker, then just
    returns the stripped response and lets the apply step reject it.
    """
    if not text:
        return ""

    fenced = _FENCE_RE.search(text)
    if fenced:
        return fenced.group("body").strip() + "\n"

    # No fence: find the first plausible diff marker and take everything after.
    for marker in ("diff --git ", "--- a/", "--- /", "Index: "):
        idx = text.find(marker)
        if idx != -1:
            return text[idx:].strip() + "\n"

    return text.strip()
