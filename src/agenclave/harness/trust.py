# Trust ranking — the Chairman reborn as a verifier.
#
# Given candidate patches and their VerifyResults, rank them by DEMONSTRATED
# trustworthiness (what actually applies and passes) rather than by how a diff
# reads. This answers the product's core question — "which of these agent outputs
# do I trust?" — with evidence, not vibes.

from __future__ import annotations

from dataclasses import dataclass

from .interfaces import PatchResult
from .verify import VerifyResult

# Trust tiers, best first.
TRUSTED = "trusted"
APPLIES_BUT_FAILS = "applies_but_fails"
BROKEN = "broken"
_TIER_ORDER = {TRUSTED: 0, APPLIES_BUT_FAILS: 1, BROKEN: 2}


@dataclass
class TrustVerdict:
    agent_name: str
    tier: str
    score: float  # 0..1, higher = more trustworthy
    reason: str
    verify: VerifyResult


def _verdict(candidate: PatchResult, vr: VerifyResult | None) -> TrustVerdict:
    if vr is None or not candidate.ok:
        return TrustVerdict(
            candidate.agent_name, BROKEN, 0.0, "no usable patch produced",
            vr or VerifyResult(False, False, 0, 0, "", error="not verified"),
        )
    if not vr.applies:
        return TrustVerdict(
            candidate.agent_name, BROKEN, 0.1, "patch does not apply cleanly", vr
        )
    if vr.tests_passed:
        return TrustVerdict(
            candidate.agent_name, TRUSTED, 1.0,
            f"applies and all tests pass ({vr.passed}/{vr.total})", vr,
        )
    return TrustVerdict(
        candidate.agent_name, APPLIES_BUT_FAILS, 0.5,
        f"applies but tests fail ({vr.passed}/{vr.total} passed)", vr,
    )


def trust_rank(
    candidates: list[PatchResult],
    verify_results: dict[str, VerifyResult],
) -> list[TrustVerdict]:
    # Rank candidates best-first. Tiebreak trusted patches by minimality — a smaller
    # verified diff is preferred (less collateral surface).
    patch_len = {c.agent_name: len(c.patch or "") for c in candidates}
    verdicts = [_verdict(c, verify_results.get(c.agent_name)) for c in candidates]
    verdicts.sort(
        key=lambda v: (_TIER_ORDER[v.tier], -v.score, patch_len.get(v.agent_name, 0))
    )
    return verdicts
