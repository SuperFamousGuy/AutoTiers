from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import generate, rules, players, data

app = FastAPI(title="AutoTiers API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate.router, prefix="/api")
app.include_router(rules.router, prefix="/api")
app.include_router(players.router, prefix="/api")
app.include_router(data.router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
