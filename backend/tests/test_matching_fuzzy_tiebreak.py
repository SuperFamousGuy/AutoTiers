"""Strategy 3 (fuzzy) tie-breaking determinism — issue #842.

Lives at the top level rather than in ``tests/test_sources/`` because the CI
suite ignores that directory (OOM on the data-pipeline tests), and this
regression must actually run in CI and count toward diff coverage.

Two players with the SAME name (so identical ``token_set_ratio``) but different
teams both fuzzy-match a typo'd scraped name at the same score. Before the fix,
the strict ``score > best_score`` handed the win to whichever row the DB
returned first — an arbitrary, unordered outcome. Now the team-matching
candidate wins deterministically regardless of fetch order.
"""
import pytest

from app.models import Player
from app.data.matching import PositionMatchIndex, fuzzy_match


@pytest.mark.asyncio
@pytest.mark.parametrize("insert_team_match_first", [True, False])
@pytest.mark.parametrize("use_index", [False, True])
async def test_fuzzy_tie_resolves_to_team_match(test_db, use_index, insert_team_match_first):
    """Two equally-fuzzy candidates (one team-matching, one not) always resolve
    to the team-matching one — no matter which row is inserted/fetched first."""
    team_match = Player(id="mw_team", name="Mike Williams", position="WR", team="NYJ")
    other = Player(id="mw_other", name="Mike Williams", position="WR", team="PIT")

    if insert_team_match_first:
        test_db.add(team_match)
        test_db.add(other)
    else:
        test_db.add(other)
        test_db.add(team_match)
    await test_db.commit()

    index = PositionMatchIndex() if use_index else None
    # "Mike Willians" is a typo: it exactly matches neither candidate (so we
    # fall through to strategy 3) yet scores identically against both.
    match = await fuzzy_match(test_db, "Mike Willians", "NYJ", "WR", index=index)
    assert match is not None and match.id == "mw_team"


@pytest.mark.asyncio
async def test_fuzzy_tie_stable_across_repeated_runs(test_db):
    """The same triple resolves to the same Player on every call — the property
    the arbitrary-order bug violated."""
    test_db.add(Player(id="mw_team", name="Mike Williams", position="WR", team="NYJ"))
    test_db.add(Player(id="mw_other", name="Mike Williams", position="WR", team="PIT"))
    await test_db.commit()

    results = {
        (await fuzzy_match(test_db, "Mike Willians", "NYJ", "WR")).id
        for _ in range(5)
    }
    assert results == {"mw_team"}


@pytest.mark.asyncio
async def test_fuzzy_tie_no_team_match_is_deterministic(test_db):
    """When neither tied candidate matches the requested team, the outcome is
    still deterministic (falls to the id tiebreak) rather than fetch-order
    dependent."""
    test_db.add(Player(id="mw_aaa", name="Mike Williams", position="WR", team="PIT"))
    test_db.add(Player(id="mw_zzz", name="Mike Williams", position="WR", team="LAC"))
    await test_db.commit()

    first = (await fuzzy_match(test_db, "Mike Willians", "MIN", "WR")).id
    again = (await fuzzy_match(test_db, "Mike Willians", "MIN", "WR")).id
    assert first == again == "mw_zzz"  # highest id wins the deterministic tiebreak
