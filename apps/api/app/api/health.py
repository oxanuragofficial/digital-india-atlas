"""Health-check endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from app import __version__
from app.api.deps import get_engine_dep
from app.db.health import check_database

router = APIRouter(tags=["health"])

SERVICE_NAME = "digital-india-atlas-api"


@router.get("/health")
def liveness() -> dict[str, str]:
    """Process liveness. Does not touch the database."""
    return {"status": "ok", "service": SERVICE_NAME, "version": __version__}


@router.get("/health/db")
def database_health(engine: Annotated[Engine | None, Depends(get_engine_dep)]) -> JSONResponse:
    """Readiness of the database (and PostGIS when running on PostgreSQL)."""
    if engine is None:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "not_configured"},
        )
    result = check_database(engine)
    if not result.ok:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": result.reason},
        )
    return JSONResponse(
        content={"status": "ok", "database": "up", "postgis": result.postgis_version}
    )
