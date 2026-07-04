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


# XML-ish wrappers some models put around a diff (open or close forms).
_WRAP_TAG_RE = re.compile(
    r"</?(?:patch|diff|solution|code|answer|final)\s*>", re.IGNORECASE
)
# A line that is *only* a markdown code fence, e.g. ``` or ```diff. A real diff
# line touching a fence is prefixed with +/-/space, so a bare fence is junk.
_FENCE_LINE_RE = re.compile(r"^```[a-zA-Z]*[ \t]*$")
# A well-formed fenced block, optionally tagged as diff or patch.
_FENCE_BLOCK_RE = re.compile(
    r"```(?:diff|patch)?[ \t]*\r?\n(?P<body>.*?)```",
    re.DOTALL | re.IGNORECASE,
)
_DIFF_MARKERS = ("diff --git ", "--- a/", "--- /", "Index: ")


def extract_diff(text: str) -> str:
    """Pull a unified diff out of a model response.

    Robust to the wrappers models put around a diff, so a correct patch is not
    rejected by `git apply` over a leaked ``` fence or a </patch> tag:
      - strips XML-ish wrappers (<patch>...</patch>, <diff>..., <solution>...),
      - prefers the body of a well-formed ``` / ```diff block,
      - otherwise starts at the first real diff marker,
      - drops any stray fence lines and trims surrounding blank lines.
    Falls back to the raw response and lets the apply step reject it.
    """
    if not text:
        return ""

    # Wrapper tags are never valid diff content; remove them wherever they sit.
    text = _WRAP_TAG_RE.sub("", text)

    block = _FENCE_BLOCK_RE.search(text)
    if block:
        text = block.group("body")
    else:
        # No clean fence: start at the first plausible diff marker.
        for marker in _DIFF_MARKERS:
            idx = text.find(marker)
            if idx != -1:
                text = text[idx:]
                break

    # Drop leaked fence lines, then trim blank lines around the diff.
    lines = [ln for ln in text.splitlines() if not _FENCE_LINE_RE.match(ln)]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    body = "\n".join(lines)
    return body + "\n" if body.strip() else ""
