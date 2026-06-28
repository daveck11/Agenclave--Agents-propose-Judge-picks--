# Issue persistence routes (auth required). Each issue belongs to one user; the
# ownership guard is enforced on every read/delete (404 when not owned).

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_session
from ..models import Issue, User
from ..schemas import IssueCreate, IssueOut

router = APIRouter(prefix="/issues", tags=["issues"])


async def _owned_issue(issue_id: int, user: User, session: AsyncSession) -> Issue:
    # Fetch an issue or 404 if it doesn't exist / isn't the caller's.
    issue = await session.get(Issue, issue_id)
    if issue is None or issue.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="issue not found")
    return issue


@router.post("", response_model=IssueOut, status_code=status.HTTP_201_CREATED)
async def create_issue(
    req: IssueCreate,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Issue:
    # Persist a triaged issue (snapshots the Stage 1 prediction).
    issue = Issue(
        user_id=current.id,
        title=req.title,
        body=req.body,
        label=req.label,
        confidence=req.confidence,
        severity=req.severity,
        top_tokens=req.top_tokens,
        recommendations=[r.model_dump() for r in req.recommendations],
    )
    session.add(issue)
    await session.commit()
    await session.refresh(issue)
    return issue


@router.get("", response_model=list[IssueOut])
async def list_issues(
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Issue]:
    # List the caller's issues, newest first.
    result = await session.execute(
        select(Issue).where(Issue.user_id == current.id).order_by(Issue.id.desc())
    )
    return list(result.scalars().all())


@router.get("/{issue_id}", response_model=IssueOut)
async def get_issue(
    issue_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Issue:
    # Fetch one of the caller's issues (404 if not owned).
    return await _owned_issue(issue_id, current, session)


@router.delete("/{issue_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_issue(
    issue_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    # Delete one of the caller's issues (404 if not owned).
    issue = await _owned_issue(issue_id, current, session)
    await session.delete(issue)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
