from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from app.api import generate, rules, data
from app.api import auth as auth_api
from app.api import profiles_api
from app.api import favorites_api
from app.api import players_search
from app.api import feedback
from app.api.linked_league import router as linked_league_router
from app.scheduler import setup_scheduler, scheduler
from app.config import settings
from app.email import make_email_sender


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.email_sender = make_email_sender()
    if settings.run_scheduler:
        setup_scheduler()
    yield
    if settings.run_scheduler and scheduler.running:
        scheduler.shutdown()


# orjson serializes large tiered-player lists (hundreds of players x ~20 fields
# plus nested rule-application lists) faster and with lower memory than the
# stdlib-json path FastAPI defaults to. ORJSONResponse keeps the same
# application/json content-type, so a blanket default is a safe drop-in (#581).
app = FastAPI(
    title="AutoTiers API",
    version="0.1.0",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,  # required so the session cookie travels
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate.router, prefix="/api")
app.include_router(rules.router, prefix="/api")
app.include_router(data.router, prefix="/api")
app.include_router(auth_api.router, prefix="/api")
app.include_router(profiles_api.router, prefix="/api")
app.include_router(favorites_api.router, prefix="/api")
app.include_router(players_search.router, prefix="/api")
app.include_router(linked_league_router, prefix="/api")
app.include_router(feedback.router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
