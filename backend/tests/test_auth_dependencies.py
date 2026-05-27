import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.database import get_db
from app.models import User
from app.auth.dependencies import get_current_user, require_user
from app.auth.jwt import encode_jwt, JWT_COOKIE_NAME


def _make_app(test_engine) -> FastAPI:
    app = FastAPI()
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    @app.get("/optional")
    async def optional_route(user: User | None = get_current_user):
        return {"user_id": str(user.id) if user else None}

    @app.get("/required")
    async def required_route(user: User = require_user):
        return {"user_id": str(user.id)}

    return app


@pytest.mark.asyncio
async def test_optional_returns_none_without_cookie(test_engine):
    app = _make_app(test_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/optional")
    assert r.json() == {"user_id": None}


@pytest.mark.asyncio
async def test_required_returns_401_without_cookie(test_engine):
    app = _make_app(test_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/required")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_required_returns_user_with_valid_cookie(test_engine, test_db):
    user = User(email="me@x.com", password_hash="x")
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    app = _make_app(test_engine)
    token = encode_jwt(user.id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.cookies.set(JWT_COOKIE_NAME, token)
        r = await c.get("/required")
    assert r.status_code == 200
    assert r.json() == {"user_id": str(user.id)}
