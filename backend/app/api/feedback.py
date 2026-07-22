"""In-app feedback endpoint.

POST /api/feedback accepts a free-text message and persists it. Fully
anonymous (no accounts): there is no submitter identity to attach, and no
email notification is sent (SES/email was removed in the v1 accounts
teardown). The feedback row itself is the durable record; admins read it via
the existing X-Api-Key-gated GET route.
"""
import logging
import uuid
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Feedback
from app.auth.admin import require_admin
from app.auth.rate_limit import feedback_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])


class FeedbackCategory(str, Enum):
    """Triage category the submitter tags their feedback with.

    Wire values are lowercase enum strings. `idea` is the default when a client
    omits the field entirely (old clients predating #285 send no category), so
    backward compatibility is preserved: an absent category is a valid `idea`.
    """

    bug = "bug"
    idea = "idea"
    other = "other"


class FeedbackRequest(BaseModel):
    # min_length=1 rejects the empty string; the route additionally rejects
    # whitespace-only messages after stripping. max_length caps abuse.
    message: str = Field(min_length=1, max_length=4000)
    # Optional with a server-side default so old clients (no category) still
    # work; an unknown string yields a 422 from Pydantic enum validation.
    category: FeedbackCategory = FeedbackCategory.idea


class FeedbackRecord(BaseModel):
    """Admin read-model for a persisted feedback row."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    category: str
    message: str
    created_at: datetime


def _client_ip(request: Request) -> str:
    """Best-effort client IP for rate-limiting. Falls back to 'unknown'.

    Behind a reverse proxy / load balancer (ECS Fargate sits behind an ALB),
    request.client.host is the proxy's IP, which would collapse every caller
    into one rate-limit bucket, so we read X-Forwarded-For instead.

    The ALB appends the real peer IP to the RIGHT of whatever the client sent —
    it does not strip a client-supplied XFF. Taking the left-most entry (the old
    behaviour) let a client forge `X-Forwarded-For: <random>` and mint a fresh
    rate-limit bucket per request (#519). Instead take the entry
    `settings.trusted_proxy_count` hops from the right: with one trusted ALB hop
    that is the right-most entry (the IP the ALB appended), which the client
    cannot control. Chains shorter than the trusted-hop count fall back to the
    left-most entry. Falls back to the socket peer, then to 'unknown'.

    XFF is still not authentication — a misconfigured trusted-proxy count or an
    extra untrusted hop can shift the read — but with the hop count correct a
    client can no longer trivially rotate its own key. This is best-effort
    throttling, not auth.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            # Clamp to >=1: a 0 trusted-hop count means XFF is untrusted, so
            # skip it entirely and use the socket peer below.
            hops = settings.trusted_proxy_count
            if hops >= 1:
                # N-from-the-right, clamped so a chain shorter than the trusted
                # hop count yields the left-most (oldest) entry, not an error.
                idx = max(0, len(parts) - hops)
                return parts[idx]
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.post("/feedback", status_code=202)
async def submit_feedback(
    body: FeedbackRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Persist a feedback message. Anonymous, persist-only — no email is sent.

    Returns 202 on success, 422 for empty/oversize input (Pydantic), and 429
    when rate-limited.
    """
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Feedback message cannot be empty.")

    # Rate-limit key: client IP only — there is no account to key on.
    rate_key = f"ip:{_client_ip(request)}"
    if not feedback_rate_limiter.check_and_record(rate_key):
        raise HTTPException(
            status_code=429,
            detail="You're sending feedback too quickly — please wait a moment and try again.",
        )

    record = Feedback(
        category=body.category.value,
        message=message,
    )
    db.add(record)
    await db.commit()

    return {"detail": "Thanks for the feedback!"}


@router.get("/feedback", response_model=list[FeedbackRecord])
async def list_feedback(
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[FeedbackRecord]:
    """Admin-only: list persisted feedback, newest first.

    Gated by the shared admin API key (X-Api-Key). API-only — there is no UI.
    Paginated with limit/offset; newest-first ordering for triage.
    """
    result = await db.execute(
        select(Feedback)
        .order_by(Feedback.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [FeedbackRecord.model_validate(row) for row in result.scalars().all()]
