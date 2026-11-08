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
from .utils import run_cleanup_task
from .version import APP_VERSION


logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("app")

# Background task handle
cleanup_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global cleanup_task

    # Startup
    logger.info("Starting %s %s...", settings.app_name, APP_VERSION)

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Start cleanup task
    cleanup_task = asyncio.create_task(run_cleanup_task())
    logger.info("File cleanup task started (interval: %d min)", settings.cleanup_interval_minutes)

    logger.info("Server ready at http://%s:%s", settings.host, settings.port)

    yield

    # Shutdown
    logger.info("Shutting down...")

    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

    logger.info("Goodbye!")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Personal video/audio downloader for YouTube, Instagram, Facebook, and Twitter/X",
    version=APP_VERSION,
    lifespan=lifespan,
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


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint - returns API info"""
    return {
        "name": settings.app_name,
        "version": APP_VERSION,
        "docs": "/docs",
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
