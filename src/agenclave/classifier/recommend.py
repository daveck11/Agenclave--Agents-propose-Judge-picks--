# Deterministic, torch-free next-step recommendations for a triaged issue.
#
# Pure rules keyed on the Stage 1 prediction (`label` + `label_confidence`, and
# `severity` when present). No model, no I/O, no randomness, so the same triage
# always yields the same advice. `bug` is the only label that may proceed to the
# Stage 2 code-fix agents; everything else routes to a human workflow.

from __future__ import annotations

# Confidence below this is treated as "weak" -> prepend a manual-review caution.
LOW_CONFIDENCE = 0.5


def _rec(title: str, detail: str, kind: str) -> dict:
    return {"title": title, "detail": detail, "kind": kind}


def _severity_urgency(severity: str | None) -> str:
    # Map an optional coarse severity onto urgency wording for the rec details.
    if severity == "high":
        return "Treat as urgent"
    if severity == "medium":
        return "Prioritise normally"
    if severity == "low":
        return "Low urgency"
    return "Prioritise"


def recommend(triage: dict) -> dict:
    # Turn a triage result into concrete next steps + a Stage 2 gate decision.
    #
    #     Returns `{"recommendations": [{title, detail, kind}, ...],
    #     "can_proceed_to_stage2": bool}`. Only `bug` can proceed.
    label = triage.get("label", "")
    confidence = float(triage.get("label_confidence", triage.get("confidence", 0.0)))
    severity = triage.get("severity")
    urgency = _severity_urgency(severity)

    recs: list[dict] = []
    can_proceed = False

    if label == "bug":
        can_proceed = True
        recs.extend(
            [
                _rec(
                    "Reproduce the bug",
                    f"{urgency}: confirm exact reproduction steps and the "
                    "environment before changing code.",
                    "action",
                ),
                _rec(
                    "Add a failing regression test",
                    "Capture the defect as a test that fails today and will guard "
                    "against regressions once fixed.",
                    "action",
                ),
                _rec(
                    "Search for duplicates",
                    "Check open/closed issues for an existing report or fix to "
                    "avoid duplicated effort.",
                    "action",
                ),
                _rec(
                    "Send to the code-fix agents",
                    "This looks like a bug — proceed to Stage 2 best-of-N dispatch "
                    "so the agents can propose a patch.",
                    "proceed",
                ),
            ]
        )
    elif label == "feature_request":
        recs.extend(
            [
                _rec(
                    "Write acceptance criteria and scope",
                    "Define what 'done' means and bound the scope before any "
                    "implementation work.",
                    "action",
                ),
                _rec(
                    "Check the roadmap and duplicates",
                    "Confirm it isn't already planned or requested elsewhere.",
                    "action",
                ),
                _rec(
                    "Label and prioritise",
                    f"{urgency}: triage onto the backlog with the right labels and "
                    "priority.",
                    "action",
                ),
            ]
        )
    elif label == "documentation":
        recs.extend(
            [
                _rec(
                    "Locate the affected doc page",
                    "Find the page or section that is missing/incorrect so the fix "
                    "is targeted.",
                    "action",
                ),
                _rec(
                    "Mark as good-first-issue",
                    "Docs changes are approachable — flag for new contributors.",
                    "action",
                ),
                _rec(
                    "Link the contributing guide",
                    "Point the reporter at the contribution + docs style guide.",
                    "action",
                ),
            ]
        )
    elif label == "question_other":
        recs.extend(
            [
                _rec(
                    "Convert to a discussion / Q&A",
                    "This reads as a question — move it to discussions or a Q&A "
                    "channel rather than the issue tracker.",
                    "action",
                ),
                _rec(
                    "Link docs and support",
                    "Point to the relevant documentation or support resources.",
                    "action",
                ),
                _rec(
                    "Request a minimal repro",
                    "If it may be a defect, ask for a minimal reproducible example "
                    "to re-triage.",
                    "action",
                ),
            ]
        )
    else:
        # Unknown/unseen label: stay safe, route to a human.
        recs.append(
            _rec(
                "Manual triage required",
                f"Unrecognised label {label!r}; route to a human for review.",
                "caution",
            )
        )

    if confidence < LOW_CONFIDENCE:
        recs.insert(
            0,
            _rec(
                "Low confidence — manual review suggested",
                f"The classifier is only {confidence:.0%} confident in "
                f"'{label}'. Double-check the label before acting.",
                "caution",
            ),
        )

    return {"recommendations": recs, "can_proceed_to_stage2": can_proceed}
