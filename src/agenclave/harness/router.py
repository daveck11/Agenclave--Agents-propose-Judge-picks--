# Picks which models get dispatched for a task category, based on the
# reliability each model has earned from in-loop verification.
#
# Routing is only a prior: it decides who runs. trust_rank still decides who
# won among the ones that ran, so a bad route can't crown a bad patch.
#
# I use Thompson sampling instead of just taking the highest reliability
# because the greedy pick collapses to always-the-leader. Drawing one sample
# per model from Beta(passed+1, fail+1) keeps some exploration: a model with
# little data has a wide posterior and still gets picked sometimes.
#
# This file reads reliability.py and nothing else. Keeping held-out grades
# out of that store is what makes the routing claim defensible.

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .reliability import reliability as _reliability


@dataclass
class RouteDecision:
    selected: list[str]  # models chosen to run, best sample first
    considered: list[dict] = field(default_factory=list)  # per-model detail
    reason: str = ""  # plain-English explanation shown in the UI


def _short(model: str) -> str:
    # "blackboxai/openai/gpt-5.4" -> "GPT-5.4" for display
    return (model.split("/")[-1] if model else "").upper()


def _phrase(considered: list[dict], selected: list[str], category: str | None) -> str:
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
    """Pick the top-k models for a category by Thompson sampling.

    One Beta(passed+1, fail+1) draw per model, keep the k highest samples.
    k >= len(models) just returns everything. `rng` can be passed in for
    reproducible tests, and `path` points at an alternate reliability store
    (used by the tests so they don't touch the real one).
    """
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

    # ties: point estimate, then input order, so results are deterministic
    # for a fixed rng and store
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
