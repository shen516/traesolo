"""
足球量化分析模型 API 服务
FastAPI 提供预测接口，供前端Vue项目调用
"""
from pathlib import Path
import logging
import os

# Windows + OpenBLAS：大规模蒙特卡洛（≥50k）多线程易触发 memory allocation 崩溃。
# 仅在未显式配置时设默认值，不影响生产已调参场景。
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from services.app_log_service import setup_app_logging

setup_app_logging()
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from services.ensemble_registry import load_weights_from_db
import time
from db.database import engine
from db import models

models.Base.metadata.create_all(bind=engine)
from db.database import ensure_schema
ensure_schema()

from init_db import init_database
init_database()

from api import router as api_router
from services.scheduler_service import scheduler
from services.crawler_service import crawler_service


def run_initial_crawls():
    """后台线程执行初始采集任务"""
    import threading
    def run():
        try:
            logger.info("Running initial match crawl...")
            crawler_service.crawl_all_leagues()
            logger.info("Initial match crawl completed")
        except Exception as e:
            logger.error(f"Initial match crawl failed: {e}")

        try:
            logger.info("Running initial league crawl...")
            crawler_service.crawl_leagues(crawl_type='initial')
            logger.info("Initial league crawl completed")
        except Exception as e:
            logger.error(f"Initial league crawl failed: {e}")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()


def _recover_stale_training():
    """启动时把锁已释放、或超过僵死阈值仍为 running 的训练记录标为失败。"""
    try:
        from services.training_service import training_service
        n = training_service.fail_abandoned_running_records(force=True)
        if n:
            logger.warning("Marked %s stale training record(s) as failed", n)
    except Exception as e:
        logger.warning("stale training recovery failed: %s", e)


def _load_ensemble_weights():
    load_weights_from_db()


def _startup():
    _recover_stale_training()
    run_scheduler = os.environ.get("RUN_SCHEDULER", "1").lower() not in ("0", "false", "no")
    if not run_scheduler:
        logger.info("RUN_SCHEDULER=0 — skipping scheduler and initial crawls (API-only worker)")
        _load_ensemble_weights()
        return

    logger.info("Starting scheduler service...")
    # 仅真实采集；模拟爬虫已移除
    if crawler_service._real_crawler:
        crawler_service._default_crawler = crawler_service._real_crawler
    logger.info("Real crawler ready")

    from services.scheduled_tasks import register_all as register_scheduled_tasks

    # 1. 注册所有任务的元信息（不启动，仅记录到内存注册表）
    #    后续 enable/disable 通过 API 触发或从 DB 恢复
    register_scheduled_tasks(scheduler, crawler_service)

    # 2. 清理已下线的任务（如 player_crawl；不在注册表内的 DB 记录一并删除）
    scheduler.cleanup_orphan_tasks()

    # 4. 从数据库恢复任务状态：DB 中 is_enabled=True 的任务自动启动，False 的保持停止
    scheduler.restore_from_db()

    # 5. 启动调度器线程
    scheduler.start()
    logger.info("Scheduler started; task states restored from database")

    # 5b. 从当前模型版本恢复全局/分联赛融合权重
    _load_ensemble_weights()

    # 6. 可选：启动时一次性初始采集（默认关闭，避免重启打爆源站/脏数据）
    #    设置 TRAESOLO_INITIAL_CRAWL=1 开启
    if os.environ.get("TRAESOLO_INITIAL_CRAWL", "").lower() in ("1", "true", "yes"):
        run_initial_crawls()
    else:
        logger.info("TRAESOLO_INITIAL_CRAWL not set — skip startup crawl (use scheduled tasks)")


def _shutdown():
    try:
        from services.training_service import training_service
        training_service.abort_for_shutdown()
    except Exception as e:
        logger.warning("abort training on shutdown failed: %s", e)
    logger.info("Stopping scheduler service...")
    scheduler.stop()
    logger.info("Scheduler stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup()
    yield
    _shutdown()


_docs_enabled = os.environ.get("TRAESOLO_DISABLE_DOCS", "").lower() not in ("1", "true", "yes")
app = FastAPI(
    title="足球量化分析API",
    version="5.0.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api/v1")

static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 需登录的写操作与管理路径前缀（GET 列表类仍要求登录，仅放行 auth）
_AUTH_WHITELIST_PREFIXES = (
    "/static",
)
if _docs_enabled:
    _AUTH_WHITELIST_PREFIXES = (
        "/docs",
        "/openapi.json",
        "/redoc",
        "/static",
    )
_AUTH_WHITELIST_EXACT = {
    "/",
    "/metrics",
    "/api/v1/health",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/api/v1/auth/captcha",
    "/api/v1/auth/login",
}


@app.middleware("http")
async def require_auth_middleware(request, call_next):
    path = request.url.path
    method = request.method.upper()
    if method == "OPTIONS":
        return await call_next(request)
    if path in _AUTH_WHITELIST_EXACT or any(path.startswith(p) for p in _AUTH_WHITELIST_PREFIXES):
        return await call_next(request)
    if not path.startswith("/api/"):
        return await call_next(request)

    from fastapi.responses import JSONResponse
    from api.deps import token_store

    auth = request.headers.get("Authorization") or ""
    if not auth.lower().startswith("bearer "):
        return JSONResponse(status_code=401, content={"detail": "未登录或 Token 缺失"})
    token = auth.split(" ", 1)[1].strip()
    data = token_store.get(token)
    if not data:
        return JSONResponse(status_code=401, content={"detail": "登录已失效，请重新登录"})
    if time.time() > data["expires"]:
        token_store.revoke(token)
        return JSONResponse(status_code=401, content={"detail": "登录已过期，请重新登录"})
    return await call_next(request)


@app.middleware("http")
async def prometheus_metrics_middleware(request, call_next):
    from services.metrics_service import record_request
    from services.app_log_service import log_http_access
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    try:
        record_request(request.method, request.url.path, response.status_code, elapsed)
        log_http_access(
            request.method,
            request.url.path,
            response.status_code,
            elapsed * 1000,
        )
    except Exception:
        logger.warning("prometheus/access log failed", exc_info=True)
    return response


# CORS 必须在鉴权之后注册，才能成为最外层
_cors_raw = os.environ.get("TRAESOLO_CORS_ORIGINS", "").strip()
_cors_origins = (
    [o.strip() for o in _cors_raw.split(",") if o.strip()]
    if _cors_raw
    else [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://localhost",
        "http://localhost:80",
        "http://127.0.0.1",
        "http://127.0.0.1:80",
    ]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== 统一异常处理：不向客户端回传堆栈/内部异常文本，避免信息泄露 =====

@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    """兜底 500：仅记录服务端堆栈，响应体只给固定文案。"""
    logger.exception("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": "服务内部错误"})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """参数校验失败：保留 {loc,msg} 结构，与前端 http.js 的 422 解析保持一致。"""
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": [str(p) for p in e.get("loc", [])], "msg": str(e.get("msg", ""))}
                for e in exc.errors()
            ]
        },
    )


@app.get("/")
async def root():
    return {"status": "ok", "service": "football-quant-analysis", "version": "5.0.0"}


@app.get("/metrics")
async def prometheus_metrics():
    from fastapi.responses import Response
    from services.metrics_service import metrics_content_type, metrics_payload
    return Response(metrics_payload(), media_type=metrics_content_type())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
