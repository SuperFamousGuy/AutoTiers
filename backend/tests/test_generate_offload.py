"""Issue #577: the CPU-bound tiering computation must run OFF the event loop.

``generate_tiers`` is an ``async def`` route, but the heavy per-player scoring +
rules + VBD + Jenks clustering used to run inline on the single event loop,
starving every other coroutine (other ``/generate`` calls, ``/api/data/health``,
the in-process scheduler) for the duration.

The fix wraps that pure-Python work in ``asyncio.to_thread`` after copying the
ORM rows into session-free snapshots. These tests prove:

1. The event loop stays responsive while the CPU work runs (the whole point).
2. The offloaded computation is a *pure* function of plain snapshots — it never
   touches the ORM session (so a worker thread can't trigger lazy I/O).
3. Output is unchanged for identical input (behaviour is preserved; only where
   it runs changed). The existing golden e2e suites
   (``test_per_position_rules_generate_e2e``, ``test_generate_espn_weight``,
   ``test_generate_vbd_cap``) are the primary guard for this; here we add a
   direct determinism check on the sync core.
"""
import asyncio
import contextlib
import time

import pytest

import app.api.generate as gen
from app.api.generate import (
    _AdpSnapshot,
    _PlayerSnapshot,
    _ProjSnapshot,
    _StatSnapshot,
    _build_league_settings,
    _compute_ranked_players,
)
from app.models.player import Player, PlayerStat
from app.models.projection import Projection
from app.schemas.generate import GenerateRequest


def _base_body(**overrides) -> dict:
    body = {
        "scoring_format": "ppr",
        "league_type": "standard",
        "league_size": 12,
        "qb_td_points": 4,
        "weight_prior_year": 0.5,
        "weight_espn": 0.0,
        "weight_consensus": 0.5,
        "draft_rounds": 15,
    }
    body.update(overrides)
    return body


async def _seed_pool(test_db, n_per_position: int = 8) -> None:
    """Seed a realistic multi-position pool with stats + projections."""
    positions = ["QB", "RB", "WR", "TE", "K", "DST"]
    for pos in positions:
        for i in range(n_per_position):
            pid = f"{pos.lower()}_{i}"
            test_db.add(Player(id=pid, name=f"{pos} Player {i}", position=pos,
                               team="NE", age=25 + (i % 6), years_exp=i % 8))
            test_db.add(PlayerStat(
                player_id=pid, season=2025,
                targets=90 - i, receptions=60 - i, rec_yards=800.0 - 10 * i, rec_tds=6,
                rush_att=40, rush_yards=180.0, rush_tds=2,
                pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
                snaps=900, snap_pct=0.75, carry_share=0.4, target_share=0.2,
                games_played=16, red_zone_looks=10,
            ))
            test_db.add(Projection(
                player_id=pid, source="fantasypros",
                scoring_format="ppr", projected_points=250.0 - i * 3,
            ))
    await test_db.commit()


@pytest.mark.asyncio
async def test_generate_keeps_event_loop_responsive_during_cpu_work(
    async_client, test_db, monkeypatch
):
    """While the CPU-bound tiering runs, the event loop must keep making
    progress. We simulate heavy CPU by sleeping inside the offloaded function;
    if it runs on a worker thread (the fix) a concurrent heartbeat coroutine
    ticks freely, if it runs inline on the loop (the bug) the heartbeat stalls.
    """
    await _seed_pool(test_db)

    original = gen._compute_ranked_players
    hold = 0.4  # seconds of simulated CPU work

    def slow_compute(*args, **kwargs):
        time.sleep(hold)  # blocking — only harmless if run off the event loop
        return original(*args, **kwargs)

    monkeypatch.setattr(gen, "_compute_ranked_players", slow_compute)

    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    hb = asyncio.create_task(heartbeat())
    try:
        r = await async_client.post("/api/generate", json=_base_body())
    finally:
        hb.cancel()
        # Await the cancellation so no pending task leaks past the test (avoids
        # "Task was destroyed but it is pending" warnings under strict asyncio).
        with contextlib.suppress(asyncio.CancelledError):
            await hb

    assert r.status_code == 200, r.text
    # ~0.4s / 0.02s ≈ 20 ideal ticks. If the loop were blocked inline, ticks
    # would be ~0. Assert a conservative floor to stay robust to CI jitter.
    assert ticks >= 5, (
        f"event loop was starved during CPU work (only {ticks} heartbeat ticks) "
        "— the tiering computation is not being offloaded via asyncio.to_thread"
    )


@pytest.mark.asyncio
async def test_two_overlapping_generate_calls_both_succeed(
    async_client, test_db, monkeypatch
):
    """Two overlapping /generate requests both complete, agree with a
    sequential run, AND run concurrently rather than serialized.

    We block the CPU core for a fixed interval. If the work is offloaded via
    ``asyncio.to_thread`` (the fix) the two requests overlap on separate worker
    threads and the pair finishes in ~1×hold. If the CPU work ran inline on the
    event loop (the pre-fix bug) the second request would be gated behind the
    first and the pair would take ~2×hold — so the wall-clock assertion below
    fails, which the plain "both succeed" check could not catch (serialized
    requests still both succeed)."""
    await _seed_pool(test_db)

    original = gen._compute_ranked_players
    hold = 0.3  # seconds of simulated CPU work per request

    def slow_compute(*args, **kwargs):
        time.sleep(hold)  # blocking — only overlaps if run off the event loop
        return original(*args, **kwargs)

    monkeypatch.setattr(gen, "_compute_ranked_players", slow_compute)

    seq = await async_client.post("/api/generate", json=_base_body())
    assert seq.status_code == 200, seq.text
    expected_total = seq.json()["total"]

    t0 = time.perf_counter()
    a, b = await asyncio.gather(
        async_client.post("/api/generate", json=_base_body()),
        async_client.post("/api/generate", json=_base_body()),
    )
    elapsed = time.perf_counter() - t0

    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["total"] == expected_total
    assert b.json()["total"] == expected_total
    # Identical input → identical ranking (pure performance change).
    assert [p["player_id"] for p in a.json()["players"]] == \
           [p["player_id"] for p in b.json()["players"]]
    # The two CPU phases overlapped on worker threads: total wall-clock is far
    # closer to one hold than two. A generous 1.5× ceiling stays robust to CI
    # jitter while still failing the serialized (~2×hold) inline-on-loop case.
    assert elapsed < hold * 1.5, (
        f"overlapping requests took {elapsed:.2f}s for a {hold}s CPU hold — "
        "they appear serialized, i.e. the tiering is running inline on the "
        "event loop instead of via asyncio.to_thread"
    )


def _snapshot_pool(n_per_position: int = 6) -> list[_PlayerSnapshot]:
    positions = ["QB", "RB", "WR", "TE", "K", "DST"]
    pool: list[_PlayerSnapshot] = []
    for pos in positions:
        for i in range(n_per_position):
            stat = _StatSnapshot(
                season=2025, games_played=16, targets=90 - i, receptions=60 - i,
                rec_yards=800.0 - 10 * i, rec_tds=6, rush_att=40, rush_yards=180.0,
                rush_tds=2, pass_att=0, pass_yards=0.0, pass_tds=0, interceptions=0,
                snap_pct=0.75, carry_share=0.4, target_share=0.2,
                actual_tds=8, expected_tds=6.0, red_zone_looks=10,
                fumbles_lost=1, two_pt_conversions=0,
                first_down_rush=8, first_down_rec=25,
            )
            pool.append(_PlayerSnapshot(
                id=f"{pos.lower()}_{i}", name=f"{pos} Player {i}", position=pos,
                team="NE", age=25, years_exp=3, draft_round=None, draft_pick=None,
                stats=(stat,),
                projections=(_ProjSnapshot("fantasypros", "ppr", 250.0 - i * 3),),
                adp_entries=(_AdpSnapshot("ppr", float(i + 1)),),
            ))
    return pool


def test_compute_ranked_players_is_pure_and_deterministic():
    """The offloaded core is a pure function of plain snapshots (no DB, no
    ORM). Same input twice → identical ranking, ranks, tiers, and scores."""
    pool = _snapshot_pool()
    req = GenerateRequest(**_base_body())
    settings = _build_league_settings(req)

    def run():
        return _compute_ranked_players(
            list(pool),
            settings=settings,
            req=req,
            scoring_fmt="ppr",
            keepers_normalized=set(),
            bad_offense_teams=set(),
            above_market_pids=set(),
            current_year=2026,
        )

    r1 = run()
    r2 = run()
    assert r1, "expected a non-empty ranking"
    assert [(p.player_id, p.overall_rank, p.overall_tier, p.vbd_score) for p in r1] == \
           [(p.player_id, p.overall_rank, p.overall_tier, p.vbd_score) for p in r2]
    # Ranks are dense and 1-based.
    assert [p.overall_rank for p in r1] == list(range(1, len(r1) + 1))


def test_compute_ranked_players_honors_keepers():
    """A keeper name is dropped from the returned pool — proves the sync core
    receives and applies the request-derived plain data correctly."""
    pool = _snapshot_pool()
    req = GenerateRequest(**_base_body())
    settings = _build_league_settings(req)
    from app.data.matching import normalize_name

    keeper = pool[0]
    ranked = _compute_ranked_players(
        list(pool),
        settings=settings,
        req=req,
        scoring_fmt="ppr",
        keepers_normalized={normalize_name(keeper.name)},
        bad_offense_teams=set(),
        above_market_pids=set(),
        current_year=2026,
    )
    assert keeper.id not in {p.player_id for p in ranked}
