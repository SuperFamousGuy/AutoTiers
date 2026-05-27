from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import generate, rules, players, data
from app.api import auth as auth_api
from app.api import profiles_api
from app.scheduler import setup_scheduler, scheduler
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.run_scheduler:
        setup_scheduler()
    yield
    if settings.run_scheduler and scheduler.running:
        scheduler.shutdown()


app = FastAPI(title="AutoTiers API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate.router, prefix="/api")
app.include_router(rules.router, prefix="/api")
app.include_router(players.router, prefix="/api")
app.include_router(data.router, prefix="/api")
app.include_router(auth_api.router, prefix="/api")
app.include_router(profiles_api.router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
