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
