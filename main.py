"""
Pipways - Forex Trading Journal API
A comprehensive trading journal and educational platform
"""

import os
import re
import json
import base64
import logging
import hashlib
import io
import csv
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import wraps

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Header, status, Request, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field, validator
from passlib.context import CryptContext
from jose import JWTError, jwt
from PIL import Image

# =============================================================================
# CONFIGURATION & LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/pipways")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
FRONTEND_URL = os.getenv("FRONTEND_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "")

# JWT Configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database pool
db_pool: Optional[asyncpg.Pool] = None

# Simple in-memory cache (replace with Redis in production)
cache_store: Dict[str, Any] = {}
cache_expiry: Dict[str, datetime] = {}

# Rate limiting store
rate_limit_store: Dict[str, List[datetime]] = {}

# =============================================================================
# CACHE FUNCTIONS
# =============================================================================

def cache_get(key: str) -> Any:
    """Get value from cache"""
    if key in cache_store:
        if cache_expiry.get(key, datetime.min) > datetime.utcnow():
            return cache_store[key]
        else:
            del cache_store[key]
            del cache_expiry[key]
    return None

def cache_set(key: str, value: Any, expire_seconds: int = 3600):
    """Set value in cache"""
    cache_store[key] = value
    cache_expiry[key] = datetime.utcnow() + timedelta(seconds=expire_seconds)

def cache_delete(key: str):
    """Delete value from cache"""
    if key in cache_store:
        del cache_store[key]
        if key in cache_expiry:
            del cache_expiry[key]

def cache_clear_pattern(pattern: str):
    """Clear cache keys matching pattern"""
    keys_to_delete = [k for k in cache_store.keys() if pattern in k]
    for key in keys_to_delete:
        cache_delete(key)

# =============================================================================
# RATE LIMITING
# =============================================================================

def rate_limit(max_requests: int = 5, window_seconds: int = 60):
    """Rate limiting decorator"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get client IP from request
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            if request:
                client_ip = request.client.host if request.client else "unknown"
                key = f"rate_limit:{func.__name__}:{client_ip}"

                now = datetime.utcnow()
                window_start = now - timedelta(seconds=window_seconds)

                # Get existing requests
                requests = rate_limit_store.get(key, [])
                requests = [r for r in requests if r > window_start]

                if len(requests) >= max_requests:
                    raise HTTPException(
                        status_code=429,
                        detail=f"Rate limit exceeded. Try again in {window_seconds} seconds."
                    )

                requests.append(now)
                rate_limit_store[key] = requests

            return await func(*args, **kwargs)
        return wrapper
    return decorator

# =============================================================================
# DATABASE SETUP
# =============================================================================

async def init_db_pool():
    """Initialize database connection pool"""
    global db_pool
    try:
        ssl_mode = "require" if ENVIRONMENT == "production" else "prefer"
        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=60,
            ssl=ssl_mode
        )
        logger.info("Database pool initialized successfully")
        await create_tables()
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        db_pool = None

async def create_tables():
    """Create database tables if they don't exist"""
    if not db_pool:
        return

    async with db_pool.acquire() as conn:
        # Users table - with all required columns
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE,
                subscription_status VARCHAR(50) DEFAULT 'trial',
                subscription_ends_at TIMESTAMP,
                trial_ends_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Check if is_admin column exists, add if not
        try:
            await conn.fetch("SELECT is_admin FROM users LIMIT 1")
        except:
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE")

        # Check if trial_ends_at column exists
        try:
            await conn.fetch("SELECT trial_ends_at FROM users LIMIT 1")
        except:
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP")

        # Check if subscription_ends_at column exists
        try:
            await conn.fetch("SELECT subscription_ends_at FROM users LIMIT 1")
        except:
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_ends_at TIMESTAMP")

        # Trades table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                pair VARCHAR(20) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                pips DECIMAL(10,2) NOT NULL,
                grade VARCHAR(5) NOT NULL,
                entry_price DECIMAL(15,5),
                exit_price DECIMAL(15,5),
                checklist_completed BOOLEAN DEFAULT FALSE,
                checklist_data JSONB,
                tags TEXT[],
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Courses table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                category VARCHAR(100),
                level VARCHAR(50) NOT NULL,
                thumbnail_url TEXT,
                lessons JSONB DEFAULT '[]',
                quiz_questions JSONB DEFAULT '[]',
                passing_score INTEGER DEFAULT 70,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # User courses (progress tracking)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_courses (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
                progress_percentage INTEGER DEFAULT 0,
                completed_lessons INTEGER[] DEFAULT '{}',
                quiz_score INTEGER,
                certificate_issued BOOLEAN DEFAULT FALSE,
                started_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP,
                UNIQUE(user_id, course_id)
            )
        """)

        # Webinars table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS webinars (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                level VARCHAR(50),
                scheduled_at TIMESTAMP NOT NULL,
                zoom_meeting_id VARCHAR(100),
                zoom_join_url TEXT,
                recording_url TEXT,
                is_recorded BOOLEAN DEFAULT FALSE,
                reminder_sent BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Webinar registrations
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS webinar_registrations (
                id SERIAL PRIMARY KEY,
                webinar_id INTEGER REFERENCES webinars(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                registered_at TIMESTAMP DEFAULT NOW(),
                attended BOOLEAN DEFAULT FALSE,
                UNIQUE(webinar_id, user_id)
            )
        """)

        # Blog posts
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blog_posts (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                slug VARCHAR(255) UNIQUE NOT NULL,
                content TEXT NOT NULL,
                excerpt TEXT,
                category VARCHAR(100),
                tags TEXT[],
                featured_image TEXT,
                published BOOLEAN DEFAULT FALSE,
                view_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Performance analyses
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS performance_analyses (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                file_name VARCHAR(255),
                analysis_result JSONB,
                trader_type VARCHAR(100),
                performance_score INTEGER,
                risk_appetite VARCHAR(50),
                recommendations JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Payments
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                paystack_reference VARCHAR(255),
                amount DECIMAL(10,2),
                status VARCHAR(50),
                paid_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Course reviews
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS course_reviews (
                id SERIAL PRIMARY KEY,
                course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                review TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(course_id, user_id)
            )
        """)

        # Insert sample courses if none exist
        existing_courses = await conn.fetchval("SELECT COUNT(*) FROM courses")
        if existing_courses == 0:
            await conn.execute("""
                INSERT INTO courses (title, description, category, level, lessons, quiz_questions, passing_score) VALUES
                ('Forex Fundamentals', 'Learn the basics of forex trading', 'basics', 'beginner', 
                 '[{"id": 1, "title": "What is Forex?", "duration": "10 min", "video_url": ""}, {"id": 2, "title": "Currency Pairs", "duration": "15 min", "video_url": ""}]'::jsonb,
                 '[{"question": "What does EUR/USD represent?", "options": ["Euro vs US Dollar", "US Dollar vs Euro", "European Stock Index"], "correct": 0}]'::jsonb, 70),
                ('Technical Analysis Basics', 'Master chart patterns and indicators', 'technical_analysis', 'beginner',
                 '[{"id": 1, "title": "Support and Resistance", "duration": "20 min", "video_url": ""}]'::jsonb,
                 '[]'::jsonb, 70),
                ('Risk Management', 'Protect your capital with proper risk management', 'risk_management', 'intermediate',
                 '[{"id": 1, "title": "Position Sizing", "duration": "25 min", "video_url": ""}]'::jsonb,
                 '[]'::jsonb, 80)
            """)

        # Insert sample webinars if none exist
        existing_webinars = await conn.fetchval("SELECT COUNT(*) FROM webinars")
        if existing_webinars == 0:
            await conn.execute("""
                INSERT INTO webinars (title, description, level, scheduled_at, zoom_join_url) VALUES
                ('Live Trading Session', 'Join us for live market analysis and trading', 'all_levels', NOW() + INTERVAL '7 days', 'https://zoom.us/j/example'),
                ('Q&A with Pro Traders', 'Ask questions and get answers from experienced traders', 'all_levels', NOW() + INTERVAL '14 days', 'https://zoom.us/j/example2')
            """)

        logger.info("Database tables created/verified successfully")

# =============================================================================
# LIFESPAN CONTEXT
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager"""
    await init_db_pool()
    yield
    if db_pool:
        await db_pool.close()

# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="Pipways API",
    description="Forex Trading Journal and Educational Platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Configuration
origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "https://pipways-web.onrender.com",
    "https://pipways-web-nhem.onrender.com",
    "https://www.pipways.com",
    "https://pipways.com",
]

if FRONTEND_URL:
    origins.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers middleware
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = datetime.utcnow()
    response = await call_next(request)
    duration = (datetime.utcnow() - start).total_seconds()

    logger.info(
        f"{request.method} {request.url.path} - {response.status_code} - {duration:.3f}s"
    )
    return response

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    id: int
    email: str
    name: str
    is_admin: bool
    subscription_status: str
    trial_ends_at: Optional[str] = None
    subscription_ends_at: Optional[str] = None

class TradeResponse(BaseModel):
    id: int
    user_id: int
    pair: str
    direction: str
    pips: float
    grade: str
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    checklist_completed: bool
    created_at: str

class CourseResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    category: Optional[str]
    level: str
    thumbnail_url: Optional[str]
    progress_percentage: int = 0
    completed_lessons: List[int] = []
    certificate_issued: bool = False
    avg_rating: Optional[float] = None
    review_count: int = 0

class WebinarResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    level: Optional[str]
    scheduled_at: str
    is_live: bool
    time_until: Dict[str, int]
    registered_count: int
    is_registered: bool = False

class PerformanceAnalysisResponse(BaseModel):
    id: int
    performance_score: int
    trader_type: str
    risk_appetite: str
    score_breakdown: Dict[str, int]
    strengths: List[str]
    weaknesses: List[str]
    improvements: Dict[str, List[Dict]]
    suggested_goal: Dict[str, str]
    created_at: str

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password[:72])

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password[:72], hashed_password)

def create_access_token(data: dict) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    """Get current user from JWT token"""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")

        if not db_pool:
            raise HTTPException(status_code=503, detail="Database not available")

        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT id, email, name, is_admin, subscription_status, trial_ends_at, subscription_ends_at FROM users WHERE id = $1",
                int(user_id)
            )
            if user is None:
                raise HTTPException(status_code=401, detail="User not found")
            return dict(user)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def check_trial_limits(user: dict):
    """Check if user has exceeded trial limits"""
    if user.get("subscription_status") == "trial":
        trial_ends = user.get("trial_ends_at")
        if trial_ends and trial_ends < datetime.utcnow():
            raise HTTPException(status_code=403, detail="Trial has expired. Please upgrade to Pro.")
    return True

# =============================================================================
# HEALTH & DEBUG ENDPOINTS
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        if db_pool:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "database": "connected" if db_pool else "not_connected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }
        )

@app.get("/debug")
async def debug_info():
    """Debug endpoint - returns system info"""
    return {
        "db_pool_initialized": db_pool is not None,
        "database_url_set": bool(os.getenv("DATABASE_URL")),
        "secret_key_set": bool(os.getenv("SECRET_KEY")),
        "openrouter_key_set": bool(os.getenv("OPENROUTER_API_KEY")),
        "environment": os.getenv("ENVIRONMENT", "unknown"),
        "timestamp": datetime.utcnow().isoformat()
    }

# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

@app.post("/auth/register", response_model=TokenResponse)
@rate_limit(max_requests=3, window_seconds=60)
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form(...)
):
    """Register a new user with 3-day trial"""
    # Check database connection
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not connected. Please try again later.")

    try:
        # Validate email format
        email = email.lower().strip()
        if '@' not in email or '.' not in email.split('@')[1]:
            raise HTTPException(status_code=400, detail="Invalid email format")

        # Validate password length
        if len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

        # Validate name
        if len(name.strip()) < 2:
            raise HTTPException(status_code=400, detail="Name must be at least 2 characters")

        async with db_pool.acquire() as conn:
            # Check if email exists
            existing = await conn.fetchval(
                "SELECT id FROM users WHERE email = $1",
                email
            )
            if existing:
                raise HTTPException(status_code=400, detail="Email already registered")

            # Hash password
            password_hash = hash_password(password)

            # Create user with 3-day trial
            trial_ends = datetime.utcnow() + timedelta(days=3)

            user_id = await conn.fetchval("""
                INSERT INTO users (email, password_hash, name, trial_ends_at, is_admin)
                VALUES ($1, $2, $3, $4, FALSE)
                RETURNING id
            """, email, password_hash, name.strip(), trial_ends)

            # Create access token
            token = create_access_token({"sub": str(user_id)})

            return {
                "access_token": token,
                "token_type": "bearer",
                "id": user_id,
                "email": email,
                "name": name.strip(),
                "is_admin": False,
                "subscription_status": "trial",
                "trial_ends_at": trial_ends.isoformat()
            }
    except HTTPException:
        raise
    except asyncpg.exceptions.UniqueViolationError:
        raise HTTPException(status_code=400, detail="Email already registered")
    except Exception as e:
        logger.error(f"Registration error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)[:100]}")

@app.post("/auth/login", response_model=TokenResponse)
@rate_limit(max_requests=5, window_seconds=60)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    """Login and return JWT token"""
    # Check database connection
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not connected. Please try again later.")

    try:
        # Normalize email
        email = email.lower().strip()

        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT id, email, password_hash, name, is_admin, subscription_status, trial_ends_at, subscription_ends_at FROM users WHERE email = $1",
                email
            )

            if not user or not verify_password(password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="Invalid email or password")

            # Create access token
            token = create_access_token({"sub": str(user["id"])})

            return {
                "access_token": token,
                "token_type": "bearer",
                "id": user["id"],
                "email": user["email"],
                "name": user["name"],
                "is_admin": user["is_admin"] if user["is_admin"] is not None else False,
                "subscription_status": user["subscription_status"],
                "trial_ends_at": user["trial_ends_at"].isoformat() if user["trial_ends_at"] else None,
                "subscription_ends_at": user["subscription_ends_at"].isoformat() if user["subscription_ends_at"] else None
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)[:100]}")

# =============================================================================
# TRADES ENDPOINTS
# =============================================================================

@app.get("/trades", response_model=List[TradeResponse])
async def get_trades(current_user: dict = Depends(get_current_user)):
    """Get all trades for current user"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    cache_key = f"trades:{current_user['id']}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM trades WHERE user_id = $1 ORDER BY created_at DESC",
                current_user["id"]
            )
            result = [dict(row) for row in rows]
            cache_set(cache_key, result, 300)  # Cache for 5 minutes
            return result
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch trades")

@app.post("/trades")
async def create_trade(
    pair: str = Form(...),
    direction: str = Form(...),
    pips: float = Form(...),
    grade: str = Form(...),
    entry_price: Optional[float] = Form(None),
    exit_price: Optional[float] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """Create a new trade"""
    check_trial_limits(current_user)

    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            # Check trial trade limit
            if current_user.get("subscription_status") == "trial":
                trade_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM trades WHERE user_id = $1",
                    current_user["id"]
                )
                if trade_count >= 5:
                    raise HTTPException(
                        status_code=403, 
                        detail="Trial limit reached (5 trades). Upgrade to Pro for unlimited trades."
                    )

            trade_id = await conn.fetchval("""
                INSERT INTO trades (user_id, pair, direction, pips, grade, entry_price, exit_price)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
            """, current_user["id"], pair.upper(), direction.upper(), pips, grade.upper(), 
                 entry_price, exit_price)

            # Clear trades cache
            cache_delete(f"trades:{current_user['id']}")
            cache_delete(f"analytics:{current_user['id']}")

            return {"id": trade_id, "message": "Trade created successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating trade: {e}")
        raise HTTPException(status_code=500, detail="Failed to create trade")

@app.get("/trades/export")
async def export_trades(
    format: str = "csv",
    current_user: dict = Depends(get_current_user)
):
    """Export trades to CSV or PDF"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT pair, direction, pips, grade, entry_price, exit_price, created_at FROM trades WHERE user_id = $1 ORDER BY created_at DESC",
                current_user["id"]
            )

        if format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Pair", "Direction", "Pips", "Grade", "Entry Price", "Exit Price", "Date"])
            for row in rows:
                writer.writerow([
                    row["pair"], row["direction"], row["pips"], row["grade"],
                    row["entry_price"], row["exit_price"], row["created_at"].isoformat()
                ])

            output.seek(0)
            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=trades.csv"}
            )
        else:
            raise HTTPException(status_code=400, detail="Format not supported")
    except Exception as e:
        logger.error(f"Error exporting trades: {e}")
        raise HTTPException(status_code=500, detail="Failed to export trades")

# =============================================================================
# ANALYTICS ENDPOINTS
# =============================================================================

@app.get("/analytics/dashboard")
async def get_analytics(current_user: dict = Depends(get_current_user)):
    """Get comprehensive analytics for dashboard"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    cache_key = f"analytics:{current_user['id']}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    try:
        async with db_pool.acquire() as conn:
            # Get all trades
            trades = await conn.fetch(
                "SELECT * FROM trades WHERE user_id = $1 ORDER BY created_at",
                current_user["id"]
            )

            if not trades:
                return {
                    "total_trades": 0,
                    "win_rate": 0,
                    "total_pips": 0,
                    "profit_factor": 0,
                    "equity_curve": [],
                    "monthly_performance": [],
                    "pair_performance": [],
                    "grade_distribution": {}
                }

            # Calculate metrics
            total_trades = len(trades)
            wins = sum(1 for t in trades if t["pips"] > 0)
            win_rate = round((wins / total_trades) * 100, 1)
            total_pips = sum(t["pips"] for t in trades)

            # Profit factor
            winning_pips = sum(t["pips"] for t in trades if t["pips"] > 0)
            losing_pips = abs(sum(t["pips"] for t in trades if t["pips"] < 0))
            profit_factor = round(winning_pips / losing_pips, 2) if losing_pips > 0 else winning_pips

            # Equity curve
            cumulative = 0
            equity_curve = []
            for trade in trades:
                cumulative += trade["pips"]
                equity_curve.append({
                    "date": trade["created_at"].isoformat(),
                    "cumulative_pips": round(cumulative, 2)
                })

            # Monthly performance
            monthly = {}
            for trade in trades:
                month = trade["created_at"].strftime("%Y-%m")
                if month not in monthly:
                    monthly[month] = {"pips": 0, "trades": 0}
                monthly[month]["pips"] += trade["pips"]
                monthly[month]["trades"] += 1

            monthly_performance = [
                {"month": k, "pips": round(v["pips"], 2), "trades": v["trades"]}
                for k, v in sorted(monthly.items())
            ]

            # Pair performance
            pair_stats = {}
            for trade in trades:
                pair = trade["pair"]
                if pair not in pair_stats:
                    pair_stats[pair] = {"trades": 0, "wins": 0, "total_pips": 0}
                pair_stats[pair]["trades"] += 1
                if trade["pips"] > 0:
                    pair_stats[pair]["wins"] += 1
                pair_stats[pair]["total_pips"] += trade["pips"]

            pair_performance = [
                {
                    "pair": k,
                    "trades": v["trades"],
                    "win_rate": round((v["wins"] / v["trades"]) * 100, 1),
                    "total_pips": round(v["total_pips"], 2)
                }
                for k, v in pair_stats.items()
            ]

            # Grade distribution
            grade_dist = {}
            for trade in trades:
                grade = trade["grade"]
                grade_dist[grade] = grade_dist.get(grade, 0) + 1

            result = {
                "total_trades": total_trades,
                "win_rate": win_rate,
                "total_pips": round(total_pips, 2),
                "profit_factor": profit_factor,
                "equity_curve": equity_curve,
                "monthly_performance": monthly_performance,
                "pair_performance": pair_performance,
                "grade_distribution": grade_dist
            }

            cache_set(cache_key, result, 300)
            return result
    except Exception as e:
        logger.error(f"Error fetching analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")

# =============================================================================
# COURSES ENDPOINTS
# =============================================================================

@app.get("/courses", response_model=List[CourseResponse])
async def get_courses(current_user: dict = Depends(get_current_user)):
    """Get all courses with user progress"""
    cache_key = "courses:all"
    cached = cache_get(cache_key)

    try:
        if not db_pool:
            raise HTTPException(status_code=503, detail="Database not available")

        async with db_pool.acquire() as conn:
            # Get courses with ratings
            courses = await conn.fetch("""
                SELECT c.*, 
                       COALESCE(AVG(cr.rating), 0) as avg_rating,
                       COUNT(cr.id) as review_count
                FROM courses c
                LEFT JOIN course_reviews cr ON c.id = cr.course_id
                GROUP BY c.id
                ORDER BY c.created_at DESC
            """)

            # Get user progress
            user_courses = await conn.fetch(
                "SELECT * FROM user_courses WHERE user_id = $1",
                current_user["id"]
            )
            user_progress = {uc["course_id"]: dict(uc) for uc in user_courses}

            result = []
            for course in courses:
                progress = user_progress.get(course["id"], {})
                result.append({
                    "id": course["id"],
                    "title": course["title"],
                    "description": course["description"],
                    "category": course["category"],
                    "level": course["level"],
                    "thumbnail_url": course["thumbnail_url"],
                    "progress_percentage": progress.get("progress_percentage", 0),
                    "completed_lessons": progress.get("completed_lessons", []),
                    "certificate_issued": progress.get("certificate_issued", False),
                    "avg_rating": round(course["avg_rating"], 1) if course["avg_rating"] else None,
                    "review_count": course["review_count"]
                })

            cache_set(cache_key, result, 3600)
            return result
    except Exception as e:
        logger.error(f"Error fetching courses: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch courses")

@app.post("/courses/{course_id}/enroll")
async def enroll_course(course_id: int, current_user: dict = Depends(get_current_user)):
    """Enroll in a course"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            # Check if already enrolled
            existing = await conn.fetchval(
                "SELECT id FROM user_courses WHERE user_id = $1 AND course_id = $2",
                current_user["id"], course_id
            )
            if existing:
                return {"message": "Already enrolled"}

            await conn.execute("""
                INSERT INTO user_courses (user_id, course_id)
                VALUES ($1, $2)
            """, current_user["id"], course_id)

            return {"message": "Enrolled successfully"}
    except Exception as e:
        logger.error(f"Error enrolling in course: {e}")
        raise HTTPException(status_code=500, detail="Failed to enroll")

@app.post("/courses/{course_id}/progress")
async def update_course_progress(
    course_id: int,
    lesson_id: int = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """Update course progress"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            # Get course lessons
            course = await conn.fetchrow(
                "SELECT lessons FROM courses WHERE id = $1",
                course_id
            )
            if not course:
                raise HTTPException(status_code=404, detail="Course not found")

            lessons = json.loads(course["lessons"]) if isinstance(course["lessons"], str) else course["lessons"]
            total_lessons = len(lessons)

            # Update progress
            await conn.execute("""
                UPDATE user_courses 
                SET completed_lessons = array_append(completed_lessons, $1),
                    progress_percentage = LEAST(100, (array_length(array_append(completed_lessons, $1), 1) * 100 / $2)),
                    completed_at = CASE WHEN array_length(array_append(completed_lessons, $1), 1) >= $2 THEN NOW() ELSE completed_at END
                WHERE user_id = $3 AND course_id = $4
            """, lesson_id, total_lessons, current_user["id"], course_id)

            # Clear cache
            cache_delete("courses:all")

            return {"message": "Progress updated"}
    except Exception as e:
        logger.error(f"Error updating progress: {e}")
        raise HTTPException(status_code=500, detail="Failed to update progress")

@app.get("/courses/{course_id}/reviews")
async def get_course_reviews(course_id: int):
    """Get reviews for a course"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            reviews = await conn.fetch("""
                SELECT cr.*, u.name as user_name
                FROM course_reviews cr
                JOIN users u ON cr.user_id = u.id
                WHERE cr.course_id = $1
                ORDER BY cr.created_at DESC
            """, course_id)

            return [dict(r) for r in reviews]
    except Exception as e:
        logger.error(f"Error fetching reviews: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch reviews")

# =============================================================================
# WEBINARS ENDPOINTS
# =============================================================================

@app.get("/webinars", response_model=List[WebinarResponse])
async def get_webinars(current_user: dict = Depends(get_current_user)):
    """Get all webinars with registration status"""
    cache_key = "webinars:all"
    cached = cache_get(cache_key)

    try:
        if not db_pool:
            raise HTTPException(status_code=503, detail="Database not available")

        async with db_pool.acquire() as conn:
            webinars = await conn.fetch("""
                SELECT w.*, COUNT(wr.id) as registered_count
                FROM webinars w
                LEFT JOIN webinar_registrations wr ON w.id = wr.webinar_id
                GROUP BY w.id
                ORDER BY w.scheduled_at ASC
            """)

            # Get user's registrations
            user_regs = await conn.fetch(
                "SELECT webinar_id FROM webinar_registrations WHERE user_id = $1",
                current_user["id"]
            )
            registered_ids = {r["webinar_id"] for r in user_regs}

            result = []
            now = datetime.utcnow()
            for webinar in webinars:
                scheduled = webinar["scheduled_at"]
                is_live = scheduled <= now < scheduled + timedelta(hours=2)

                time_until = {"days": 0, "hours": 0, "minutes": 0}
                if scheduled > now:
                    diff = scheduled - now
                    time_until = {
                        "days": diff.days,
                        "hours": diff.seconds // 3600,
                        "minutes": (diff.seconds % 3600) // 60
                    }

                result.append({
                    "id": webinar["id"],
                    "title": webinar["title"],
                    "description": webinar["description"],
                    "level": webinar["level"],
                    "scheduled_at": scheduled.isoformat(),
                    "is_live": is_live,
                    "time_until": time_until,
                    "registered_count": webinar["registered_count"],
                    "is_registered": webinar["id"] in registered_ids
                })

            cache_set(cache_key, result, 300)
            return result
    except Exception as e:
        logger.error(f"Error fetching webinars: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch webinars")

@app.post("/webinars/{webinar_id}/register")
async def register_webinar(webinar_id: int, current_user: dict = Depends(get_current_user)):
    """Register for a webinar"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            # Check if already registered
            existing = await conn.fetchval(
                "SELECT id FROM webinar_registrations WHERE user_id = $1 AND webinar_id = $2",
                current_user["id"], webinar_id
            )
            if existing:
                return {"message": "Already registered"}

            await conn.execute("""
                INSERT INTO webinar_registrations (user_id, webinar_id)
                VALUES ($1, $2)
            """, current_user["id"], webinar_id)

            # Clear cache
            cache_delete("webinars:all")

            return {"message": "Registered successfully"}
    except Exception as e:
        logger.error(f"Error registering for webinar: {e}")
        raise HTTPException(status_code=500, detail="Failed to register")

# =============================================================================
# AI ANALYSIS ENDPOINTS
# =============================================================================

async def call_openrouter(prompt: str, max_tokens: int = 1000) -> str:
    """Call OpenRouter API for AI responses"""
    if not OPENROUTER_API_KEY:
        return "AI service not configured. Please contact support."

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://pipways.com",
                    "X-Title": "Pipways Trading Journal"
                },
                json={
                    "model": "anthropic/claude-3.5-sonnet",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens
                }
            )

            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            else:
                logger.error(f"OpenRouter error: {response.status_code} - {response.text}")
                return "AI analysis temporarily unavailable. Please try again later."
    except Exception as e:
        logger.error(f"Error calling OpenRouter: {e}")
        return "AI service error. Please try again later."

@app.post("/analyze-chart")
async def analyze_chart(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Analyze a chart image using AI"""
    check_trial_limits(current_user)

    try:
        # Read and optimize image
        contents = await file.read()
        img = Image.open(io.BytesIO(contents))

        # Resize if too large
        max_size = (1200, 800)
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Convert to base64
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        base64_image = base64.b64encode(output.getvalue()).decode()

        # Call AI for analysis
        prompt = f"""Analyze this forex trading chart image. Provide:
1. Setup quality grade (A, B, C, D)
2. Currency pair identified
3. Trade direction (LONG/SHORT)
4. Entry price suggestion
5. Stop loss level
6. Take profit level
7. Risk:Reward ratio
8. Brief technical analysis
9. Key support/resistance levels

Format as JSON with these keys: setup_quality, pair, direction, entry_price, stop_loss, take_profit, risk_reward, analysis, key_levels (array)"""

        # For now, return mock analysis (replace with actual AI call)
        analysis = {
            "setup_quality": "B",
            "pair": "EURUSD",
            "direction": "LONG",
            "entry_price": "1.0850",
            "stop_loss": "1.0820",
            "take_profit": "1.0900",
            "risk_reward": "1:1.67",
            "analysis": "Price is testing support at 1.0850 with bullish divergence on RSI. Good risk:reward setup with clear stop loss below recent low.",
            "key_levels": ["1.0850 (Support)", "1.0900 (Resistance)", "1.0820 (Stop)"]
        }

        return {"analysis": analysis}
    except Exception as e:
        logger.error(f"Error analyzing chart: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze chart")

@app.post("/performance/analyze")
async def analyze_performance(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Analyze trading history and provide performance score"""
    check_trial_limits(current_user)

    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            # Check trial analysis limit
            if current_user.get("subscription_status") == "trial":
                analysis_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM performance_analyses WHERE user_id = $1",
                    current_user["id"]
                )
                if analysis_count >= 1:
                    raise HTTPException(
                        status_code=403,
                        detail="Trial limit reached (1 analysis). Upgrade to Pro for unlimited analyses."
                    )

            # Read file content
            contents = await file.read()

            # Get user's trades for analysis
            trades = await conn.fetch(
                "SELECT * FROM trades WHERE user_id = $1 ORDER BY created_at",
                current_user["id"]
            )

            # Calculate metrics
            total_trades = len(trades)
            wins = sum(1 for t in trades if t["pips"] > 0)
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            total_pips = sum(t["pips"] for t in trades)

            # Generate analysis (mock for now)
            analysis = {
                "performance_score": 72,
                "trader_type": "Trend Following Scalper",
                "risk_appetite": "Moderate",
                "score_breakdown": {
                    "profitability": 75,
                    "risk_management": 68,
                    "consistency": 70,
                    "psychology": 75
                },
                "strengths": [
                    "Good win rate on trending markets",
                    "Disciplined stop loss placement",
                    "Consistent position sizing"
                ],
                "weaknesses": [
                    "Overtrading during consolidation",
                    "Missing major moves due to early exits",
                    "Revenge trading after losses"
                ],
                "improvements": {
                    "high": [
                        {"title": "Reduce Trade Frequency", "description": "Wait for A+ setups only", "actions": [{"id": "course_risk", "name": "Take Risk Management Course"}]},
                        {"title": "Improve Patience", "description": "Let winners run longer", "actions": [{"id": "mentor_patience", "name": "Ask AI Mentor about Patience"}]}
                    ],
                    "medium": [
                        {"title": "Journal Better", "description": "Add more detail to trade notes"}
                    ]
                },
                "suggested_goal": {
                    "id": "reduce_trades",
                    "title": "Reduce Daily Trades by 30%",
                    "description": "Focus on quality over quantity"
                }
            }

            # Save analysis
            await conn.execute("""
                INSERT INTO performance_analyses 
                (user_id, file_name, analysis_result, trader_type, performance_score, risk_appetite, recommendations)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, current_user["id"], file.filename, json.dumps(analysis),
                 analysis["trader_type"], analysis["performance_score"],
                 analysis["risk_appetite"], json.dumps(analysis["improvements"]))

            return {"analysis": analysis}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing performance: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze performance")

@app.get("/performance/history")
async def get_performance_history(current_user: dict = Depends(get_current_user)):
    """Get performance analysis history"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            history = await conn.fetch("""
                SELECT id, performance_score, analysis_result, created_at
                FROM performance_analyses
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT 10
            """, current_user["id"])

            result = []
            for h in history:
                analysis = json.loads(h["analysis_result"]) if isinstance(h["analysis_result"], str) else h["analysis_result"]
                result.append({
                    "id": h["id"],
                    "performance_score": h["performance_score"],
                    "score_breakdown": analysis.get("score_breakdown", {}),
                    "created_at": h["created_at"].isoformat()
                })

            # Calculate improvement
            improvement = 0
            if len(result) >= 2:
                improvement = result[0]["performance_score"] - result[-1]["performance_score"]

            return {
                "history": result,
                "improvement": improvement,
                "trend": "improving" if improvement > 0 else "declining" if improvement < 0 else "stable"
            }
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch history")

@app.get("/mentor-chat")
async def mentor_chat(
    message: str,
    current_user: dict = Depends(get_current_user)
):
    """Chat with AI trading mentor"""
    prompt = f"""You are an experienced forex trading mentor. The trader asks: "{message}"

Provide helpful, practical advice in a supportive tone. Keep your response concise (2-3 paragraphs max)."""

    response = await call_openrouter(prompt, max_tokens=500)
    return {"response": response}

# =============================================================================
# SUBSCRIPTION ENDPOINTS
# =============================================================================

@app.get("/subscription/status")
async def get_subscription_status(current_user: dict = Depends(get_current_user)):
    """Get current subscription status"""
    return {
        "subscription_status": current_user.get("subscription_status"),
        "trial_ends_at": current_user.get("trial_ends_at"),
        "subscription_ends_at": current_user.get("subscription_ends_at")
    }

# =============================================================================
# BLOG ENDPOINTS
# =============================================================================

@app.get("/blog/posts")
async def get_blog_posts(category: Optional[str] = None):
    """Get published blog posts"""
    cache_key = f"blog:posts:{category or 'all'}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            if category:
                posts = await conn.fetch(
                    "SELECT * FROM blog_posts WHERE published = TRUE AND category = $1 ORDER BY created_at DESC",
                    category
                )
            else:
                posts = await conn.fetch(
                    "SELECT * FROM blog_posts WHERE published = TRUE ORDER BY created_at DESC"
                )

            result = [dict(p) for p in posts]
            cache_set(cache_key, result, 3600)
            return result
    except Exception as e:
        logger.error(f"Error fetching blog posts: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch blog posts")

@app.get("/blog/posts/{slug}")
async def get_blog_post(slug: str):
    """Get a specific blog post"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            post = await conn.fetchrow(
                "SELECT * FROM blog_posts WHERE slug = $1 AND published = TRUE",
                slug
            )
            if not post:
                raise HTTPException(status_code=404, detail="Post not found")

            # Increment view count
            await conn.execute(
                "UPDATE blog_posts SET view_count = view_count + 1 WHERE id = $1",
                post["id"]
            )

            return dict(post)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching blog post: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch blog post")

# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================

@app.get("/admin/stats")
async def get_admin_stats(current_user: dict = Depends(get_current_user)):
    """Get platform statistics (admin only)"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT 
                    (SELECT COUNT(*) FROM users) as total_users,
                    (SELECT COUNT(*) FROM trades) as total_trades,
                    (SELECT COUNT(*) FROM courses) as total_courses,
                    (SELECT COUNT(*) FROM webinars) as total_webinars
            """)

            return dict(stats)
    except Exception as e:
        logger.error(f"Error fetching admin stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stats")

@app.post("/admin/blog/posts")
async def create_blog_post(
    title: str = Form(...),
    slug: str = Form(...),
    content: str = Form(...),
    excerpt: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    published: bool = Form(False),
    current_user: dict = Depends(get_current_user)
):
    """Create a new blog post (admin only)"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            post_id = await conn.fetchval("""
                INSERT INTO blog_posts (title, slug, content, excerpt, category, published)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            """, title, slug, content, excerpt, category, published)

            # Clear cache
            cache_delete_pattern("blog:")

            return {"id": post_id, "message": "Blog post created"}
    except Exception as e:
        logger.error(f"Error creating blog post: {e}")
        raise HTTPException(status_code=500, detail="Failed to create blog post")

@app.post("/admin/courses")
async def create_course(
    title: str = Form(...),
    description: str = Form(...),
    level: str = Form(...),
    category: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """Create a new course (admin only)"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            course_id = await conn.fetchval("""
                INSERT INTO courses (title, description, level, category)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """, title, description, level, category)

            # Clear cache
            cache_delete("courses:all")

            return {"id": course_id, "message": "Course created"}
    except Exception as e:
        logger.error(f"Error creating course: {e}")
        raise HTTPException(status_code=500, detail="Failed to create course")

@app.post("/admin/webinars")
async def create_webinar(
    title: str = Form(...),
    description: str = Form(...),
    scheduled_at: datetime = Form(...),
    zoom_join_url: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """Create a new webinar (admin only)"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            webinar_id = await conn.fetchval("""
                INSERT INTO webinars (title, description, scheduled_at, zoom_join_url)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """, title, description, scheduled_at, zoom_join_url)

            # Clear cache
            cache_delete("webinars:all")

            return {"id": webinar_id, "message": "Webinar created"}
    except Exception as e:
        logger.error(f"Error creating webinar: {e}")
        raise HTTPException(status_code=500, detail="Failed to create webinar")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
t_admin_user)):
    """Get platform statistics"""
    try:
        async with db_pool.acquire() as conn:
            stats = {
                "total_users": await conn.fetchval("SELECT COUNT(*) FROM users"),
                "total_trades": await conn.fetchval("SELECT COUNT(*) FROM trades"),
                "active_subscriptions": await conn.fetchval("""
                    SELECT COUNT(*) FROM users 
                    WHERE subscription_status = 'active' AND subscription_ends_at > NOW()
                """),
                "trial_users": await conn.fetchval("""
                    SELECT COUNT(*) FROM users 
                    WHERE subscription_status = 'trial' AND trial_ends_at > NOW()
                """),
                "total_courses": await conn.fetchval("SELECT COUNT(*) FROM courses"),
                "total_webinars": await conn.fetchval("SELECT COUNT(*) FROM webinars"),
                "total_blog_posts": await conn.fetchval("SELECT COUNT(*) FROM blog_posts"),
                "published_blog_posts": await conn.fetchval("SELECT COUNT(*) FROM blog_posts WHERE published = TRUE"),
                "recent_signups": await conn.fetchval("""
                    SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '7 days'
                """),
                "recent_trades": await conn.fetchval("""
                    SELECT COUNT(*) FROM trades WHERE created_at > NOW() - INTERVAL '7 days'
                """)
            }
            
            return stats
    except Exception as e:
        logger.error(f"Admin stats error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stats")

@app.get("/admin/blog/posts")
async def get_all_blog_posts_admin(admin: Dict[str, Any] = Depends(get_admin_user)):
    """Get all blog posts including unpublished"""
    try:
        async with db_pool.acquire() as conn:
            posts = await conn.fetch("""
                SELECT id, title, slug, excerpt, category, published, view_count, created_at
                FROM blog_posts
                ORDER BY created_at DESC
            """)
            
            return {"posts": [dict(p) for p in posts]}
    except Exception as e:
        logger.error(f"Admin get posts error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch posts")

@app.post("/admin/blog/posts")
async def create_blog_post(post: BlogPostCreate, admin: Dict[str, Any] = Depends(get_admin_user)):
    """Create new blog post"""
    try:
        async with db_pool.acquire() as conn:
            # Check slug uniqueness
            existing = await conn.fetchval("SELECT id FROM blog_posts WHERE slug = $1", post.slug)
            if existing:
                raise HTTPException(status_code=400, detail="Slug already exists")
            
            post_id = await conn.fetchval("""
                INSERT INTO blog_posts (title, slug, content, excerpt, category, tags, featured_image, published)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            """, post.title, post.slug, post.content, post.excerpt, post.category, post.tags, post.featured_image, post.published)
            
            return {"id": post_id, "message": "Blog post created"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create blog post error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create post")

@app.put("/admin/blog/posts/{post_id}")
async def update_blog_post(post_id: int, post: BlogPostCreate, admin: Dict[str, Any] = Depends(get_admin_user)):
    """Update blog post"""
    try:
        async with db_pool.acquire() as conn:
            # Check if post exists
            existing = await conn.fetchval("SELECT id FROM blog_posts WHERE id = $1", post_id)
            if not existing:
                raise HTTPException(status_code=404, detail="Post not found")
            
            await conn.execute("""
                UPDATE blog_posts
                SET title = $1, slug = $2, content = $3, excerpt = $4, category = $5, 
                    tags = $6, featured_image = $7, published = $8, updated_at = NOW()
                WHERE id = $9
            """, post.title, post.slug, post.content, post.excerpt, post.category, 
                post.tags, post.featured_image, post.published, post_id)
            
            return {"message": "Blog post updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update blog post error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update post")

@app.delete("/admin/blog/posts/{post_id}")
async def delete_blog_post(post_id: int, admin: Dict[str, Any] = Depends(get_admin_user)):
    """Delete blog post"""
    try:
        async with db_pool.acquire() as conn:
            result = await conn.execute("DELETE FROM blog_posts WHERE id = $1", post_id)
            
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Post not found")
            
            return {"message": "Blog post deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete blog post error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete post")

@app.post("/admin/courses")
async def create_course(course: CourseCreate, admin: Dict[str, Any] = Depends(get_admin_user)):
    """Create new course"""
    try:
        async with db_pool.acquire() as conn:
            course_id = await conn.fetchval("""
                INSERT INTO courses (title, description, level, thumbnail_url, lessons, quiz_questions, passing_score)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
            """, course.title, course.description, course.level, course.thumbnail_url,
                json.dumps(course.lessons), json.dumps(course.quiz_questions), course.passing_score)
            
            return {"id": course_id, "message": "Course created"}
    except Exception as e:
        logger.error(f"Create course error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create course")

@app.post("/admin/webinars")
async def create_webinar(webinar: WebinarCreate, admin: Dict[str, Any] = Depends(get_admin_user)):
    """Create new webinar"""
    try:
        async with db_pool.acquire() as conn:
            webinar_id = await conn.fetchval("""
                INSERT INTO webinars (title, description, level, scheduled_at, zoom_meeting_id, zoom_join_url)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            """, webinar.title, webinar.description, webinar.level, webinar.scheduled_at,
                webinar.zoom_meeting_id, webinar.zoom_join_url)
            
            return {"id": webinar_id, "message": "Webinar created"}
    except Exception as e:
        logger.error(f"Create webinar error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create webinar")

# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again later."}
    )

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
