# Old build (archived)

This file preserves the project's original framing, kept for context only. It is
**not** how the system works today. The live product is a **verification-backed trust
layer for multi-agent coding** (see the [README](README.md)); this document records
what came before the pivot so the history stays honest without cluttering the rest of
the tree.

## What the project originally was

Agenclave began as an **honest, open-source reproduction of the "Chairman LLM"
pattern**: dispatch a coding task to N model-agents in parallel, then have a
"Chairman" judge LLM score the candidate patches and select or synthesise the best
one. Success was framed as a **SWE-bench Lite resolve rate**.

Two stages:

- **Stage 1 - triage classifier** (still shipped, unchanged): TF-IDF -> issue type,
  used as the gate for Stage 2.
- **Stage 2 - Chairman best-of-N harness**: send the SWE-bench task to N agents,
  judge, and emit SWE-bench-format predictions.

## How it was measured (SWE-bench resolve rate)

The harness deliberately did **not** self-report a resolve rate. `scripts/run_chairman.py`
produced candidate patches, the Chairman's selection, and SWE-bench-format
`preds_*.jsonl` files. Real numbers came only from the **official SWE-bench evaluation
harness** (applies each patch, runs the repo's FAIL_TO_PASS tests in Docker), driven
by `scripts/grade_swebench.py`. The rule was: any number is from a real run or it says
TBD; a negative result (best-of-N not beating the best single agent) would be reported
plainly. The early honest number was low.

Artifacts this produced, all since **removed** from the live tree:

- Scripts: `scripts/run_chairman.py`, `scripts/grade_swebench.py`
- Results: `results/chairman_eval.json`, `results/preds_*.jsonl`, `results/resolve_rate.json`
- API endpoints: `GET /runs/latest` (served the committed `chairman_eval.json` demo)
  and `GET /resolve-rate` (served the offline SWE-bench grade)
- `make stage2` (ran `run_chairman.py`)

## Why it changed

Chasing a raw SWE-bench resolve rate made the project a weaker generator competing
head-on with frontier systems, and the honest early number was low. The more
defensible and more useful question turned out to be **"which of N agent outputs do I
trust?"** - so the product pivoted to a verification-backed trust layer with
**trust-scored routing** (Thompson sampling over per-model reliability, fed only by
in-loop verification, never a held-out grade).

The **Chairman judge survived as a component** of the live pipeline (it still ranks
candidate patches when there is no repo to run tests against). What did not survive
was the "reproduce-the-Chairman-and-benchmark-on-SWE-bench" *framing* and its scoring
machinery. Everything about the current system lives in the README.
