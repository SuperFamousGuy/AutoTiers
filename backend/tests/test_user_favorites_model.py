"""Tests for the UserFavorites ORM model."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserFavorites


@pytest.mark.asyncio
async def test_user_favorites_round_trip(test_db: AsyncSession):
    user = User(email="fav@example.com", password_hash="x" * 60)
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    fav = UserFavorites(
        user_id=user.id,
        favorite_player_ids=["4046", "7564"],
        favorite_teams=["KC", "BUF"],
    )
    test_db.add(fav)
    await test_db.commit()

    loaded = (await test_db.scalars(
        select(UserFavorites).where(UserFavorites.user_id == user.id)
    )).one()
    assert loaded.favorite_player_ids == ["4046", "7564"]
    assert loaded.favorite_teams == ["KC", "BUF"]


@pytest.mark.asyncio
async def test_user_favorites_defaults(test_db: AsyncSession):
    """A freshly-created row with no favorites round-trips as empty lists."""
    user = User(email="empty@example.com", password_hash="x" * 60)
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    fav = UserFavorites(user_id=user.id, favorite_player_ids=[], favorite_teams=[])
    test_db.add(fav)
    await test_db.commit()

    loaded = (await test_db.scalars(
        select(UserFavorites).where(UserFavorites.user_id == user.id)
    )).one()
    assert loaded.favorite_player_ids == []
    assert loaded.favorite_teams == []
