#!/usr/bin/env python3
# Routing demo. Seeds a leader plus a couple of low-data challengers, then
# routes many times to show the behaviour that matters: the leader gets
# picked most but not always, and a model with no history still gets tried.
# Runs offline against a temp store, so the real reliability file is never
# touched.
#
#     python scripts/demo_router.py

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.harness import reliability as rel  # noqa: E402
from agenclave.harness.router import route  # noqa: E402

CATEGORY = "bug"
MODELS = ["claude-sonnet-4.6", "gpt-5.4", "gemini-3.1-flash-lite"]
K = 2  # dispatch a trusted subset of 2 of the 3 models
ROUNDS = 1000

# (model, passed, failed) of made-up past verified runs
HISTORY = [
    ("claude-sonnet-4.6", 7, 3),        # established leader: 7/10
    ("gpt-5.4", 3, 7),                  # middling: 3/10
    ("gemini-3.1-flash-lite", 0, 0),    # newcomer: no track record
]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = f"{tmp}/model_reliability.json"
        for model, passed, failed in HISTORY:
            for _ in range(passed):
                rel.record_outcome(model, CATEGORY, True, path=store)
            for _ in range(failed):
                rel.record_outcome(model, CATEGORY, False, path=store)

        rng = np.random.default_rng(2024)  # seeded for a reproducible demo

        print(f"Task category: {CATEGORY}  |  route top-{K} of {len(MODELS)} models")
        print("Which models do we trust for this task? Sampled from learned trust:\n")

        # one routing decision, fully printed
        dec = route(CATEGORY, MODELS, K, rng=rng, path=store)
        print(f"{'model':<26}{'reliability':<16}{'sample':<10}picked")
        picked = set(dec.selected)
        for c in dec.considered:
            rel_col = f"{c['estimate']:.2f} (n={c['total']})"
            mark = "  <-- routed" if c["model"] in picked else ""
            print(f"{c['model']:<26}{rel_col:<16}{c['sample']:.3f}     {mark}")
        print(f"\n{dec.reason}\n")

        # then selection frequency over many rounds
        counts = {m: 0 for m in MODELS}
        for _ in range(ROUNDS):
            for m in route(CATEGORY, MODELS, K, rng=rng, path=store).selected:
                counts[m] += 1

        print(f"Selection frequency over {ROUNDS} routing rounds (top-{K} each):")
        for m in MODELS:
            pct = counts[m] / ROUNDS
            bar = "#" * round(pct * 40)
            print(f"  {m:<26}{counts[m]:>5}  {pct:6.1%}  {bar}")
        print(
            "\nThe leader is chosen most, but not always; the newcomer is still "
            "explored.\nRouting only picks who runs - trust_rank decides who won."
        )


if __name__ == "__main__":
    main()
