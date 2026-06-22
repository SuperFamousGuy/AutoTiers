"""SES sandbox/production preflight for the transactional-email switch.

Issue #273: production could not deliver verification/password-reset email to
real users because the SES account in us-east-1 was still in the **sandbox**
(`ProductionAccessEnabled: false`). In the sandbox, `SendEmail` is rejected
(`MessageRejected`) for any recipient that has not been individually verified.
The user-visible symptom is the worst kind: the UI reports "we re-sent it"
(the HTTP request succeeds), the background SES send is rejected, and no email
ever arrives.

The single load-bearing fix is manual and cannot be expressed in code or
Terraform: an AWS account holder must **request SES production access** for the
region (Console -> SES -> Account dashboard -> Request production access). See
``docs/runbooks/ses-email-provisioning.md``.

What CAN be expressed in code is the *guard* that stops an operator walking
back into the trap: turning on real sends (``enable_ses = true``) while the
account is still sandboxed. This module holds that pure, testable decision.
Given the SES account status (what ``aws sesv2 get-account`` returns), the set
of verified recipient identities (``aws ses list-identities``), and the
intended ``enable_ses`` value, it decides whether the configuration will
silently drop mail to real users.

It encodes the three options the issue lays out:

  1. **Production access granted** -> real sends to anyone succeed. (The fix.)
  2. **Still sandboxed, recipient individually verified** -> that one recipient
     receives mail; everyone else is still silently rejected. (The interim,
     per-recipient unblock.)
  3. **`enable_ses = false`** -> the app falls back to the in-process fake
     sender. No mail reaches users, but nothing is *silently* dropped either.
     A safe holding state until the sandbox is exited.

The dangerous state -- ``enable_ses = true`` while still sandboxed -- is the
one this guard flags as unsafe.

Run standalone with explicit values (used in tests / CI):

    python3 backend/scripts/ses_preflight.py \\
        --enable-ses \\
        --production-access \\
        --max-24h-send 50000 --max-send-rate 14

or feed it the raw AWS CLI output directly (how an operator runs it):

    aws sesv2 get-account --region us-east-1 > acct.json
    aws ses list-identities --identity-type EmailAddress > ids.json
    python3 backend/scripts/ses_preflight.py --enable-ses \\
        --get-account-json acct.json \\
        --verified-identities-json ids.json

Exit code is 0 when the configuration is safe (will not silently drop mail to
real users) and 1 when it is unsafe, so the script doubles as a deploy gate.
A malformed input exits non-zero (argparse's 2) so bad data is loud rather
than silently "safe".
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence


@dataclass(frozen=True)
class SesReadinessVerdict:
    """Structured result of an SES send-readiness evaluation."""

    status: str  # see STATUS_* constants below
    safe: bool  # False => config can silently drop mail to real users
    enable_ses: bool
    production_access_enabled: bool
    sandbox: bool
    recipient: Optional[str]
    recipient_deliverable: Optional[bool]
    verified_identities: List[str]
    max_24h_send: Optional[float]
    max_send_rate: Optional[float]
    detail: str
    # Production-access review case state (from `get-account` Details.ReviewDetails):
    # one of the REVIEW_* constants. Surfaces WHY the account is still sandboxed
    # — never requested vs. pending vs. denied — so the remediation can name the
    # exact next action (see issue #273's 2026-06-22 status: case DENIED).
    review_status: str = "none"
    review_case_id: Optional[str] = None
    remediation: List[str] = field(default_factory=list)


# Status constants — one per branch of the decision so callers can switch on a
# stable string instead of re-deriving it from the booleans.
STATUS_FAKE_SENDER = "fake_sender"  # enable_ses = false; on the fake sender.
STATUS_PRODUCTION_READY = "production_ready"  # out of sandbox, real sends OK.
STATUS_SANDBOXED_RECIPIENT_VERIFIED = "sandboxed_recipient_verified"
STATUS_SANDBOXED_BLOCKED = "sandboxed_blocked"  # the bug state.


# Production-access review states. AWS `get-account` reports the review case as
# Details.ReviewDetails.Status, one of PENDING | GRANTED | DENIED | FAILED. We
# canonicalise to these four so the guard can tell an operator the precise next
# move: a fresh request, waiting on a pending one, or replying to a denied case.
REVIEW_NONE = "none"  # no review case on record — production access never requested.
REVIEW_PENDING = "pending"  # a request is in flight; don't resubmit.
REVIEW_GRANTED = "granted"  # review passed (ProductionAccessEnabled should be true).
REVIEW_DENIED = "denied"  # request DENIED/FAILED — reply in console to reopen.


def _normalize_review_status(value: object) -> str:
    """Canonicalise an SES ReviewDetails.Status into a REVIEW_* constant.

    AWS uses PENDING | GRANTED | DENIED | FAILED. We fold FAILED into DENIED
    (both mean "the request did not succeed and needs operator action") and map
    a missing/empty/unknown value to REVIEW_NONE — fail-soft, since this field
    only enriches the remediation text and never flips the safety verdict on
    its own (ProductionAccessEnabled does that).
    """
    if value is None:
        return REVIEW_NONE
    text = str(value).strip().upper()
    if text == "PENDING":
        return REVIEW_PENDING
    if text == "GRANTED":
        return REVIEW_GRANTED
    if text in ("DENIED", "FAILED"):
        return REVIEW_DENIED
    return REVIEW_NONE


def _normalize_identities(identities: Optional[Sequence[str]]) -> List[str]:
    """Lower-case, strip, and de-dupe verified identities for matching.

    SES identity matching is case-insensitive on the recipient address, and
    the AWS CLI occasionally returns surrounding whitespace; normalising here
    keeps the membership test from missing a real verification on a cosmetic
    difference.
    """
    if not identities:
        return []
    seen: dict[str, None] = {}
    for raw in identities:
        text = str(raw).strip().lower()
        if text:
            seen.setdefault(text, None)
    return list(seen.keys())


def evaluate_ses_readiness(
    *,
    enable_ses: bool,
    production_access_enabled: bool,
    verified_identities: Optional[Sequence[str]] = None,
    recipient: Optional[str] = None,
    max_24h_send: Optional[float] = None,
    max_send_rate: Optional[float] = None,
    review_status: str = REVIEW_NONE,
    review_case_id: Optional[str] = None,
) -> SesReadinessVerdict:
    """Decide whether the SES configuration will reliably reach real users.

    Args:
        enable_ses: The intended value of the Terraform ``enable_ses`` flag.
            When false the backend runs on the in-process fake sender and never
            calls SES at all.
        production_access_enabled: ``ProductionAccessEnabled`` from
            ``aws sesv2 get-account``. False means the account is still in the
            SES sandbox and can only deliver to individually verified
            recipients.
        verified_identities: Email identities verified in the account (from
            ``aws ses list-identities --identity-type EmailAddress``). Only
            meaningful while sandboxed.
        recipient: Optional specific recipient to evaluate — e.g. the address
            an operator is about to smoke-test. When the account is sandboxed,
            the verdict reports whether *this* recipient would receive mail.
        max_24h_send / max_send_rate: ``Max24HourSend`` / ``MaxSendRate`` from
            ``get-account``, echoed into the verdict for visibility (sandbox
            quotas are 200 / 1.0).
        review_status: Canonical production-access review state (a REVIEW_*
            constant) from ``get-account`` Details.ReviewDetails.Status. Used
            only to sharpen the remediation while sandboxed — it does not change
            the safety verdict.
        review_case_id: The AWS support case id for that review, if any, so the
            remediation can point the operator straight at the case to reply to.

    Returns:
        A SesReadinessVerdict. ``safe`` is True when the configuration will not
        silently drop mail to real users.
    """
    normalized = _normalize_identities(verified_identities)
    sandbox = not production_access_enabled
    review = _normalize_review_status(review_status)
    case = str(review_case_id).strip() if review_case_id else None
    recipient_norm = recipient.strip().lower() if recipient else None
    recipient_deliverable: Optional[bool] = None

    # Branch 3: real sends are off entirely. Safe holding state — the app uses
    # the fake sender, so nothing is *silently* dropped (no SES call is made).
    if not enable_ses:
        return SesReadinessVerdict(
            status=STATUS_FAKE_SENDER,
            safe=True,
            enable_ses=False,
            production_access_enabled=production_access_enabled,
            sandbox=sandbox,
            recipient=recipient,
            recipient_deliverable=None,
            verified_identities=normalized,
            max_24h_send=max_24h_send,
            max_send_rate=max_send_rate,
            review_status=review,
            review_case_id=case,
            detail=(
                "enable_ses is false: the backend runs on the in-process fake "
                "sender and never calls SES. No mail reaches real users, but "
                "nothing is silently rejected either. This is the safe holding "
                "state until SES production access is granted."
            ),
            remediation=[
                "To send real mail, first confirm production access is granted "
                "(re-run this preflight with --production-access), then set "
                "enable_ses = true.",
            ],
        )

    # enable_ses is true from here down — SES will actually be called.

    # Branch 1: out of the sandbox. Real sends to any recipient succeed.
    if production_access_enabled:
        if recipient_norm is not None:
            recipient_deliverable = True
        return SesReadinessVerdict(
            status=STATUS_PRODUCTION_READY,
            safe=True,
            enable_ses=True,
            production_access_enabled=True,
            sandbox=False,
            recipient=recipient,
            recipient_deliverable=recipient_deliverable,
            verified_identities=normalized,
            max_24h_send=max_24h_send,
            max_send_rate=max_send_rate,
            review_status=review,
            review_case_id=case,
            detail=(
                "Production access is enabled and enable_ses is true: SES "
                "delivers to any recipient. Verification and password-reset "
                "email reach real users."
            ),
            remediation=[],
        )

    # Sandboxed AND enable_ses is true — the trap. Every send to an unverified
    # recipient is rejected (MessageRejected) while the UI reports success.
    #
    # The load-bearing fix is always "get production access", but the precise
    # next action depends on where the review case stands (issue #273's
    # 2026-06-22 status: the request was DENIED, case 178154208400595, and the
    # API refuses a resubmit while that case is open — ConflictException). Lead
    # with the action that actually matches the current review state.
    case_suffix = f" (case {case})" if case else ""
    if review == REVIEW_DENIED:
        lead = (
            "LOAD-BEARING FIX: your SES production-access request was DENIED"
            f"{case_suffix}. Re-requesting via the API (`aws sesv2 "
            "put-account-details`) fails with ConflictException while the "
            "denied case is open — reply to the case in the AWS Console "
            "(SES -> Account dashboard, or Support Center) with strengthened "
            "justification to get it reconsidered. "
            "See docs/runbooks/ses-email-provisioning.md."
        )
    elif review == REVIEW_PENDING:
        lead = (
            "A SES production-access request is already PENDING"
            f"{case_suffix} — wait for the decision; do NOT resubmit (the API "
            "rejects a duplicate with ConflictException). "
            "See docs/runbooks/ses-email-provisioning.md."
        )
    else:
        lead = (
            "LOAD-BEARING FIX: request SES production access for the region "
            "(Console -> SES -> Account dashboard -> Request production access). "
            "Terraform cannot do this. See docs/runbooks/ses-email-provisioning.md."
        )
    remediation = [
        lead,
        "OR set enable_ses = false to fall back to the fake sender until "
        "production access is granted (no silent rejections).",
        "INTERIM per-recipient unblock while sandboxed: "
        "aws ses verify-email-identity --email-address <addr>.",
    ]

    if recipient_norm is not None and recipient_norm in normalized:
        # Branch 2: the specific recipient is individually verified, so it
        # receives mail — but the broader config is still unsafe for real
        # users, so safe stays False.
        recipient_deliverable = True
        return SesReadinessVerdict(
            status=STATUS_SANDBOXED_RECIPIENT_VERIFIED,
            safe=False,
            enable_ses=True,
            production_access_enabled=False,
            sandbox=True,
            recipient=recipient,
            recipient_deliverable=True,
            verified_identities=normalized,
            max_24h_send=max_24h_send,
            max_send_rate=max_send_rate,
            review_status=review,
            review_case_id=case,
            detail=(
                f"SES is sandboxed but {recipient!r} is individually verified, "
                "so that recipient receives mail (the interim per-recipient "
                "unblock). Every OTHER recipient is still silently rejected — "
                "this is safe only for smoke-testing, not for real users."
            ),
            remediation=remediation,
        )

    # Branch (the bug): sandboxed, enabled, recipient not verified (or none
    # given). Mail to real users is silently dropped.
    if recipient_norm is not None:
        recipient_deliverable = False
    detail = (
        "DANGER: enable_ses is true but the account is still in the SES "
        "sandbox (ProductionAccessEnabled=false). Every send to an unverified "
        "recipient is rejected with MessageRejected, yet the HTTP request "
        "succeeds — users see 'we re-sent it' and no email arrives."
    )
    if recipient_norm is not None:
        detail += f" Recipient {recipient!r} is NOT verified and would be rejected."
    if review == REVIEW_DENIED:
        detail += (
            f" Production-access review was DENIED{case_suffix}; reply to the "
            "case in the console to reopen it."
        )
    elif review == REVIEW_PENDING:
        detail += (
            f" A production-access review is PENDING{case_suffix}; mail stays "
            "blocked until it is granted."
        )
    return SesReadinessVerdict(
        status=STATUS_SANDBOXED_BLOCKED,
        safe=False,
        enable_ses=True,
        production_access_enabled=False,
        sandbox=True,
        recipient=recipient,
        recipient_deliverable=recipient_deliverable,
        verified_identities=normalized,
        max_24h_send=max_24h_send,
        max_send_rate=max_send_rate,
        review_status=review,
        review_case_id=case,
        detail=detail,
        remediation=remediation,
    )


def _identities_from_list_identities(payload: dict) -> List[str]:
    """Extract addresses from `aws ses list-identities` JSON.

    Shape: ``{"Identities": ["a@x.com", ...]}``. A missing/empty key yields an
    empty list (the triage state in the issue: no verified recipients).
    """
    identities = payload.get("Identities", [])
    if not isinstance(identities, list):
        raise ValueError("list-identities JSON: 'Identities' must be a list")
    return [str(i) for i in identities]


def _coerce_production_access(value: object) -> bool:
    """Strictly interpret ``ProductionAccessEnabled`` as a boolean (fail closed).

    This is a safety gate, so it must not over-trust its input. A plain
    ``bool(value)`` treats any non-empty string — including ``"false"`` — as
    ``True``, which would silently mark a sandboxed account as production-ready
    (exactly the trap #273 guards against). Here only a genuine JSON boolean
    (what a real ``aws sesv2 get-account`` returns) or an explicit
    ``"true"``/``"false"`` string is honoured; a missing key defaults to the
    safe ``False`` (sandboxed), and anything else is rejected loudly rather
    than coerced.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "false"):
            return text == "true"
    raise ValueError(
        "get-account JSON: 'ProductionAccessEnabled' must be a boolean, "
        f"got {value!r}"
    )


def _account_from_get_account(payload: dict) -> dict:
    """Pull the fields we care about out of `aws sesv2 get-account` JSON.

    Tolerates both the documented nested shape
    (``{"SendQuota": {"Max24HourSend": ...}}``) and a flattened one, since the
    CLI shape has shifted across versions.
    """
    production = _coerce_production_access(payload.get("ProductionAccessEnabled", False))
    quota = payload.get("SendQuota") or {}
    max_24h = payload.get("Max24HourSend", quota.get("Max24HourSend"))
    max_rate = payload.get("MaxSendRate", quota.get("MaxSendRate"))
    # ReviewDetails lives under Details in the documented shape; tolerate a
    # flattened top-level ReviewDetails too. Absent => no review on record.
    details = payload.get("Details") or {}
    review_details = details.get("ReviewDetails") or payload.get("ReviewDetails") or {}
    return {
        "production_access_enabled": production,
        "max_24h_send": float(max_24h) if max_24h is not None else None,
        "max_send_rate": float(max_rate) if max_rate is not None else None,
        "review_status": _normalize_review_status(review_details.get("Status")),
        "review_case_id": review_details.get("CaseId"),
    }


def _load_json(path: str) -> dict:
    """Load JSON from a file path, or stdin when path is '-'."""
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="SES sandbox/production preflight (issue #273).",
    )
    parser.add_argument(
        "--enable-ses",
        action="store_true",
        help="The intended Terraform enable_ses value (real sends on).",
    )
    parser.add_argument(
        "--production-access",
        action="store_true",
        help="ProductionAccessEnabled is true (account is OUT of the sandbox).",
    )
    parser.add_argument(
        "--get-account-json",
        help="Path to `aws sesv2 get-account` JSON ('-' for stdin). Overrides "
        "--production-access; supplies --max-* values unless those flags are "
        "passed explicitly (an explicit --max-* still wins).",
    )
    parser.add_argument(
        "--verified-identities-json",
        help="Path to `aws ses list-identities` JSON ('-' for stdin).",
    )
    parser.add_argument(
        "--verified-identity",
        action="append",
        default=[],
        metavar="ADDR",
        help="A verified recipient identity (repeatable).",
    )
    parser.add_argument(
        "--recipient",
        help="Optional specific recipient to evaluate (e.g. a smoke-test addr).",
    )
    parser.add_argument(
        "--review-status",
        default=None,
        metavar="STATUS",
        help="Production-access review state (PENDING|GRANTED|DENIED|FAILED). "
        "Read from --get-account-json Details.ReviewDetails when present; an "
        "explicit flag still wins. Sharpens the remediation while sandboxed.",
    )
    parser.add_argument(
        "--review-case-id",
        default=None,
        metavar="ID",
        help="AWS support case id for the production-access review, so the "
        "remediation can point at the exact case to reply to.",
    )
    parser.add_argument("--max-24h-send", type=float, default=None)
    parser.add_argument("--max-send-rate", type=float, default=None)
    args = parser.parse_args(argv)

    production_access = args.production_access
    max_24h = args.max_24h_send
    max_rate = args.max_send_rate
    review_status = args.review_status
    review_case_id = args.review_case_id
    if args.get_account_json:
        account = _account_from_get_account(_load_json(args.get_account_json))
        production_access = account["production_access_enabled"]
        # Explicit --max-* flags still win if the operator passed them.
        max_24h = max_24h if max_24h is not None else account["max_24h_send"]
        max_rate = max_rate if max_rate is not None else account["max_send_rate"]
        # Explicit --review-* flags still win over what get-account reports.
        review_status = review_status if review_status is not None else account["review_status"]
        review_case_id = (
            review_case_id if review_case_id is not None else account["review_case_id"]
        )

    identities = list(args.verified_identity)
    if args.verified_identities_json:
        identities.extend(
            _identities_from_list_identities(_load_json(args.verified_identities_json))
        )

    verdict = evaluate_ses_readiness(
        enable_ses=args.enable_ses,
        production_access_enabled=production_access,
        verified_identities=identities,
        recipient=args.recipient,
        max_24h_send=max_24h,
        max_send_rate=max_rate,
        review_status=review_status if review_status is not None else REVIEW_NONE,
        review_case_id=review_case_id,
    )
    json.dump(asdict(verdict), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if verdict.safe else 1


if __name__ == "__main__":
    raise SystemExit(main())
