import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from app.models import User, Profile


@pytest.mark.asyncio
async def test_user_persists_minimal(test_db):
    u = User(email="a@b.com", password_hash="hashstuff")
    test_db.add(u)
    await test_db.commit()
    rows = (await test_db.scalars(select(User))).all()
    assert len(rows) == 1
    assert rows[0].email == "a@b.com"
    assert rows[0].yahoo_subject is None


@pytest.mark.asyncio
async def test_user_email_can_be_null_for_yahoo_only(test_db):
    u = User(yahoo_subject="yahoo-sub-123")
    test_db.add(u)
    await test_db.commit()
    rows = (await test_db.scalars(select(User))).all()
    assert rows[0].email is None
    assert rows[0].yahoo_subject == "yahoo-sub-123"


@pytest.mark.asyncio
async def test_profile_persists_with_jsonb_fields(test_db):
    u = User(email="a@b.com", password_hash="x")
    test_db.add(u)
    await test_db.commit()

    p = Profile(
        user_id=u.id,
        name="My Setup",
        settings_json={"scoring_format": "ppr", "league_size": 12},
        rules_json=[{"name": "RB Committee Penalty", "enabled": True, "weight": 1.0}],
    )
    test_db.add(p)
    await test_db.commit()

    rows = (await test_db.scalars(select(Profile))).all()
    assert rows[0].name == "My Setup"
    assert rows[0].settings_json["league_size"] == 12
    assert rows[0].rules_json[0]["name"] == "RB Committee Penalty"
