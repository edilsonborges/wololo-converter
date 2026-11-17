"""Main FastAPI application for Wololo Converter"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import settings
from .database import init_db
from .routes import router, limiter
from .admin import router as admin_router
from .monitoring import run_monitor
from .utils import run_cleanup_task
from .version import APP_VERSION


logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("app")

# Background task handles
cleanup_task = None
monitor_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global cleanup_task, monitor_task

    # Startup
    logger.info("Starting %s %s...", settings.app_name, APP_VERSION)

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Start cleanup task
    cleanup_task = asyncio.create_task(run_cleanup_task())
    logger.info("File cleanup task started (interval: %d min)", settings.cleanup_interval_minutes)

    # Status page probes and machine usage samples
    monitor_task = asyncio.create_task(run_monitor())

    logger.info("Server ready at http://%s:%s", settings.host, settings.port)

    yield

    # Shutdown
    logger.info("Shutting down...")

    for task in (cleanup_task, monitor_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    logger.info("Goodbye!")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description=(
        "Video and audio downloader for YouTube, Instagram, TikTok, Twitter/X, Threads "
        "and Facebook. Quickest start: `GET /api/download?url=<percent-encoded URL>` "
        "returns the MP4 (720p by default) or a `202` with a job to follow. "
        "Agent guide: `/llms.txt`."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
    # Under /api so the public proxy (which only forwards /api) serves them
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url=None,
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.debug else "An unexpected error occurred",
        },
    )


# Include API routes
app.include_router(router, prefix="/api")
app.include_router(admin_router, prefix="/api")


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint - returns API info"""
    return {
        "name": settings.app_name,
        "version": APP_VERSION,
        "docs": "/api/docs",
        "openapi": "/api/openapi.json",
        "health": "/api/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
