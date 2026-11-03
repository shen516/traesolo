"""健康检查 API"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from services.health_service import aggregate_health

router = APIRouter()


@router.get("/health")
async def health():
    payload = aggregate_health()
    code = 200 if payload["status"] == "healthy" else 503
    return JSONResponse(status_code=code, content=payload)


@router.get("/health/live")
async def liveness():
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    payload = aggregate_health()
    code = 200 if payload["status"] in ("healthy", "degraded") else 503
    return JSONResponse(status_code=code, content=payload)
