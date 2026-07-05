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
    return False, last.strip()


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
