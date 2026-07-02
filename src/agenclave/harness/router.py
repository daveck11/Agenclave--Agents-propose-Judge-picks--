# Task->model routing - the north star: "which model do I trust for this task?"
#
# BlackBox routes across models but is famously opaque about which model it picks
# and why. This router picks a TRUSTED SUBSET (top-k) of the available models for a
# given task category and explains the choice, using the per-model reliability
# Round 2 learned from in-loop verification.
#
# It is a PRIOR, not a verdict: routing decides WHO RUNS from history; verification
# (harness/trust.trust_rank) still decides WHO WON among those who ran, and always
# overrides the prior on the current task. The router never selects a winner.
#
# Why Thompson sampling (not "pick the highest reliability"): the greedy choice
# collapses to always-the-leader (e.g. always Claude) - the explore/exploit trap.
# Instead we draw one sample per model from its Beta(passed+1, fail+1) posterior -
# the exact counts reliability.py stores - and take the top-k by sample. Low-data
# models have a wide Beta and still get explored; the leader wins MORE OFTEN, not
# ALWAYS.
#
# Reads ONLY reliability.py (fed solely by in-loop verify_patch). It must never
# touch any SWE-bench grade or its artifacts - that stays a separate, out-of-loop
# final scorer.

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .reliability import reliability as _reliability


@dataclass
class RouteDecision:
    # The routing verdict for one task category.
    selected: list[str]  # models chosen to run, best sample first
    considered: list[dict] = field(default_factory=list)  # per-model detail
    reason: str = ""  # human explanation - the transparency payoff


def _short(model: str) -> str:
    # Display a model id as just the model name in caps (drop the provider path).
    return (model.split("/")[-1] if model else "").upper()


def _phrase(considered: list[dict], selected: list[str], category: str | None) -> str:
    # A plain-language justification naming who was picked and hinting at why.
    cat = category or "uncategorised"
    picked = ", ".join(_short(s) for s in selected) if selected else "(none)"
    unproven = [_short(c["model"]) for c in considered if c["total"] == 0]
    tail = ""
    if unproven:
        tail = (
            f" (no track record yet for {', '.join(unproven)}; explored on the "
            "Beta(1,1) prior)"
        )
    return (
        f"routed to {picked} for '{cat}': Thompson-sampled from per-model trust"
        f"{tail}. Verification on this task still decides the winner."
    )


def route(
    category: str | None,
    models: list[str],
    k: int,
    *,
    rng: np.random.Generator | None = None,
    path=None,
) -> RouteDecision:
    # Pick the top-`k` models for `category` by Thompson sampling their reliability.
    #
    #     For each model, draw one sample from Beta(passed+1, fail+1) using the
    #     stored counts, then keep the k highest. `k >= len(models)` returns all
    #     (degenerate but valid); `k <= 0` is a configuration error.
    #
    #     `rng` is injectable for reproducible demos/tests; `path` overrides the
    #     reliability store location (test isolation), mirroring reliability.py.
    if not models:
        raise ValueError("route requires at least one candidate model")
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")
    if rng is None:
        rng = np.random.default_rng()

    considered: list[dict] = []
    for model in models:
        estimate, passed, total = _reliability(model, category, path=path)
        fail = total - passed
        sample = float(rng.beta(passed + 1, fail + 1))
        considered.append(
            {
                "model": model,
                "estimate": estimate,
                "passed": passed,
                "total": total,
                "sample": sample,
            }
        )

    # Highest sample first; break ties by point estimate, then by input order so a
    # given (rng, counts) is fully deterministic.
    order = {m: i for i, m in enumerate(models)}
    ranked = sorted(
        considered,
        key=lambda c: (-c["sample"], -c["estimate"], order[c["model"]]),
    )
    selected = [c["model"] for c in ranked[: min(k, len(models))]]

    return RouteDecision(
        selected=selected,
        considered=ranked,
        reason=_phrase(ranked, selected, category),
    )
