# Pydantic v2 request/response schemas for the triage API.
#
# These mirror the `predict_triage` contract from
# `agenclave.classifier.predict`, with `label_confidence` exposed to clients
# as the friendlier `confidence` field.

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

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
    issue_id: int | None = Field(
        None,
        description="Optional saved-issue id to associate the run with (authed only).",
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


class RunSaveRequest(BaseModel):
    # A completed run the user chose to keep (runs are not auto-persisted).

    title: str = Field("", description="Issue title.")
    body: str = Field("", description="Issue body.")
    issue_id: int | None = Field(None, description="Optional saved-issue id.")
    result: dict = Field(..., description="The run result payload from POST /runs.")


class Recommendation(BaseModel):
    # A single suggested next step for a triaged issue.

    title: str = Field(..., description="Short action label.")
    detail: str = Field(..., description="What to do and why.")
    kind: str = Field(
        ..., description="One of: action, proceed, caution."
    )


class TriageResponse(BaseModel):
    # Triage prediction returned to clients. severity fields are null unless
    # the optional severity model is present (the shipped model is type-only).

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
    recommendations: list[Recommendation] = Field(
        default_factory=list, description="Suggested next steps for this issue."
    )
    can_proceed_to_stage2: bool = Field(
        False, description="True only for bugs (eligible for the code-fix agents)."
    )


# --- Accounts / persistence (Stage 3) -----------------------------------------


class RegisterRequest(BaseModel):
    # Credentials for creating an account.

    email: EmailStr = Field(..., description="Account email (unique).")
    password: str = Field(..., min_length=8, max_length=128, description="Password.")


class LoginRequest(BaseModel):
    # Credentials for obtaining a token.

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    # Public view of a user account.

    id: int
    email: EmailStr
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    # An issued access token plus the authenticated user.

    access_token: str
    token_type: str = "bearer"
    user: UserOut


class IssueCreate(BaseModel):
    # A triaged issue to persist (snapshots the Stage 1 prediction).

    title: str = Field(..., description="Issue title.")
    body: str = Field("", description="Issue body (optional).")
    label: str = Field(..., description="Predicted issue type.")
    confidence: float = Field(..., description="Confidence in the type label (0-1).")
    severity: str | None = Field(None, description="Coarse severity (optional).")
    top_tokens: list[str] = Field(
        default_factory=list, description="Tokens driving the prediction."
    )
    recommendations: list[Recommendation] = Field(
        default_factory=list, description="Recommendation snapshot."
    )

    @field_validator("title", "body")
    @classmethod
    def _length_guard(cls, v: str) -> str:
        if v is not None and len(v) > MAX_LEN:
            raise ValueError(f"field too long (max {MAX_LEN} characters)")
        return v


class IssueOut(BaseModel):
    # A persisted issue returned to its owner.

    id: int
    title: str
    body: str
    label: str
    confidence: float
    severity: str | None
    top_tokens: list[str]
    recommendations: list[Recommendation]
    created_at: datetime

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    # A persisted pipeline run returned to its owner.

    id: int
    issue_id: int | None
    title: str
    body: str
    gate_passed: bool
    ran_live: bool
    result: dict
    created_at: datetime

    model_config = {"from_attributes": True}
