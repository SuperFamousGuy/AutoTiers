"""In-app feedback endpoint.

POST /api/feedback accepts a free-text message and emails it to a fixed,
config-driven team inbox (settings.feedback_recipient) via the existing
EmailSender. Works for both authenticated and anonymous users — the
submitter's email is attached server-side (never trusted from the client)
purely so the team can reply.

Unlike password-reset (which is deliberately non-enumerating and sends in the
background), feedback is sent synchronously and surfaces transport failures to
the caller as a 502, so the user learns whether their message actually went out.
"""
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Feedback, User
from app.auth.dependencies import get_current_user
from app.auth.rate_limit import feedback_rate_limiter
from app.auth.email_dep import get_email_sender
from app.email.sender import EmailSender
from app.email.templates import feedback_email

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])


async def require_admin(x_api_key: str = Header(default="")) -> None:
    """Gate admin-only feedback routes behind the shared admin API key.

    Identical contract to app.api.data.require_admin: when settings.admin_api_key
    is set, the X-Api-Key header must match; otherwise (key unset, e.g. local
    dev) the gate is open. This is the existing shared admin model — no new
    per-user admin concept is introduced (#286).
    """
    if settings.admin_api_key and x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


class FeedbackCategory(str, Enum):
    """Triage category the submitter tags their feedback with.

    Wire values are lowercase enum strings. `idea` is the default when a client
    omits the field entirely (old clients predating #285 send no category), so
    backward compatibility is preserved: an absent category is a valid `idea`.
    """

    bug = "bug"
    idea = "idea"
    other = "other"


# Human-readable labels for the email subject/body. Single source of truth so
# the route and the template never drift. Keys must cover every enum member.
CATEGORY_LABELS: dict[FeedbackCategory, str] = {
    FeedbackCategory.bug: "Bug",
    FeedbackCategory.idea: "Idea",
    FeedbackCategory.other: "Other",
}


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
    user_id: Optional[uuid.UUID]
    submitter_email: Optional[str]
    category: str
    message: str
    created_at: datetime


def _client_ip(request: Request) -> str:
    """Best-effort client IP for rate-limiting. Falls back to 'unknown'.

    Behind a reverse proxy / load balancer (ECS Fargate sits behind an ALB),
    request.client.host is the proxy's IP, which would collapse every caller
    into one rate-limit bucket. Prefer the left-most entry of X-Forwarded-For
    (the originating client the proxy appends), falling back to the socket peer.
    XFF is client-spoofable, but this is best-effort throttling, not auth.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.post("/feedback", status_code=202)
async def submit_feedback(
    body: FeedbackRequest,
    request: Request,
    current_user: Optional[User] = get_current_user,
    email_sender: EmailSender = Depends(get_email_sender),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Persist a feedback message and email it to the fixed team inbox.

    Returns 202 on success. Returns 422 for empty/oversize input (Pydantic),
    429 when rate-limited, and 502 if the email transport fails.
    """
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Feedback message cannot be empty.")

    # Rate-limit key: prefer the authenticated user id, else client IP.
    rate_key = f"user:{current_user.id}" if current_user is not None else f"ip:{_client_ip(request)}"
    if not feedback_rate_limiter.check_and_record(rate_key):
        raise HTTPException(
            status_code=429,
            detail="You're sending feedback too quickly — please wait a moment and try again.",
        )

    sender_email = current_user.email if current_user is not None else None
    subject_who = sender_email or "anonymous"
    category_label = CATEGORY_LABELS[body.category]
    html, text = feedback_email(message, sender_email, category_label)

    # Persist BEFORE sending (#286): a feedback row is the durable record, so a
    # later email-transport failure does not lose the submission. The email is
    # best-effort notification on top of the stored row.
    record = Feedback(
        user_id=current_user.id if current_user is not None else None,
        submitter_email=sender_email,
        category=body.category.value,
        message=message,
    )
    db.add(record)
    await db.commit()

    try:
        await email_sender.send(
            to=settings.feedback_recipient,
            subject=f"AutoTiers feedback [{category_label}] from {subject_who}",
            html=html,
            text=text,
            # Reply-To is the authenticated submitter so the team can reply
            # directly from their inbox (#288). Omitted for anonymous senders —
            # there is no address to reply to, and we never trust a body-supplied
            # email. SES/Fake both default reply_to=None.
            reply_to=sender_email,
        )
    except Exception:
        logger.exception("Failed to send feedback email to %s", settings.feedback_recipient)
        raise HTTPException(
            status_code=502,
            detail="Couldn't send your feedback right now. Please try again in a moment.",
        )

    return {"detail": "Thanks for the feedback!"}


@router.get("/feedback", response_model=list[FeedbackRecord])
async def list_feedback(
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Feedback]:
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
    return list(result.scalars().all())
