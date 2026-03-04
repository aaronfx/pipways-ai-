"""
Pipways - Institutional Forex Trader Development Platform
Main Application Entry Point
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from config import settings
from database import engine, Base
from models import create_default_admin
import auth
import lms_routes
import admin_routes
import ai_engine
import payment
import telegram_bot
import blog_routes
import analytics_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    Base.metadata.create_all(bind=engine)
    create_default_admin()
    print("✅ Database initialized")
    yield
    # Shutdown
    print("👋 Application shutting down")


app = FastAPI(
    title="Pipways API",
    description="Institutional Forex Trader Development Platform",
    version="2.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(lms_routes.router, prefix="/api/lms", tags=["LMS"])
app.include_router(admin_routes.router, prefix="/api/admin", tags=["Admin"])
app.include_router(ai_engine.router, prefix="/api/ai", tags=["AI Analysis"])
app.include_router(payment.router, prefix="/api/payment", tags=["Payments"])
app.include_router(telegram_bot.router, prefix="/api/telegram", tags=["Telegram"])
app.include_router(blog_routes.router, prefix="/api/blog", tags=["Blog"])
app.include_router(analytics_routes.router, prefix="/api/analytics", tags=["Analytics"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "services": {
            "database": "connected",
            "ai_engine": "ready",
            "payments": "ready"
        }
    }


@app.get("/")
async def landing_page(request: Request):
    """Landing page"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/dashboard")
async def dashboard_page(request: Request):
    """Student dashboard"""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/admin")
async def admin_page(request: Request):
    """Admin dashboard"""
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/course/{course_id}")
async def course_page(request: Request, course_id: int):
    """Course viewer"""
    return templates.TemplateResponse("course.html", {
        "request": request,
        "course_id": course_id
    })


@app.get("/blog")
async def blog_page(request: Request):
    """Blog listing page"""
    return templates.TemplateResponse("blog.html", {"request": request})


@app.get("/chart-analysis")
async def chart_analysis_page(request: Request):
    """Chart analysis tool"""
    return templates.TemplateResponse("chart_analysis.html", {"request": request})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
