# Agenclave

> A **verification-backed trust layer for multi-agent coding**. As agents outpace
> human review, the bottleneck stops being generating code and becomes trusting it.
> Agenclave answers one question with evidence: **which of N agent outputs do I
> trust?**

**Status:** ✅ triage classifier + ✅ trust-scored best-of-N harness, wrapped in an
account-backed web app: triage → gate → **route to the trusted models** → judge →
**verify each patch and rank by what passes**. One command to run it: **`make app`**.
All ML numbers below are from real runs.

---

## What it does

```
   issue {title, body}
        │
        ▼
 ┌──────────────────────────────┐   "bug" → proceed (non-bugs filtered, $0)
 │ TRIAGE  TF-IDF classifier    │ ──────────────┐
 │ type + confidence + next steps│              ▼
 └──────────────────────────────┘   ┌───────────────────────────────────────────┐
                                     │ TRUST-SCORED ROUTING                        │
                                     │  Thompson-sample per-model reliability →    │
                                     │  dispatch only the trusted top-k agents     │
                                     │        │                                    │
                                     │        ▼                                    │
                                     │  candidate patches → Chairman judge →       │
                                     │  verify each patch (apply + run tests) →    │
                                     │  rank by what actually passes               │
                                     └───────────────────────────────────────────┘

  Logged-in users save issues + runs and revisit them in a per-user Workspace.
```

Providers are pluggable behind one `Agent` interface
(`src/agenclave/harness/interfaces.py`): a **direct** adapter (Claude/OpenAI) and a
**BlackBox Agents API** adapter, switchable by config. The project runs its own agents
*through* BlackBox and adds the trust layer on top.

## The trust layer

- **Trust-scored routing.** Each model has a per-category reliability learned from
  in-loop verification (`Beta(passed+1, failed+1)`). Routing draws a Thompson sample
  per model and dispatches only the top `route_k`, so an unreliable model is
  transparently dropped - and the UI shows which models were considered, which were
  picked, and why.
- **Verification decides the winner, not reputation.** Reliability only chooses *who
  competes*. The winner of a given task is decided fresh: apply each candidate patch,
  run the tests, tier it (`trusted` / `applies_but_fails` / `broken`), and rank by
  what passes. A historically weak model can still win a specific task on the merits,
  and the prior never becomes a self-fulfilling prophecy.
- **No leakage.** Per-model reliability is fed **only** by in-loop verification and is
  kept strictly separate from any held-out grader. The web path (no repo checkout)
  judges with the Chairman LLM and deliberately writes **no** reliability signal.

## The app

- **Triage + recommendations** - classify an issue and get deterministic, per-type
  next steps. Bugs surface a one-click **"Send to the code-fix agents →"**.
- **Code-fix** - the issue is routed to the trusted subset and dispatched (dry run by
  default; live spends credits). The routing decision, candidate patches, and the
  Chairman's pick are shown. Logged-in users can **save** a run (nothing auto-saves)
  and delete it later.
- **Accounts + Workspace** - register/log in (bcrypt + JWT); save issues and runs and
  revisit them per-user. The anonymous demo works without an account.
- **Distributable** - `make app` builds the React app and serves the whole product
  (UI + API) from a single `uvicorn` process on one origin.

## Quickstart

```bash
make setup     # venv + pinned deps (CPU-only torch)
make stage1    # data -> train -> eval  (writes results/classifier_metrics.json)

make app       # builds frontend/dist, serves everything on http://localhost:8000

# Develop with hot reload (two terminals):
make serve     # FastAPI on :8000
make demo      # Vite dev server on :5173 (proxies to :8000)

make test      # pytest
make trust     # verified best-of-N -> per-model reliability (dry run by default)
```

Accounts/persistence need no setup - SQLite is created on first start
(`data/agenclave.db`). Set a real `SECRET_KEY` in `.env` for anything beyond local
use. Live runs need a provider key (`BLACKBOX_API_KEY`, or `ANTHROPIC_API_KEY` /
`OPENAI_API_KEY`) in `.env`.

Windows without `make`: run the one-line equivalent per target (see the `Makefile`).

## Results

### Triage classifier (issue type, 4 classes, held-out test n = 1,793)
| Estimator        | Features      | Macro-F1  | Accuracy |
| ---------------- | ------------- | --------- | -------- |
| **Logistic Reg.**| **TF-IDF**    | **0.675** | 0.674    |
| Random Forest    | TF-IDF        | 0.653     | 0.655    |
| Logistic Reg.    | MiniLM embed. | 0.628     | 0.628    |
| Random Forest    | MiniLM embed. | 0.569     | 0.578    |

> **Honest finding:** MiniLM embeddings did **not** beat TF-IDF on this task (lift
> **−0.047**). On short issue text a linear TF-IDF model is both stronger and lighter,
> so we serve it (torch-free + interpretable top tokens). Per-class metrics +
> confusion matrix: [`results/`](results/) and the [model card](models/MODEL_CARD.md).

### Trust-scored routing
Per-model reliability is learned in-loop by the verified harness (`make trust`,
`scripts/verified_run.py`) and stored in `results/model_reliability.json`. It is
small-`n` by design and moves as more verified runs accumulate - the point is the
*mechanism* (verify → tier → rank → route), not a headline score. Reliability is never
seeded from any held-out grade (see "No leakage" above). Offline demos with no network
or API keys: `scripts/demo_router.py` (Thompson routing) and `scripts/demo_trust.py`
(verification-backed ranking).

## Datasets

See [`data/README.md`](data/README.md) for exact sources, licenses, and row counts.

> **Scope note (integrity):** the classifier ships an **issue-type** head only
> (`{bug, feature_request, documentation, question_other}`, NLBSE'23). Two
> intended-but-dropped labels are documented as deliberate omissions: **`performance`**
> (no gold labels exist in any citable source) and a **severity** head (no cleanly
> OSS-licensed, fetchable source was found). Nothing is fabricated to fill these gaps.

## Repo layout

```
src/agenclave/
  classifier/   feature pipeline, training, inference, recommendations (triage)
  api/          FastAPI app factory; routes/ (triage, auth, issues, runs);
                db.py + models.py (SQLAlchemy), auth.py (bcrypt + JWT)
  harness/      Agent interface, providers, dispatch, Chairman judge,
                trust-scored router + reliability store + patch verification
scripts/        prepare_data | train_classifier | evaluate_classifier | verified_run
frontend/src/   React SPA: pages/ (Triage, CodeFix, Workspace, Login, Register),
                components/, auth + issue contexts, api.js
tests/          pytest (features, API contract, auth, recommend, issues/runs,
                harness, reliability)
results/        metrics JSON + plots + the per-model reliability store
```

> The project began as a reproduction of the "Chairman LLM" pattern benchmarked on
> SWE-bench resolve rate; that earlier framing is archived in
> [`OLD_BUILD.md`](OLD_BUILD.md).

## Author
David Nkpa, built as a portfolio project. License: MIT (code).
