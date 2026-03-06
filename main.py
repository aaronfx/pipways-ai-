"""
Pipways Trading Platform - Main Application
"""
import os
import sys
from pathlib import Path

# Ensure project root is in Python path
project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Import core modules with fallback
try:
    from core import init_db, close_db, get_settings
except ImportError as e:
    print(f"Import error from core: {e}")
    # Direct imports if package import fails
    from core.database import init_db, close_db
    from core.config import get_settings

from routers import auth_router, blog_router, trades_router, media_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting up Pipways Trading Platform...")
    try:
        await init_db()
        logger.info("Database connected successfully")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

    yield

    logger.info("Shutting down...")
    await close_db()
    logger.info("Database disconnected")

# Initialize FastAPI app
app = FastAPI(
    title="Pipways Trading Platform",
    description="AI-powered trading journal and education platform",
    version="2.0.0",
    lifespan=lifespan
)

# Get settings
settings = get_settings()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,
)

# Include routers
app.include_router(auth_router)
app.include_router(blog_router)
app.include_router(trades_router)
app.include_router(media_router)

# Mount static files
if os.path.exists("frontend"):
    app.mount("/static", StaticFiles(directory="frontend"), name="static")

if os.path.exists("uploads"):
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/")
async def root():
    """Root endpoint - serve frontend"""
    if os.path.exists("frontend/index.html"):
        return FileResponse("frontend/index.html")
    return {
        "message": "Pipways Trading Platform API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
        "environment": settings.ENV
    }

@app.get("/api/config")
async def get_config():
    """Get public configuration"""
    return {
        "app_name": "Pipways Trading Platform",
        "version": "2.0.0",
        "features": {
            "ai_enabled": bool(settings.OPENROUTER_API_KEY),
            "zoom_enabled": bool(settings.ZOOM_ACCOUNT_ID),
            "registration_enabled": True
        }
    }

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return {
        "error": True,
        "status_code": exc.status_code,
        "detail": exc.detail
    }

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return {
        "error": True,
        "status_code": 500,
        "detail": "Internal server error" if settings.is_production else str(exc)
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", settings.PORT))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=not settings.is_production,
        workers=1 if settings.is_production else 1
    )
