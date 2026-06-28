# Design notes

A few notes to myself on the decisions that weren't obvious, so I remember why
I did things the way I did. Roughly newest first.

## Why the classifier ships type-only

The label set I originally wanted was `{bug, feature_request, performance,
question/other}` plus a severity level. Two parts of that didn't survive contact
with the available data, and I decided I'd rather cut them honestly than fake
them.

- **No `performance` class.** None of the public, citable issue datasets label a
  "performance" category, so there are no gold labels to train or evaluate on. I
  dropped it and say so in the README rather than inventing labels.
- **No severity head in the shipped model.** I could not find a severity dataset
  that was both cleanly licensed and downloadable at a usable size. The one
  workable source (a Bugzilla/Eclipse mirror on HuggingFace) is citation-only,
  with no real OSS license. I didn't want a portfolio deliverable resting on an
  unlicensed source, and I won't fabricate labels, so severity is omitted from
  what ships. The code path still exists behind `--with-severity` for local
  experimentation, but nothing it produces is part of the deliverable.

So the shipped classifier is four-class issue-type only:
`{bug, feature_request, documentation, question_other}`, trained on NLBSE'23.

## Why I serve TF-IDF and not the transformer

I trained four configs per task: `{TF-IDF, MiniLM embeddings} x {LogReg,
RandomForest}`. The interesting result is that MiniLM embeddings did *not* beat
TF-IDF here (test macro-F1 0.628 vs 0.675, so the transformer is about 0.047
worse). On short issue text with a fairly focused vocabulary, a linear model on
TF-IDF features is stronger, lighter, and gives interpretable top tokens for
free. I serve TF-IDF + LogReg and report the comparison straight, including the
fact that the fancier approach lost.

The served model is also torch-free on purpose: the FastAPI service imports the
inference path without pulling in torch or sentence-transformers, so it stays
light. The MiniLM variants are still trained and scored, just not served.

## How the two stages fit together

Stage 1 (the classifier) is the front door. It sorts an incoming issue and
annotates it before anything expensive happens. Stage 2 (the Chairman harness)
is the part that mirrors BlackBox's pattern: send the same coding task to N
model-agents at once, then have a judge LLM rank the candidate patches and pick
or synthesise the best.

Everything in Stage 2 depends only on the small `Agent` / `Task` /
`PatchResult` / `ChairmanDecision` contracts in `harness/interfaces.py`, never
on a vendor SDK directly. That's what lets me switch between the direct
Claude/OpenAI adapter and the BlackBox adapter with one config value.

## On measuring resolve rate honestly

The harness produces candidate patches and the Chairman's choice. It does not
report a resolve rate, because a real resolve rate means applying each patch and
running the repo's `FAIL_TO_PASS` tests, which is what the official SWE-bench
evaluation harness does in Docker. I write the predictions out in SWE-bench
format and leave the grading to that harness. Any number in the README comes
from a real run or it says TBD. I'd rather report a negative result (best-of-N
doesn't beat the best single agent) than a made-up positive one.

## Small things worth remembering

- The pinned `anthropic` SDK is older than adaptive thinking and
  `output_config`, so the agent and judge calls stick to the stable
  `messages.create` surface, with forced tool use for the judge's strict JSON.
  If I upgrade the SDK I can turn on `thinking={"type": "adaptive"}` for the
  judge.
- Stage 1 needs no API keys. Keys only matter for the Stage 2 live runs.
- Datasets and trained model binaries are gitignored; the small metrics JSON and
  confusion-matrix image are tracked so the results are visible in the repo.
