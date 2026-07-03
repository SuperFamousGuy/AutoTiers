"""Tests for the improvement-recommender selection core.

Four specialist agents emit candidate recommendations; this core turns that
raw pile into the small, de-duplicated, best-first list the workflow actually
files as issues. These tests lock the boundaries the untestable shell relies
on: ordering by score, capping to MAX_ISSUES, suppressing anything that
duplicates an already-tracked issue OR an already-kept candidate, and tolerating
malformed / empty / garbage input without raising (a bad LLM generation must
never fail the daily schedule).
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from scripts.improvement_recommend_select import _is_duplicate, main, select


def _cand(title, score=5.0, area="internals", body="do the thing"):
    return {"title": title, "area": area, "body": body, "score": score}


def test_orders_by_score_desc():
    out = select({"max_issues": 5, "existing": [], "candidates": [
        _cand("low", 1.0), _cand("high", 9.0), _cand("mid", 5.0)]})
    assert [c["title"] for c in out] == ["high", "mid", "low"]


def test_caps_at_max_issues():
    cands = [_cand(f"rec {i}", score=i) for i in range(10)]
    out = select({"max_issues": 3, "existing": [], "candidates": cands})
    assert [c["title"] for c in out] == ["rec 9", "rec 8", "rec 7"]


def test_caps_at_ten_the_operating_max():
    # The workflow's operating cap is MAX_ISSUES=10 (env -> --max -> select()).
    # With more than ten distinct candidates, exactly the ten highest survive.
    cands = [_cand(f"rec {i:02d}", score=i) for i in range(15)]
    out = select({"max_issues": 10, "existing": [], "candidates": cands})
    assert len(out) == 10
    assert [c["title"] for c in out] == [f"rec {i:02d}" for i in range(14, 4, -1)]


def test_suppresses_duplicate_of_existing_issue():
    out = select({"max_issues": 5,
                  "existing": [{"title": "Add ADP reconciliation to tier math"}],
                  "candidates": [_cand("Add ADP reconciliation to tier math", 9.0),
                                 _cand("Upgrade tailwind to v4", 5.0)]})
    assert [c["title"] for c in out] == ["Upgrade tailwind to v4"]


def test_suppresses_duplicate_among_candidates():
    out = select({"max_issues": 5, "existing": [], "candidates": [
        _cand("Improve export button contrast", 9.0),
        _cand("improve the export button contrast!", 8.0)]})
    assert len(out) == 1
    assert out[0]["title"] == "Improve export button contrast"


def test_drops_malformed_candidate():
    out = select({"max_issues": 5, "existing": [], "candidates": [
        {"title": "", "body": "x", "score": 9},
        {"title": "no body", "body": "", "score": 8},
        _cand("valid", 1.0)]})
    assert [c["title"] for c in out] == ["valid"]


def test_empty_and_nonlist_input_is_safe():
    assert select({"max_issues": 5, "existing": [], "candidates": []}) == []
    assert select({"max_issues": 5}) == []
    assert select({"max_issues": 5, "candidates": "garbage"}) == []


def test_is_duplicate_unrelated_titles_false():
    assert not _is_duplicate("Upgrade jenkspy clustering", ["Redesign the export modal"])


def test_result_shape_is_title_area_body_only():
    out = select({"max_issues": 5, "existing": [], "candidates": [_cand("x", 1.0)]})
    assert set(out[0].keys()) == {"title", "area", "body"}


def test_main_reads_files_and_writes_json(tmp_path):
    cand = tmp_path / "candidates.json"
    cand.write_text(json.dumps([_cand("A", 9.0), _cand("B", 1.0)]))
    exist = tmp_path / "existing.json"
    exist.write_text(json.dumps([{"title": "A"}]))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--candidates", str(cand), "--existing", str(exist), "--max", "5"])
    assert rc == 0
    assert [c["title"] for c in json.loads(buf.getvalue())] == ["B"]


def test_main_tolerates_garbage_file(tmp_path):
    cand = tmp_path / "candidates.json"
    cand.write_text("not json{{{")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--candidates", str(cand), "--max", "5"])
    assert rc == 0
    assert json.loads(buf.getvalue()) == []


def test_is_duplicate_at_jaccard_boundary():
    cand = "a b c d e f g h"
    assert _is_duplicate(cand, ["a b c d e f g i j"])        # 7/10 == 0.7 -> dup
    assert not _is_duplicate(cand, ["a b c d e f i j"])      # 6/10 == 0.6 -> distinct


def test_null_and_nonnumeric_score_do_not_crash():
    out = select({"max_issues": 5, "existing": [], "candidates": [
        {"title": "stringy score", "area": "x", "body": "b", "score": "high"},
        {"title": "ok", "area": "x", "body": "b", "score": 3}]})
    # Neither crashes; the numeric-scored one sorts above the coerced-to-0 one.
    assert [c["title"] for c in out] == ["ok", "stringy score"]


def test_null_title_or_body_dropped_not_stringified():
    out = select({"max_issues": 5, "existing": [], "candidates": [
        {"title": None, "area": "x", "body": "b", "score": 9},
        {"title": "ok", "area": None, "body": None, "score": 8},
        {"title": "valid", "area": "internals", "body": "do the thing", "score": 1}]})
    titles = [c["title"] for c in out]
    assert "None" not in titles
    assert titles == ["valid"]


def test_zero_max_issues_returns_empty():
    assert select({"max_issues": 0, "existing": [],
                   "candidates": [{"title": "x", "area": "x", "body": "b", "score": 9}]}) == []


def test_garbage_max_issues_defaults_to_five():
    cands = [{"title": f"rec {i}", "area": "x", "body": "b", "score": i} for i in range(8)]
    # A non-numeric max_issues must not crash; it falls back to the default of 5.
    out = select({"max_issues": "five", "existing": [], "candidates": cands})
    assert len(out) == 5
    # None likewise falls back to 5 rather than raising.
    assert len(select({"max_issues": None, "existing": [], "candidates": cands})) == 5
