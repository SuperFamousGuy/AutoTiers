"""Issue #858: the dynasty ADP tiebreak was inert.

``backend/app/models/adp.py`` documents ``format`` as
"standard | half_ppr | ppr | dynasty" and ``generate.py`` selects
``tiebreak_adp_attr = "adp_dynasty"`` for dynasty leagues, but no fetcher ever
writes a ``format="dynasty"`` row. So ``_get_adp(entries, "dynasty")`` always
returned ``None``, ``adp_dynasty`` was always null, and the tiers.py sort key
collapsed to a constant 9999 for every dynasty player — equal-VBD ties resolved
on arbitrary insertion order.

Part 1 locks the root cause (no dynasty rows exist, so ``adp_dynasty`` is None).
Part 2 proves the short-term fallback: dynasty ties break on ``adp_ppr`` order.
"""
from app.api.generate import _get_adp
from app.engine.tiers import TieredPlayer, assign_tiers
from app.models.adp import ADPData


def _adp_row(fmt: str, adp: float) -> ADPData:
    return ADPData(player_id="p1", format=fmt, adp=adp, adp_source="fantasypros")


# --- Part 1: root cause — no source writes format="dynasty" rows -------------

def test_get_adp_dynasty_is_none_even_when_redraft_formats_present():
    """The only ADP writer (FantasyProsFetcher) emits standard/half_ppr/ppr.
    A dynasty lookup finds no matching row and returns None."""
    entries = [
        _adp_row("standard", 12.0),
        _adp_row("half_ppr", 10.0),
        _adp_row("ppr", 8.0),
    ]
    assert _get_adp(entries, "ppr", "redraft") == 8.0
    # No format="dynasty" row exists → dynasty lookup is inert.
    assert _get_adp(entries, "ppr", "dynasty") is None
    assert _get_adp(entries, "standard", "dynasty") is None


# --- Part 2: fallback — dynasty ties break on adp_ppr, not insertion order ---

def _tied_player(pid: str, adp_ppr: float) -> TieredPlayer:
    # Identical adjusted_score (→ identical VBD) so ranking depends purely on
    # the ADP tiebreak. adp_dynasty is None, mirroring production data.
    return TieredPlayer(
        player_id=pid, name=f"Player {pid}", position="RB",
        team="NE", age=25, adjusted_score=100.0,
        projected_score_raw=100.0, prior_year_actual=100.0,
        adp_standard=None, adp_ppr=adp_ppr, adp_dynasty=None,
        flags=[], rules_applied=[],
        overall_rank=0, overall_tier=0, positional_tier="",
    )


def test_dynasty_ties_break_on_adp_ppr_not_insertion_order():
    # Inserted in reverse ADP order: without the fallback, ranks would follow
    # insertion order (b before a). With it, a (adp_ppr=1) must outrank b (=2).
    b = _tied_player("b", adp_ppr=2.0)
    a = _tied_player("a", adp_ppr=1.0)
    ranked = assign_tiers([b, a], league_size=12, tiebreak_adp_attr="adp_dynasty")
    order = [p.player_id for p in ranked]
    assert order == ["a", "b"], f"dynasty tie should follow adp_ppr, got {order}"


def test_dynasty_fallback_missing_ppr_sorts_last_without_crashing():
    # A player with no adp_ppr either falls back to the 9999 sentinel and sorts
    # behind a player that does have one — no crash on the None fallback.
    has_ppr = _tied_player("has_ppr", adp_ppr=5.0)
    no_ppr = _tied_player("no_ppr", adp_ppr=None)
    ranked = assign_tiers([no_ppr, has_ppr], league_size=12, tiebreak_adp_attr="adp_dynasty")
    order = [p.player_id for p in ranked]
    assert order == ["has_ppr", "no_ppr"], f"got {order}"


def test_populated_adp_dynasty_takes_priority_over_ppr_fallback():
    """Forward-compat: when a real dynasty source ships and adp_dynasty is
    populated, it wins over the adp_ppr fallback (acceptance criterion 3)."""
    # p_dyn has a strong dynasty ADP (1.0) but a weak ppr ADP (9.0); p_ppr has
    # only the fallback (ppr=2.0). Dynasty value must rank p_dyn first.
    p_dyn = _tied_player("p_dyn", adp_ppr=9.0)
    p_dyn.adp_dynasty = 1.0
    p_ppr = _tied_player("p_ppr", adp_ppr=2.0)
    ranked = assign_tiers([p_ppr, p_dyn], league_size=12, tiebreak_adp_attr="adp_dynasty")
    order = [p.player_id for p in ranked]
    assert order == ["p_dyn", "p_ppr"], f"populated adp_dynasty should win, got {order}"
