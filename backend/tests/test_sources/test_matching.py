import pytest
from sqlalchemy import select
from app.models import Player
from app.data.matching import normalize_name, fuzzy_match


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
