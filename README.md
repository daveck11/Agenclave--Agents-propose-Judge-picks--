# Agenclave

> A bug-triage **classifier** feeding a best-of-N multi-agent **code-fix harness**  - 
> an honest, open-source reproduction of the "Chairman LLM" pattern (dispatch a
> coding task to N model-agents in parallel → a Chairman judge scores and
> selects/synthesises the best patch).

**Status:** ✅ Stage 1 complete (type-only triage classifier + FastAPI + React demo). Stage 2 (Chairman harness) pending sign-off. All numbers below are from real runs.

---

## Architecture

```
                 ┌─────────────────────────────────────────────────────┐
   issue  ──────▶│  STAGE 1: Triage classifier (the "front door")       │
 {title, body}   │  TF-IDF / MiniLM embeddings → issue-type label       │
                 └───────────────┬─────────────────────────────────────┘
                                 │  label, confidence
                  filter non-bugs│  annotate task
                                 ▼
                 ┌─────────────────────────────────────────────────────┐
                 │  STAGE 2: Chairman best-of-N harness                 │
                 │                                                       │
                 │     Task ──┬──▶ Agent A (Claude)  ─┐                  │
                 │            ├──▶ Agent B (OpenAI)  ─┤  candidate       │
                 │            └──▶ Agent N (BlackBox)─┘  patches         │
                 │                       │                               │
                 │                       ▼                               │
                 │              Chairman judge LLM  ──▶ ranked pick /    │
                 │              (strict JSON)           synthesis        │
                 └─────────────────────────────────────────────────────┘
```

Providers are pluggable behind one `Agent` interface (`src/agenclave/harness/interfaces.py`):
a **direct** adapter (Claude/OpenAI) and a **BlackBox Agents API** adapter, switchable by config.

## How this maps to BlackBox's Chairman LLM

| BlackBox concept            | Agenclave component                                            |
| --------------------------- | -------------------------------------------------------------- |
| Dispatch task to N agents   | `harness/dispatch.py`, concurrent `asyncio` fan-out           |
| Multiple model-agents       | `Agent` interface + direct / BlackBox adapters                 |
| Chairman judge selects best | `harness/chairman.py`, judge LLM, strict JSON, optional merge |
| Triage / routing front door | Stage 1 classifier filters non-bugs and annotates the task     |

## Quickstart

```bash
make setup     # venv + pinned deps (CPU-only torch)
make stage1    # data -> train -> eval  (writes results/classifier_metrics.json)
make serve     # FastAPI triage service on :8000
make demo      # Vite React demo (separate terminal)
make test      # pytest
# Stage 2 (after sign-off): make stage2
```

Windows without `make`: run the one-line equivalent per target (see the `Makefile`).

## Results

### Stage 1, triage classifier (issue type, 4 classes, held-out test n = 1,793)
| Estimator        | Features      | Macro-F1  | Accuracy |
| ---------------- | ------------- | --------- | -------- |
| **Logistic Reg.**| **TF-IDF**    | **0.675** | 0.674    |
| Random Forest    | TF-IDF        | 0.653     | 0.655    |
| Logistic Reg.    | MiniLM embed. | 0.628     | 0.628    |
| Random Forest    | MiniLM embed. | 0.569     | 0.578    |

> **Honest finding:** MiniLM embeddings did **not** beat TF-IDF on this task
> (lift **−0.047**). On short issue text a linear TF-IDF model is both stronger
> and lighter, so we serve it (torch-free + interpretable top tokens). Per-class
> metrics + confusion matrix: [`results/`](results/) and the
> [model card](models/MODEL_CARD.md).

### Stage 2, Chairman best-of-N (SWE-bench Lite slice)
| Agent / strategy        | Resolve rate |
| ----------------------- | ------------ |
| Best single agent       | TBD          |
| **Chairman best-of-N**  | TBD          |

> Honesty note: if best-of-N does **not** beat the best single agent on the slice,
> it will be reported here plainly. Resolve rate is **not** self-reported by the
> harness, `scripts/run_chairman.py` produces candidate patches, the Chairman's
> selection, and SWE-bench-format `preds_*.jsonl`; real numbers come from running
> the **official SWE-bench evaluation harness** (applies each patch, runs the
> repo's FAIL_TO_PASS tests) on those files. No fabricated scores.
>
> `make stage2` runs a **dry run by default** (loads the slice, runs Stage 1
> triage, projects cost, zero API calls). Add `--live` to spend credits:
> `python scripts/run_chairman.py --live --limit 2`.

## Datasets

See [`data/README.md`](data/README.md) for exact sources, licenses, and row counts.

> **Scope note (integrity):** Stage 1 ships an **issue-type** head only
> (`{bug, feature_request, documentation, question_other}`, NLBSE'23). Two
> intended-but-dropped labels are documented as deliberate omissions, not
> oversights: **`performance`** (no gold labels exist in any citable source) and
> a **severity** head (no cleanly OSS-licensed, fetchable source was found, only
> a citation-only one, which is excluded from the deliverable). Nothing is
> fabricated to fill these gaps.

## Repo layout

```
src/agenclave/
  classifier/   feature pipeline, training, inference (Stage 1)
  api/          FastAPI /triage service (Stage 1)
  harness/      Agent interface, providers, dispatch, Chairman judge (Stage 2)
scripts/        prepare_data | train_classifier | evaluate_classifier | run_chairman
frontend/       Vite React demo
tests/          pytest (feature pipeline, API contract, BlackBox adapter mocks)
results/        metrics JSON + plots
models/         saved models + MODEL_CARD.md
```

## Author
David Nkpa, built as a portfolio project. License: MIT (code).
