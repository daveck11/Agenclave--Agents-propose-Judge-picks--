# Pydantic v2 request/response schemas for the triage API.
#
# These mirror the `predict_triage` contract from
# `agenclave.classifier.predict`, with `label_confidence` exposed to clients
# as the friendlier `confidence` field.

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

# Guard against abuse / accidental megabyte payloads. Issue text is short.
MAX_LEN = 20_000


class TriageRequest(BaseModel):
    # An issue to classify: a required `title` and an optional `body`.

    title: str = Field(..., description="Issue title (required, non-empty).")
    body: str = Field("", description="Issue body (optional).")

    @field_validator("title", "body")
    @classmethod
    def _length_guard(cls, v: str) -> str:
        if v is not None and len(v) > MAX_LEN:
            raise ValueError(f"field too long (max {MAX_LEN} characters)")
        return v

    @model_validator(mode="after")
    def _not_all_blank(self) -> "TriageRequest":
        # Reject payloads that carry no signal at all (both blank/whitespace).
        if not (self.title or "").strip() and not (self.body or "").strip():
            raise ValueError("at least one of 'title' or 'body' must be non-empty")
        return self


class RunRequest(BaseModel):
    # An issue to run through the full pipeline: Stage 1 triage gate, then (if it
    # passes the gate AND `live` is set) the Stage 2 best-of-N dispatch + judge.

    title: str = Field("", description="Issue title.")
    body: str = Field("", description="Issue body (optional).")
    live: bool = Field(
        False,
        description="If true, dispatch to the real providers (spends API credits). "
        "Default is a dry run: triage + gate + cost projection, no calls.",
    )

    @field_validator("title", "body")
    @classmethod
    def _length_guard(cls, v: str) -> str:
        if v is not None and len(v) > MAX_LEN:
            raise ValueError(f"field too long (max {MAX_LEN} characters)")
        return v

    @model_validator(mode="after")
    def _not_all_blank(self) -> "RunRequest":
        if not (self.title or "").strip() and not (self.body or "").strip():
            raise ValueError("at least one of 'title' or 'body' must be non-empty")
        return self


class TriageResponse(BaseModel):
    # The triage prediction returned to clients.
    #
    #     The shipped deliverable is type-only, so `severity` / `severity_confidence`
    #     are nullable: they are populated only when the optional severity head is
    #     present, and `None` otherwise.

    label: str = Field(..., description="Predicted issue type.")
    confidence: float = Field(..., description="Confidence in the TYPE label (0-1).")
    severity: str | None = Field(
        None, description="Predicted coarse severity (null if severity head absent)."
    )
    severity_confidence: float | None = Field(
        None, description="Confidence in the severity label (0-1); null if absent."
    )
    top_tokens: list[str] = Field(
        default_factory=list, description="TF-IDF tokens driving the type prediction."
    )
