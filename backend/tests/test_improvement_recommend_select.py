"""Tests for the improvement-recommender selection core.

Three specialist agents emit candidate recommendations; this core turns that
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
