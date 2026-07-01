# Verification primitive for the trust layer.
#
# Apply a candidate patch to a throwaway copy of a working tree and run its tests,
# returning an evidence-bearing verdict. This is the trust signal that replaces the
# blind LLM judge: the Chairman reborn ranks candidates by what ACTUALLY passes,
# not by how a diff reads. Never raises for normal failures (a patch that doesn't
# apply, failing tests, a timeout) — they are captured in the result, mirroring the
# PatchResult / dispatch contract.

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_SUMMARY_RE = re.compile(r"(\d+) (passed|failed|errors?)")


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
    # git apply is a reliable, cross-platform, atomic patch applier (a failed apply
    # leaves the tree untouched, so the -p1 fallback is safe). Normalise line endings
    # on BOTH the patch and the target files to LF and send the patch as raw bytes —
    # otherwise stdin text-mode translation (\n->\r\n on Windows) breaks context
    # matching against LF source files.
    patch = _norm_lf(patch)
    for rel in _targets(patch):
        f = sandbox / rel
        if f.is_file():
            try:
                f.write_bytes(_norm_lf(f.read_text(encoding="utf-8")).encode("utf-8"))
            except (UnicodeDecodeError, OSError):
                pass  # binary or unreadable — let git apply decide
    subprocess.run(["git", "init", "-q"], cwd=sandbox, capture_output=True)
    last = ""
    for extra in ([], ["-p1"]):
        proc = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", *extra, "-"],
            cwd=sandbox, input=_norm_lf(patch).encode("utf-8"), capture_output=True,
        )
        if proc.returncode == 0:
            return True, "patch applied"
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
