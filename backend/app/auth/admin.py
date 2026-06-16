"""Shared admin authorization dependency.

Single source of truth for the admin gate so every admin-only route shares one
implementation (header name, status code, "key unset" behavior). Duplicating it
per-router risks the copies drifting and desyncing admin protection.

The model is the existing shared admin API key — no per-user admin concept:
when settings.admin_api_key is set, the X-Api-Key header must match; otherwise
(key unset, e.g. local dev) the gate is open.
"""
from fastapi import Header, HTTPException

from app.config import settings


async def require_admin(x_api_key: str = Header(default="")) -> None:
    """Gate admin-only routes behind the shared admin API key."""
    if settings.admin_api_key and x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
