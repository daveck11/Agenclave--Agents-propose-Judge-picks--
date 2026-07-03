# Design notes

A few notes to myself on the decisions that weren't obvious, so I remember why I did
things the way I did. Roughly newest first.

## Why routing decides who competes but verification decides who wins

Per-model reliability (a `Beta(passed+1, failed+1)` per category) only chooses which
models get dispatched for a task - it never crowns the winner. The winner is decided
fresh by verification: apply each candidate patch, run the task's own tests, tier it
(trusted / applies_but_fails / broken), and rank by what passes. This keeps a
historically weak model able to win a specific task on the merits, and stops the
reliability prior from becoming a self-fulfilling prophecy. Routing uses Thompson
sampling (not greedy argmax) so low-data models still get explored.

## Why the trust signal must never touch a held-out grade

Reliability is fed ONLY by in-loop verification - the task's own tests that the
harness runs itself. It is never seeded from a hidden held-out grade or its artifacts.
If the prior were trained on the same signal used to judge the system, the numbers
would be leaked and meaningless. `scripts/verified_run.py` is the only path that writes
reliability, and it only writes what `verify_patch` actually observed. The web path has
no repo checkout, so it judges with the Chairman LLM and writes no reliability at all.

## Why the classifier ships type-only

The label set I originally wanted was `{bug, feature_request, performance,
question/other}` plus a severity level. Two parts of that didn't survive contact with
the available data, and I decided I'd rather cut them honestly than fake them.

- **No `performance` class.** None of the public, citable issue datasets label a
  "performance" category, so there are no gold labels to train or evaluate on. I
  dropped it and say so rather than inventing labels.
- **No severity head in the shipped model.** I could not find a severity dataset that
  was both cleanly licensed and downloadable at a usable size. The one workable source
  (a Bugzilla/Eclipse mirror on HuggingFace) is citation-only, with no real OSS
  license. The code path still exists behind `--with-severity` for local
  experimentation, but nothing it produces is part of the deliverable.

So the shipped classifier is four-class issue-type only:
`{bug, feature_request, documentation, question_other}`, trained on NLBSE'23.

## Why I serve TF-IDF and not the transformer

I trained four configs per task: `{TF-IDF, MiniLM embeddings} x {LogReg,
RandomForest}`. The interesting result is that MiniLM embeddings did *not* beat TF-IDF
here (test macro-F1 0.628 vs 0.675, so the transformer is about 0.047 worse). On short
issue text with a fairly focused vocabulary, a linear model on TF-IDF features is
stronger, lighter, and gives interpretable top tokens for free. I serve TF-IDF +
LogReg and report the comparison straight, including the fact that the fancier approach
lost.

The served model is also torch-free on purpose: the FastAPI service imports the
inference path without pulling in torch or sentence-transformers, so it stays light.

## Small things worth remembering

- Everything in the harness depends only on the small `Agent` / `Task` /
  `PatchResult` / `ChairmanDecision` contracts in `harness/interfaces.py`, never on a
  vendor SDK directly. That's what lets me switch between the direct Claude/OpenAI
  adapter and the BlackBox adapter with one config value.
- The pinned `anthropic` SDK is older than adaptive thinking and `output_config`, so
  the agent and judge calls stick to the stable `messages.create` surface, with forced
  tool use for the judge's strict JSON.
- Triage needs no API keys. Keys only matter for live dispatch.
- The earlier "Chairman reproduction on SWE-bench resolve rate" framing is archived in
  `OLD_BUILD.md`.
