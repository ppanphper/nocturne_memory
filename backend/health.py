from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from db import get_db_client


router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    database_status = "disconnected"

    try:
        client = get_db_client()
        async with client.session() as session:
            await session.execute(text("SELECT 1"))
        database_status = "connected"
    except Exception:
        database_status = "disconnected"

    return {"status": "ok", "database": database_status}


__all__ = ["router", "health_check"]
