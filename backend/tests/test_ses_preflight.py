"""Tests for the SES sandbox/production preflight guard (issue #273).

The single load-bearing fix for #273 — requesting SES production access — is a
manual AWS support action no test can perform. What these tests lock down is
the *guard* that stops an operator re-entering the trap: turning on real sends
(`enable_ses = true`) while the account is still in the sandbox, which silently
drops verification/reset mail to real users.

The three options the issue lays out are each pinned here:
  1. production access granted  -> production_ready, safe.
  2. sandboxed + recipient individually verified -> deliverable for that one
     recipient, but the config is still unsafe for real users.
  3. enable_ses = false -> fake sender, safe holding state.
And the dangerous fourth state — sandboxed + enabled — is asserted unsafe.
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import pytest

from scripts.ses_preflight import (
    REVIEW_DENIED,
    REVIEW_GRANTED,
    REVIEW_NONE,
    REVIEW_PENDING,
    STATUS_FAKE_SENDER,
    STATUS_PRODUCTION_READY,
    STATUS_SANDBOXED_BLOCKED,
    STATUS_SANDBOXED_RECIPIENT_VERIFIED,
    SesReadinessVerdict,
    evaluate_ses_readiness,
    main,
)


# --- The pure decision -------------------------------------------------------

def test_enable_ses_false_is_safe_holding_state():
    """Option 3: fake sender. Safe regardless of sandbox status."""
    v = evaluate_ses_readiness(
        enable_ses=False, production_access_enabled=False
    )
    assert isinstance(v, SesReadinessVerdict)
    assert v.status == STATUS_FAKE_SENDER
    assert v.safe is True
    assert v.sandbox is True
    assert v.recipient_deliverable is None
    assert any("enable_ses = true" in r for r in v.remediation)


def test_enable_ses_false_safe_even_with_production_access():
    v = evaluate_ses_readiness(
        enable_ses=False, production_access_enabled=True
    )
    assert v.status == STATUS_FAKE_SENDER
    assert v.safe is True
    assert v.sandbox is False


def test_production_access_enabled_is_ready():
    """Option 1: the load-bearing fix landed — real sends reach anyone."""
    v = evaluate_ses_readiness(
        enable_ses=True,
        production_access_enabled=True,
        max_24h_send=50000,
        max_send_rate=14,
    )
    assert v.status == STATUS_PRODUCTION_READY
    assert v.safe is True
    assert v.sandbox is False
    assert v.remediation == []
    assert v.max_24h_send == 50000


def test_production_ready_marks_any_recipient_deliverable():
    v = evaluate_ses_readiness(
        enable_ses=True,
        production_access_enabled=True,
        recipient="anyone@example.com",
    )
    assert v.recipient_deliverable is True


def test_sandboxed_and_enabled_is_unsafe():
    """The bug state: enable_ses true while still in the sandbox."""
    v = evaluate_ses_readiness(
        enable_ses=True,
        production_access_enabled=False,
        max_24h_send=200,
        max_send_rate=1.0,
    )
    assert v.status == STATUS_SANDBOXED_BLOCKED
    assert v.safe is False
    assert v.sandbox is True
    assert "DANGER" in v.detail
    # Both the load-bearing fix and the safe fallback are offered.
    assert any("production access" in r.lower() for r in v.remediation)
    assert any("enable_ses = false" in r for r in v.remediation)


def test_sandboxed_unverified_recipient_is_rejected():
    v = evaluate_ses_readiness(
        enable_ses=True,
        production_access_enabled=False,
        verified_identities=["someone@else.com"],
        recipient="user@example.com",
    )
    assert v.status == STATUS_SANDBOXED_BLOCKED
    assert v.safe is False
    assert v.recipient_deliverable is False
    assert "NOT verified" in v.detail


def test_sandboxed_verified_recipient_is_deliverable_but_still_unsafe():
    """Option 2: the interim per-recipient unblock."""
    v = evaluate_ses_readiness(
        enable_ses=True,
        production_access_enabled=False,
        verified_identities=["smoke@test.com"],
        recipient="smoke@test.com",
    )
    assert v.status == STATUS_SANDBOXED_RECIPIENT_VERIFIED
    assert v.recipient_deliverable is True
    # That ONE recipient works, but the config is still unsafe for real users.
    assert v.safe is False
    assert "smoke-testing" in v.detail


def test_recipient_match_is_case_and_whitespace_insensitive():
    v = evaluate_ses_readiness(
        enable_ses=True,
        production_access_enabled=False,
        verified_identities=["  Smoke@Test.com "],
        recipient="smoke@test.com",
    )
    assert v.status == STATUS_SANDBOXED_RECIPIENT_VERIFIED
    assert v.recipient_deliverable is True
    # Identities are normalised in the verdict.
    assert v.verified_identities == ["smoke@test.com"]


def test_empty_verified_identities_matches_triage_evidence():
    """The issue's triage saw list-identities return [] — no verified addrs."""
    v = evaluate_ses_readiness(
        enable_ses=True,
        production_access_enabled=False,
        verified_identities=[],
        recipient="user@example.com",
    )
    assert v.status == STATUS_SANDBOXED_BLOCKED
    assert v.verified_identities == []


def test_duplicate_identities_are_deduped():
    v = evaluate_ses_readiness(
        enable_ses=True,
        production_access_enabled=False,
        verified_identities=["a@x.com", "A@X.com", "a@x.com"],
    )
    assert v.verified_identities == ["a@x.com"]


# --- Production-access review state (issue #273, 2026-06-22: case DENIED) ----

def test_default_verdicts_carry_no_review_state():
    """When no review info is supplied the field is the neutral REVIEW_NONE."""
    v = evaluate_ses_readiness(enable_ses=True, production_access_enabled=False)
    assert v.review_status == REVIEW_NONE
    assert v.review_case_id is None
    # And the original generic 'request production access' lead is used.
    # Check the stable intent case-insensitively rather than an exact-case
    # substring, so wording/casing tweaks to the lead don't break the test.
    assert any("request ses production access" in r.lower() for r in v.remediation)


def test_denied_review_leads_with_console_reply_action():
    """The current real state: request DENIED — API resubmit is blocked, reply
    in the console. The lead remediation must say exactly that, with the case."""
    v = evaluate_ses_readiness(
        enable_ses=True,
        production_access_enabled=False,
        review_status=REVIEW_DENIED,
        review_case_id="178154208400595",
    )
    assert v.status == STATUS_SANDBOXED_BLOCKED
    assert v.safe is False
    assert v.review_status == REVIEW_DENIED
    assert v.review_case_id == "178154208400595"
    lead = v.remediation[0]
    assert "DENIED" in lead
    assert "178154208400595" in lead
    assert "ConflictException" in lead  # names the API-resubmit trap
    assert "console" in lead.lower()
    assert "DENIED" in v.detail


def test_pending_review_says_wait_do_not_resubmit():
    v = evaluate_ses_readiness(
        enable_ses=True,
        production_access_enabled=False,
        review_status="PENDING",  # raw AWS casing is accepted
        review_case_id="999",
    )
    assert v.review_status == REVIEW_PENDING
    lead = v.remediation[0]
    assert "PENDING" in lead
    assert "999" in lead
    assert "PENDING" in v.detail


def test_review_state_threaded_into_recipient_verified_branch():
    v = evaluate_ses_readiness(
        enable_ses=True,
        production_access_enabled=False,
        verified_identities=["smoke@test.com"],
        recipient="smoke@test.com",
        review_status=REVIEW_DENIED,
        review_case_id="abc",
    )
    assert v.status == STATUS_SANDBOXED_RECIPIENT_VERIFIED
    assert v.review_status == REVIEW_DENIED
    assert v.remediation[0].startswith("LOAD-BEARING FIX: your SES")


def test_review_state_ignored_when_production_ready():
    """Out of the sandbox, the review state is moot but still echoed."""
    v = evaluate_ses_readiness(
        enable_ses=True,
        production_access_enabled=True,
        review_status=REVIEW_GRANTED,
    )
    assert v.status == STATUS_PRODUCTION_READY
    assert v.review_status == REVIEW_GRANTED
    assert v.remediation == []


def test_normalize_review_status_mapping():
    from scripts.ses_preflight import _normalize_review_status

    assert _normalize_review_status("PENDING") == REVIEW_PENDING
    assert _normalize_review_status("granted") == REVIEW_GRANTED
    assert _normalize_review_status("Denied") == REVIEW_DENIED
    # FAILED folds into DENIED — both mean "needs operator action".
    assert _normalize_review_status("FAILED") == REVIEW_DENIED
    # Missing / unknown values fail soft to NONE (this field never flips safety).
    assert _normalize_review_status(None) == REVIEW_NONE
    assert _normalize_review_status("") == REVIEW_NONE
    assert _normalize_review_status("WEIRD") == REVIEW_NONE


def test_account_parses_review_details_nested():
    from scripts.ses_preflight import _account_from_get_account

    acct = _account_from_get_account(
        {
            "ProductionAccessEnabled": False,
            "Details": {"ReviewDetails": {"Status": "DENIED", "CaseId": "123"}},
        }
    )
    assert acct["review_status"] == REVIEW_DENIED
    assert acct["review_case_id"] == "123"


def test_account_parses_review_details_flattened():
    from scripts.ses_preflight import _account_from_get_account

    acct = _account_from_get_account(
        {"ProductionAccessEnabled": False, "ReviewDetails": {"Status": "PENDING"}}
    )
    assert acct["review_status"] == REVIEW_PENDING
    assert acct["review_case_id"] is None


def test_account_absent_review_details_is_none():
    from scripts.ses_preflight import _account_from_get_account

    acct = _account_from_get_account({"ProductionAccessEnabled": False})
    assert acct["review_status"] == REVIEW_NONE
    assert acct["review_case_id"] is None


# --- CLI ---------------------------------------------------------------------

def test_main_safe_config_exits_zero():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--enable-ses", "--production-access"])
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["status"] == STATUS_PRODUCTION_READY
    assert payload["safe"] is True


def test_main_unsafe_config_exits_one():
    """Sandboxed + enabled must fail the gate (non-zero exit)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--enable-ses"])  # no --production-access => sandboxed
    assert rc == 1
    payload = json.loads(buf.getvalue())
    assert payload["status"] == STATUS_SANDBOXED_BLOCKED
    assert payload["safe"] is False


def test_main_fake_sender_exits_zero():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main([])  # enable_ses defaults off
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["status"] == STATUS_FAKE_SENDER


def test_main_ingests_get_account_json(tmp_path):
    """Feed the raw `aws sesv2 get-account` sandbox shape from the issue."""
    acct = tmp_path / "acct.json"
    acct.write_text(
        json.dumps(
            {
                "ProductionAccessEnabled": False,
                "SendQuota": {"Max24HourSend": 200, "MaxSendRate": 1.0},
            }
        )
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--enable-ses", "--get-account-json", str(acct)])
    assert rc == 1
    payload = json.loads(buf.getvalue())
    assert payload["production_access_enabled"] is False
    assert payload["max_24h_send"] == 200
    assert payload["max_send_rate"] == 1.0
    assert payload["status"] == STATUS_SANDBOXED_BLOCKED


def test_main_get_account_production_true_is_ready(tmp_path):
    acct = tmp_path / "acct.json"
    acct.write_text(json.dumps({"ProductionAccessEnabled": True}))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--enable-ses", "--get-account-json", str(acct)])
    assert rc == 0
    assert json.loads(buf.getvalue())["status"] == STATUS_PRODUCTION_READY


def test_main_ingests_list_identities_json(tmp_path):
    acct = tmp_path / "acct.json"
    acct.write_text(json.dumps({"ProductionAccessEnabled": False}))
    ids = tmp_path / "ids.json"
    ids.write_text(json.dumps({"Identities": ["smoke@test.com"]}))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(
            [
                "--enable-ses",
                "--get-account-json",
                str(acct),
                "--verified-identities-json",
                str(ids),
                "--recipient",
                "smoke@test.com",
            ]
        )
    assert rc == 1  # one verified recipient, but config still unsafe overall
    payload = json.loads(buf.getvalue())
    assert payload["status"] == STATUS_SANDBOXED_RECIPIENT_VERIFIED
    assert payload["recipient_deliverable"] is True


def test_main_ingests_review_details_from_get_account(tmp_path):
    """The full triage shape from #273's 2026-06-22 status: sandboxed + DENIED."""
    acct = tmp_path / "acct.json"
    acct.write_text(
        json.dumps(
            {
                "ProductionAccessEnabled": False,
                "SendQuota": {"Max24HourSend": 200, "MaxSendRate": 1.0},
                "Details": {
                    "ReviewDetails": {
                        "Status": "DENIED",
                        "CaseId": "178154208400595",
                    }
                },
            }
        )
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--enable-ses", "--get-account-json", str(acct)])
    assert rc == 1
    payload = json.loads(buf.getvalue())
    assert payload["status"] == STATUS_SANDBOXED_BLOCKED
    assert payload["review_status"] == REVIEW_DENIED
    assert payload["review_case_id"] == "178154208400595"
    assert "178154208400595" in payload["remediation"][0]


def test_main_review_status_flag_overrides_json(tmp_path):
    acct = tmp_path / "acct.json"
    acct.write_text(
        json.dumps(
            {
                "ProductionAccessEnabled": False,
                "Details": {"ReviewDetails": {"Status": "DENIED", "CaseId": "x"}},
            }
        )
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(
            [
                "--enable-ses",
                "--get-account-json",
                str(acct),
                "--review-status",
                "PENDING",
                "--review-case-id",
                "override-case",
            ]
        )
    assert rc == 1
    payload = json.loads(buf.getvalue())
    assert payload["review_status"] == REVIEW_PENDING
    assert payload["review_case_id"] == "override-case"


def test_main_explicit_flag_combines_with_json_identities(tmp_path):
    ids = tmp_path / "ids.json"
    ids.write_text(json.dumps({"Identities": ["json@test.com"]}))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(
            [
                "--enable-ses",
                "--verified-identity",
                "flag@test.com",
                "--verified-identities-json",
                str(ids),
                "--recipient",
                "flag@test.com",
            ]
        )
    assert rc == 1
    payload = json.loads(buf.getvalue())
    assert payload["status"] == STATUS_SANDBOXED_RECIPIENT_VERIFIED
    assert "flag@test.com" in payload["verified_identities"]
    assert "json@test.com" in payload["verified_identities"]


def test_list_identities_bad_shape_raises(tmp_path):
    from scripts.ses_preflight import _identities_from_list_identities

    with pytest.raises(ValueError):
        _identities_from_list_identities({"Identities": "not-a-list"})


def test_get_account_flattened_shape_is_tolerated():
    from scripts.ses_preflight import _account_from_get_account

    acct = _account_from_get_account(
        {"ProductionAccessEnabled": True, "Max24HourSend": 50000, "MaxSendRate": 14}
    )
    assert acct["production_access_enabled"] is True
    assert acct["max_24h_send"] == 50000
    assert acct["max_send_rate"] == 14


def test_production_access_string_false_is_not_production():
    """A literal "false" string must fail closed, not coerce to True."""
    from scripts.ses_preflight import _account_from_get_account

    acct = _account_from_get_account({"ProductionAccessEnabled": "false"})
    assert acct["production_access_enabled"] is False


def test_production_access_string_true_is_honoured():
    from scripts.ses_preflight import _account_from_get_account

    acct = _account_from_get_account({"ProductionAccessEnabled": "true"})
    assert acct["production_access_enabled"] is True


def test_production_access_missing_defaults_to_sandboxed():
    from scripts.ses_preflight import _account_from_get_account

    acct = _account_from_get_account({})
    assert acct["production_access_enabled"] is False


def test_production_access_non_boolean_raises():
    """Garbage in the safety-gate field is loud, not silently coerced."""
    from scripts.ses_preflight import _account_from_get_account

    with pytest.raises(ValueError):
        _account_from_get_account({"ProductionAccessEnabled": "yes"})
