import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient, ASGITransport
from app.auth.rate_limit import login_rate_limiter, reset_rate_limiter, verify_rate_limiter, feedback_rate_limiter
from app.config import settings
from app.database import Base, get_db
from app.email.fake_sender import FakeSender
from app.main import app


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Hermetic per-test reset of all in-process rate limiters.

    Without this, tests that submit failed requests accumulate attempts
    across the test run and a future test can spuriously hit 429.
    """
    login_rate_limiter._attempts.clear()
    reset_rate_limiter._attempts.clear()
    verify_rate_limiter._attempts.clear()
    feedback_rate_limiter._attempts.clear()
    yield
    login_rate_limiter._attempts.clear()
    reset_rate_limiter._attempts.clear()
    verify_rate_limiter._attempts.clear()
    feedback_rate_limiter._attempts.clear()

# Tests run over plain HTTP (http://test). The auth cookie defaults to
# secure=True when settings.debug=False, which would cause httpx to drop
# the cookie on non-HTTPS — making any test that hits an authenticated
# endpoint after signup/login spuriously fail with 401. Force debug=True
# so set_auth_cookie issues insecure cookies for the test environment.
settings.debug = True

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(test_engine):
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def fake_sender() -> FakeSender:
    """A FakeSender wired into app.state for the duration of the test."""
    sender = FakeSender()
    app.state.email_sender = sender
    yield sender
    # Clean up so state doesn't leak between test files.
    if hasattr(app.state, "email_sender"):
        del app.state.email_sender


@pytest_asyncio.fixture
async def async_client(test_engine, fake_sender):
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
