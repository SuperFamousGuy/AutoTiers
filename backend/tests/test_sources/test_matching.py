import pytest
from sqlalchemy import event, select
from app.models import Player
from app.data.matching import PositionMatchIndex, normalize_name, fuzzy_match


def _count_position_queries(engine):
    """Return (list, remover) that records every 'SELECT ... FROM players WHERE
    players.position = ?' statement executed on the given async engine."""
    seen: list[str] = []

    def _listener(conn, cursor, statement, parameters, context, executemany):
        normalized = " ".join(statement.split()).lower()
        if "from players" in normalized and "players.position" in normalized:
            seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _listener)

    def _remove():
        event.remove(engine.sync_engine, "before_cursor_execute", _listener)

    return seen, _remove


@pytest.mark.parametrize("raw,expected", [
    ("Patrick Mahomes II", "patrick mahomes"),
    ("Marvin Harrison Jr.", "marvin harrison"),
    ("Odell Beckham Jr", "odell beckham"),
    ("D.J. Moore", "dj moore"),
    ("Ja'Marr Chase", "jamarr chase"),
    ("  CeeDee  Lamb  ", "ceedee lamb"),
    ("Amon-Ra St. Brown", "amonra st brown"),
])
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


@pytest.mark.asyncio
async def test_fuzzy_match_exact(test_db):
    test_db.add(Player(id="sleep_1", name="Justin Jefferson", position="WR", team="MIN"))
    await test_db.commit()
    match = await fuzzy_match(test_db, "Justin Jefferson", "MIN", "WR")
    assert match is not None
    assert match.id == "sleep_1"


@pytest.mark.asyncio
async def test_fuzzy_match_ignores_jr_suffix(test_db):
    test_db.add(Player(id="sleep_1", name="Marvin Harrison Jr.", position="WR", team="ARI"))
    await test_db.commit()
    match = await fuzzy_match(test_db, "Marvin Harrison", "ARI", "WR")
    assert match is not None and match.id == "sleep_1"


@pytest.mark.asyncio
async def test_fuzzy_match_handles_traded_player(test_db):
    """Player traded mid-cycle — name and position match, team differs."""
    test_db.add(Player(id="sleep_1", name="Davante Adams", position="WR", team="NYJ"))
    await test_db.commit()
    match = await fuzzy_match(test_db, "Davante Adams", "LV", "WR")
    assert match is not None and match.id == "sleep_1"


@pytest.mark.asyncio
async def test_fuzzy_match_returns_none_below_threshold(test_db):
    test_db.add(Player(id="sleep_1", name="Justin Jefferson", position="WR", team="MIN"))
    await test_db.commit()
    match = await fuzzy_match(test_db, "Totally Unrelated Player", "MIN", "WR")
    assert match is None


@pytest.mark.asyncio
async def test_fuzzy_match_respects_position(test_db):
    test_db.add(Player(id="sleep_qb", name="Josh Allen", position="QB", team="BUF"))
    test_db.add(Player(id="sleep_lb", name="Josh Allen", position="LB", team="JAX"))
    await test_db.commit()
    match = await fuzzy_match(test_db, "Josh Allen", "BUF", "QB")
    assert match.id == "sleep_qb"


@pytest.mark.asyncio
async def test_position_match_index_queries_position_once(test_engine, test_db):
    """A shared PositionMatchIndex issues exactly one position query no matter
    how many fuzzy_match calls hit that bucket."""
    for i in range(3):
        test_db.add(Player(id=f"wr_{i}", name=f"Wide Receiver {i}", position="WR", team="MIN"))
    await test_db.commit()

    index = PositionMatchIndex()
    seen, remove = _count_position_queries(test_engine)
    try:
        for i in range(3):
            match = await fuzzy_match(test_db, f"Wide Receiver {i}", "MIN", "WR", index=index)
            assert match is not None and match.id == f"wr_{i}"
    finally:
        remove()

    assert len(seen) == 1, f"expected one WR position query, got {len(seen)}"


@pytest.mark.asyncio
async def test_fuzzy_match_with_index_matches_without_index(test_db):
    """The index path must produce identical results to the standalone path."""
    test_db.add(Player(id="wr_1", name="Marvin Harrison Jr.", position="WR", team="ARI"))
    test_db.add(Player(id="wr_2", name="Davante Adams", position="WR", team="NYJ"))
    await test_db.commit()

    index = PositionMatchIndex()
    # exact-name-ignoring-suffix, traded-player (team differs), and below-threshold
    assert (await fuzzy_match(test_db, "Marvin Harrison", "ARI", "WR", index=index)).id == "wr_1"
    assert (await fuzzy_match(test_db, "Davante Adams", "LV", "WR", index=index)).id == "wr_2"
    assert await fuzzy_match(test_db, "Totally Unrelated Player", "ARI", "WR", index=index) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("use_index", [False, True])
async def test_fuzzy_match_falls_back_to_token_ratio(test_db, use_index):
    """Strategy 3: a near-miss name (typo) with no exact normalized match still
    resolves via token_set_ratio when it scores >= threshold. Exercised on both
    the standalone and the cached-index code paths."""
    test_db.add(Player(id="wr_1", name="Justin Jefferson", position="WR", team="MIN"))
    await test_db.commit()
    index = PositionMatchIndex() if use_index else None
    match = await fuzzy_match(test_db, "Justin Jeferson", "MIN", "WR", index=index)
    assert match is not None and match.id == "wr_1"


@pytest.mark.asyncio
async def test_position_match_index_caches_empty_bucket(test_engine, test_db):
    """A position with no players is cached too — no re-query on repeat lookups."""
    index = PositionMatchIndex()
    seen, remove = _count_position_queries(test_engine)
    try:
        assert await fuzzy_match(test_db, "Nobody", "FA", "QB", index=index) is None
        assert await fuzzy_match(test_db, "Nobody Else", "FA", "QB", index=index) is None
    finally:
        remove()
    assert len(seen) == 1, f"expected one QB query for the empty bucket, got {len(seen)}"
