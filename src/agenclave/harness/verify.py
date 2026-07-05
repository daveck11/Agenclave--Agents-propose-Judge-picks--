# Applies a candidate patch to a throwaway copy of a working tree and runs
# the tests there. The result of that run is what trust_rank sorts on.
#
# Normal failures (patch doesn't apply, tests fail, timeout) don't raise;
# they come back in the VerifyResult, same convention as PatchResult.

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_SUMMARY_RE = re.compile(r"(\d+) (passed|failed|errors?)")

# git-apply attempts, strict first then more lenient: wrong hunk line numbers
# (--recount), whitespace (--ignore-whitespace), thinner context (-C1), missing
# a/ b/ prefix (-p0). Models often produce diffs with slightly-off metadata;
# these passes recover those without misapplying, since the actual context
# lines still have to match.
_APPLY_PASSES = [
    [],
    ["--recount"],
    ["--recount", "--ignore-whitespace"],
    ["--recount", "--ignore-whitespace", "-C1"],
    ["-p0", "--recount", "--ignore-whitespace"],
]


@dataclass
class VerifyResult:
    applies: bool
    tests_passed: bool
    passed: int
    total: int
    evidence: str
    error: str | None = None


def _parse_pytest(output: str) -> tuple[int, int]:
    # Best-effort passed/total from pytest's summary line ("1 passed, 1 failed").
    passed = failed = 0
    for n, kind in _SUMMARY_RE.findall(output):
        if kind == "passed":
            passed = int(n)
        else:  # failed / error / errors
            failed += int(n)
    return passed, passed + failed


def _norm_lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _targets(patch: str) -> list[str]:
    # Files the patch modifies (from `+++ b/path` lines), prefix stripped.
    paths = []
    for line in patch.splitlines():
        if line.startswith("+++ "):
            p = line[4:].strip().split("\t")[0]
            if p.startswith(("a/", "b/")):
                p = p[2:]
            if p and p != "/dev/null":
                paths.append(p)
    return paths


def _apply(patch: str, sandbox: Path) -> tuple[bool, str]:
    # git apply is atomic (a failed apply leaves the tree untouched), which is
    # what makes retrying with looser flags safe. Line endings on the patch and
    # the target files both get normalised to LF, and the patch goes in as raw
    # bytes; on Windows, text-mode stdin turns \n into \r\n and context
    # matching breaks against LF files. That one cost me an afternoon.
    patch = _norm_lf(patch)
    for rel in _targets(patch):
        f = sandbox / rel
        if f.is_file():
            try:
                f.write_bytes(_norm_lf(f.read_text(encoding="utf-8")).encode("utf-8"))
            except (UnicodeDecodeError, OSError):
                pass  # binary or unreadable - let git apply decide
    subprocess.run(["git", "init", "-q"], cwd=sandbox, capture_output=True)
    patch_bytes = patch.encode("utf-8")
    last = ""
    for extra in _APPLY_PASSES:
        proc = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", *extra, "-"],
            cwd=sandbox, input=patch_bytes, capture_output=True,
        )
        if proc.returncode == 0:
            return True, f"applied ({' '.join(extra) or 'exact'})"
        last = (proc.stderr or proc.stdout).decode("utf-8", "replace")
    # git rejected every pass - often a malformed hunk header (e.g. a bare "@@"
    # with no line numbers, which some models emit). Last resort: match each
    # hunk's old block against the file by content and swap in the new block.
    # Exact contiguous match only, so a correct fix applies but a wrong one can't
    # be misapplied.
    if _fuzzy_apply(patch, sandbox):
        return True, "applied (content match)"
    return False, last.strip()


def _find_block(lines: list[str], block: list[str]) -> int | None:
    n = len(block)
    if n == 0:
        return None
    for i in range(len(lines) - n + 1):
        if lines[i : i + n] == block:
            return i
    return None


def _fuzzy_apply(patch: str, sandbox: Path) -> bool:
    # Apply a single-file diff by CONTENT, ignoring the hunk headers: for each
    # hunk, find its old block (context + '-' lines) verbatim in the file and
    # replace it with the new block (context + '+' lines). Bails on any ambiguity,
    # so it recovers a correct fix with a bad header without risking a misapply.
    targets = _targets(patch)
    if not targets:
        # Some models omit the ---/+++ lines; fall back to `diff --git a/X b/X`.
        for line in patch.splitlines():
            if line.startswith("diff --git "):
                p = line.split()[-1]
                targets = [p[2:] if p.startswith(("a/", "b/")) else p]
                break
    if len(targets) != 1:
        return False
    f = sandbox / targets[0]
    if not f.is_file():
        return False
    try:
        content = _norm_lf(f.read_text(encoding="utf-8")).split("\n")
    except (UnicodeDecodeError, OSError):
        return False

    hunks: list[list[str]] = []
    cur: list[str] | None = None
    for ln in _norm_lf(patch).split("\n"):
        if ln.startswith("@@"):
            cur = []
            hunks.append(cur)
        elif ln.startswith(("diff ", "--- ", "+++ ", "index ")):
            cur = None
        elif cur is not None:
            cur.append(ln)
    if not hunks:
        return False

    for hunk in hunks:
        old_block, new_block = [], []
        for ln in hunk:
            tag = ln[:1]
            if ln.startswith("\\"):
                continue  # "\ No newline at end of file" - metadata
            if tag == "+":
                new_block.append(ln[1:])
            elif tag == "-":
                old_block.append(ln[1:])
            elif tag == " ":
                old_block.append(ln[1:])
                new_block.append(ln[1:])
            elif ln == "":
                old_block.append("")
                new_block.append("")
            else:
                return False  # unexpected line -> bail rather than risk it
        while old_block and new_block and old_block[-1] == "" and new_block[-1] == "":
            old_block.pop()
            new_block.pop()
        idx = _find_block(content, old_block)
        if idx is None:
            return False
        content = content[:idx] + new_block + content[idx + len(old_block) :]

    try:
        f.write_bytes(("\n".join(content)).encode("utf-8"))
    except OSError:
        return False
    return True


def verify_patch(
    patch: str,
    workdir: Path | str,
    test_cmd: list[str],
    *,
    timeout: int = 180,
) -> VerifyResult:
    # Apply `patch` to a copy of `workdir`, run `test_cmd` there, report the verdict.
    workdir = Path(workdir)
    if not (patch or "").strip():
        return VerifyResult(False, False, 0, 0, "", error="empty patch")
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp) / "repo"
        shutil.copytree(workdir, sandbox)
        applied, apply_log = _apply(patch, sandbox)
        if not applied:
            return VerifyResult(False, False, 0, 0, apply_log, error="patch did not apply")
        try:
            proc = subprocess.run(
                test_cmd, cwd=sandbox, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return VerifyResult(True, False, 0, 0, "test run timed out", error="timeout")
        out = (proc.stdout or "") + (proc.stderr or "")
        passed, total = _parse_pytest(out)
        return VerifyResult(
            applies=True,
            tests_passed=(proc.returncode == 0),
            passed=passed,
            total=total,
            evidence=out[-2000:],
        )
