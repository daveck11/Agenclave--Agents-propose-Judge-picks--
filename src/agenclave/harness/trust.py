# Trust ranking - the Chairman reborn as a verifier.
#
# Given candidate patches and their VerifyResults, rank them by DEMONSTRATED
# trustworthiness (what actually applies and passes) rather than by how a diff
# reads. This answers the product's core question - "which of these agent outputs
# do I trust?" - with evidence, not vibes.
#
# Two trained signals are fused on top of that verification spine, but neither can
# override it:
#   * per-model reliability (harness/reliability.py) - how often this model's
#     patches have passed in-loop verification before. Used only to break ties
#     between candidates that are equally good on the CURRENT task.
#   * triage confidence (Stage 1 classifier) - when the front-door label is weak,
#     the whole verdict set is flagged for a human second look.
# Hard verification evidence on this task always dominates the ranking.

from __future__ import annotations

from dataclasses import dataclass

from .interfaces import PatchResult
from .reliability import reliability as _reliability
from .verify import VerifyResult

# Confidence below this is "weak" -> annotate the verdicts with a caution. Reused
# from the Stage 1 recommender so the trust layer and the front door agree on the
# threshold.
from ..classifier.recommend import LOW_CONFIDENCE

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
    reliability: float = 0.5  # Beta(1,1)-smoothed pass rate; 0.5 = no track record
    reliability_n: int = 0  # number of prior verified outcomes behind `reliability`


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


def _reliability_phrase(passed: int, total: int) -> str:
    # Human-readable evidence for the reason string.
    if total == 0:
        return "no track record yet"
    return f"this model resolved {passed}/{total} bugs historically"


def trust_rank(
    candidates: list[PatchResult],
    verify_results: dict[str, VerifyResult],
    *,
    category: str | None = None,
    triage_confidence: float | None = None,
) -> list[TrustVerdict]:
    # Rank candidates best-first. Verification tier is PRIMARY. Within an equal
    # tier+score, tiebreak by learned reliability (higher first), then by
    # minimality - a smaller verified diff is preferred (less collateral surface).
    #
    # `category` (the Stage 1 triage label) enables the reliability lookup and its
    # mention in the reason. `triage_confidence`, when weak, appends a caution to
    # every verdict - the trained front-door signal, fused but non-overriding.
    patch_len = {c.agent_name: len(c.patch or "") for c in candidates}
    verdicts = [_verdict(c, verify_results.get(c.agent_name)) for c in candidates]

    if category is not None:
        for v in verdicts:
            est, passed, total = _reliability(v.agent_name, category)
            v.reliability = est
            v.reliability_n = total
            v.reason = f"{v.reason}; {_reliability_phrase(passed, total)}"

    if triage_confidence is not None and triage_confidence < LOW_CONFIDENCE:
        caution = (
            f" (caution: triage only {triage_confidence:.0%} confident - "
            "verify the label before trusting this ranking)"
        )
        for v in verdicts:
            v.reason += caution

    verdicts.sort(
        key=lambda v: (
            _TIER_ORDER[v.tier],
            -v.score,
            -v.reliability,
            patch_len.get(v.agent_name, 0),
        )
    )
    return verdicts
