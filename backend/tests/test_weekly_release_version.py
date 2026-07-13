"""Tests for the weekly auto-release version core
(`backend/scripts/weekly_release_version.py`, driving
`.github/workflows/weekly-release.yml`).

The weekly job creates a real GitHub release, which triggers deploy.yml and a
prod deploy. So the two things this core gets wrong would ship straight to
users: (a) computing the wrong next version (a lexical sort makes v3.9 look
newer than v3.15), and (b) cutting a release when it must not (an empty week,
or -- worse -- inventing a baseline when there is no base tag at all).

Every assertion below is EXACT (a specific version string / exit code), not a
bound, so it fails if the logic regresses to the old/broken behaviour rather
than passing across a range that includes it.
"""
from __future__ import annotations

import io
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

from scripts.weekly_release_version import (
    decide,
    format_version,
    highest_version,
    main,
    next_version,
    parse_tag,
)

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "weekly_release_version.py"
)


# --- parse_tag -------------------------------------------------------------

def test_parse_tag_two_component():
    assert parse_tag("v3.15") == (3, 15)
    assert parse_tag("v0.1") == (0, 1)
    assert parse_tag(" v3.15 ") == (3, 15)  # surrounding whitespace tolerated


def test_parse_tag_rejects_non_two_component():
    # Exactly two numeric components required; everything else is ignored,
    # never partially parsed.
    for bad in ["v1", "v1.2.3", "v1.2-rc1", "3.15", "vX.Y", "latest",
                "release-1.2", "v3.", "v.3", ""]:
        assert parse_tag(bad) is None, bad


# --- highest_version (the numeric-sort trap) -------------------------------

def test_highest_version_is_numeric_not_lexical():
    # The core regression guard: lexical sort ranks "v3.9" > "v3.15"; numeric
    # sort ranks v3.15 > v3.9. Assert the NUMERIC winner exactly.
    tags = ["v3.9", "v3.10", "v3.15", "v3.2"]
    assert highest_version(tags) == (3, 15)


def test_highest_version_across_majors():
    assert highest_version(["v2.99", "v3.0", "v10.1", "v9.20"]) == (10, 1)


def test_highest_version_ignores_non_matching_tags():
    tags = ["latest", "v1.2.3", "release-2", "v3.15", "not-a-tag"]
    assert highest_version(tags) == (3, 15)


def test_highest_version_none_when_no_release_tag():
    assert highest_version([]) is None
    assert highest_version(["latest", "v1.2.3", "v1"]) is None


# --- next_version / format -------------------------------------------------

def test_next_version_bumps_minor_only():
    assert next_version((3, 15)) == (3, 16)


def test_next_version_minor_rolls_past_nine_without_touching_major():
    # v3.9 -> v3.10, NOT v4.0. Minor is a plain integer, not a digit.
    assert next_version((3, 9)) == (3, 10)


def test_next_version_never_bumps_major():
    # Major bump is human-only; the core must not produce it from any input.
    assert next_version((3, 99)) == (3, 100)


def test_format_version():
    assert format_version((3, 16)) == "v3.16"


# --- decide (the full policy) ----------------------------------------------

def test_decide_cuts_next_minor_on_the_real_repo_state():
    # Mirrors the actual repo at authoring time: latest v3.15, commits present.
    code, msg = decide(["v3.14", "v3.15", "v3.9"], commit_count=7)
    assert code == 0
    assert msg == "next=v3.16"


def test_decide_skips_empty_week():
    code, msg = decide(["v3.15"], commit_count=0)
    assert code == 0
    assert msg.startswith("skip=empty")
    assert "v3.15" in msg  # names the tag it compared against


def test_decide_negative_commit_count_also_skips():
    code, msg = decide(["v3.15"], commit_count=-1)
    assert code == 0
    assert msg.startswith("skip=empty")


def test_decide_fails_loudly_with_no_base_tag():
    code, msg = decide(["latest", "v1.2.3"], commit_count=42)
    assert code == 3
    assert msg.startswith("error:")
    assert "invent" in msg  # explicitly refuses to invent a baseline
    # Must NOT emit a COMPUTED next version -- a loud failure, not a silent
    # baseline guess. (The message may cite `v1.0` inside the how-to-fix hint;
    # what matters is that no `next=`/`skip=` machine-readable line is emitted,
    # so the workflow's shell cuts nothing.)
    assert "next=" not in msg
    assert "skip=" not in msg


def test_decide_empty_week_takes_precedence_is_not_reached_without_base():
    # No base tag AND no commits -> the missing-base failure wins (exit 3),
    # because we cannot even name what to skip.
    code, msg = decide([], commit_count=0)
    assert code == 3
    assert msg.startswith("error:")


# --- main() CLI + exit-code contract (what the workflow actually calls) -----

def _run_main(tags: list[str], commit_count, tmp_path):
    tags_file = tmp_path / "tags.txt"
    tags_file.write_text("\n".join(tags) + "\n")
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(["--tags-file", str(tags_file),
                     "--commit-count", str(commit_count)])
    return code, buf.getvalue().strip()


def test_main_prints_next_and_exits_zero(tmp_path):
    code, out = _run_main(["v3.15", "v3.9"], 5, tmp_path)
    assert code == 0
    assert out == "next=v3.16"


def test_main_skips_empty_week_exit_zero(tmp_path):
    code, out = _run_main(["v3.15"], 0, tmp_path)
    assert code == 0
    assert out.startswith("skip=empty")


def test_main_no_base_tag_exits_three(tmp_path):
    code, out = _run_main(["latest"], 9, tmp_path)
    assert code == 3
    assert out.startswith("error:")


def test_main_end_to_end_via_subprocess(tmp_path):
    # Exercise the exact `python3 <script> --tags-file ... --commit-count ...`
    # invocation the workflow runs, asserting the process exit code the shell
    # branches on.
    tags_file = tmp_path / "tags.txt"
    tags_file.write_text("v3.15\nv3.9\nlatest\n")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--tags-file", str(tags_file), "--commit-count", "3"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "next=v3.16"

    proc_skip = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--tags-file", str(tags_file), "--commit-count", "0"],
        capture_output=True, text=True,
    )
    assert proc_skip.returncode == 0
    assert proc_skip.stdout.strip().startswith("skip=empty")
