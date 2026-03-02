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
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from contextlib import asynccontextmanager
from dataclasses import dataclass

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, validator
from passlib.context import CryptContext
from jose import JWTError, jwt

# =============================================================================
# CONFIGURATION & LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("pipways")

# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/pipways")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_DAYS = int(os.getenv("JWT_EXPIRATION_DAYS", "30"))
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# =============================================================================
# DATABASE POOL
# =============================================================================

db_pool: Optional[asyncpg.Pool] = None

async def init_db_pool():
    """Initialize database connection pool"""
    global db_pool
    
    ssl_mode = "require" if ENVIRONMENT == "production" else "prefer"
    
    try:
        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=60,
            ssl=ssl_mode if ssl_mode == "require" else None
        )
        logger.info("Database pool initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise

async def close_db_pool():
    """Close database connection pool"""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Database pool closed")

async def get_db():
    """Get database connection from pool"""
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not initialized")
    async with db_pool.acquire() as conn:
        yield conn

# =============================================================================
# DATABASE SCHEMA CREATION
# =============================================================================

CREATE_TABLES_SQL = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    subscription_status VARCHAR(50) DEFAULT 'trial',
    subscription_ends_at TIMESTAMP,
    trial_ends_at TIMESTAMP DEFAULT (NOW() + INTERVAL '3 days'),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Trades table
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    pair VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('buy', 'sell')),
    pips DECIMAL(10, 2),
    grade VARCHAR(2),
    entry_price DECIMAL(15, 5),
    exit_price DECIMAL(15, 5),
    checklist_completed BOOLEAN DEFAULT FALSE,
    checklist_data JSONB,
    chart_image_url TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Courses table
CREATE TABLE IF NOT EXISTS courses (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    level VARCHAR(50) NOT NULL CHECK (level IN ('beginner', 'intermediate', 'advanced')),
    thumbnail_url TEXT,
    lessons JSONB DEFAULT '[]',
    quiz_questions JSONB DEFAULT '[]',
    passing_score INTEGER DEFAULT 70,
    created_at TIMESTAMP DEFAULT NOW()
);

-- User courses (enrollments)
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
);

-- Webinars table
CREATE TABLE IF NOT EXISTS webinars (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    level VARCHAR(50) NOT NULL CHECK (level IN ('beginner', 'intermediate', 'advanced')),
    scheduled_at TIMESTAMP NOT NULL,
    zoom_meeting_id VARCHAR(100),
    zoom_join_url TEXT,
    recording_url TEXT,
    is_recorded BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Webinar registrations
CREATE TABLE IF NOT EXISTS webinar_registrations (
    id SERIAL PRIMARY KEY,
    webinar_id INTEGER REFERENCES webinars(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    registered_at TIMESTAMP DEFAULT NOW(),
    attended BOOLEAN DEFAULT FALSE,
    UNIQUE(webinar_id, user_id)
);

-- Blog posts table
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
);

-- Performance analyses table
CREATE TABLE IF NOT EXISTS performance_analyses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    file_name VARCHAR(255),
    analysis_result TEXT,
    trader_type VARCHAR(100),
    performance_score INTEGER,
    risk_appetite VARCHAR(50),
    recommendations JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Payments table
CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    paystack_reference VARCHAR(255),
    amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades(created_at);
CREATE INDEX IF NOT EXISTS idx_user_courses_user_id ON user_courses(user_id);
CREATE INDEX IF NOT EXISTS idx_webinar_registrations_webinar_id ON webinar_registrations(webinar_id);
CREATE INDEX IF NOT EXISTS idx_blog_posts_slug ON blog_posts(slug);
CREATE INDEX IF NOT EXISTS idx_blog_posts_published ON blog_posts(published);
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
"""

async def create_tables():
    """Create database tables"""
    async with db_pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)
        logger.info("Database tables created successfully")

async def seed_initial_data():
    """Seed initial data (courses, blog posts, etc.)"""
    async with db_pool.acquire() as conn:
        # Check if courses exist
        course_count = await conn.fetchval("SELECT COUNT(*) FROM courses")
        if course_count == 0:
            # Seed courses
            courses = [
                {
                    "title": "Forex Fundamentals",
                    "description": "Learn the basics of forex trading including currency pairs, pips, and market structure.",
                    "level": "beginner",
                    "lessons": [
                        {"id": 1, "title": "What is Forex?", "duration": "15 min"},
                        {"id": 2, "title": "Currency Pairs Explained", "duration": "20 min"},
                        {"id": 3, "title": "Understanding Pips", "duration": "15 min"}
                    ],
                    "quiz_questions": [
                        {"question": "What does pip stand for?", "options": ["Price Interest Point", "Percentage in Point", "Point in Percentage"], "correct": 1}
                    ]
                },
                {
                    "title": "Technical Analysis Mastery",
                    "description": "Master chart patterns, indicators, and price action strategies.",
                    "level": "intermediate",
                    "lessons": [
                        {"id": 1, "title": "Support and Resistance", "duration": "25 min"},
                        {"id": 2, "title": "Trend Lines", "duration": "20 min"},
                        {"id": 3, "title": "Chart Patterns", "duration": "30 min"}
                    ],
                    "quiz_questions": []
                },
                {
                    "title": "Advanced Trading Psychology",
                    "description": "Develop the mental discipline required for consistent trading success.",
                    "level": "advanced",
                    "lessons": [
                        {"id": 1, "title": "Emotional Control", "duration": "20 min"},
                        {"id": 2, "title": "Risk Management", "duration": "25 min"},
                        {"id": 3, "title": "Building a Trading Plan", "duration": "30 min"}
                    ],
                    "quiz_questions": []
                }
            ]
            
            for course in courses:
                await conn.execute("""
                    INSERT INTO courses (title, description, level, lessons, quiz_questions)
                    VALUES ($1, $2, $3, $4, $5)
                """, course["title"], course["description"], course["level"],
                    json.dumps(course["lessons"]), json.dumps(course["quiz_questions"]))
            logger.info("Courses seeded successfully")

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str = Field(..., min_length=2)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

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

class TradeCreate(BaseModel):
    pair: str = Field(..., pattern=r'^[A-Z]{6}$')
    direction: str = Field(..., pattern=r'^(buy|sell)$')
    pips: Optional[float] = None
    grade: Optional[str] = Field(None, pattern=r'^[A-F]$')
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    checklist_completed: bool = False
    checklist_data: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None

class TradeResponse(BaseModel):
    id: int
    pair: str
    direction: str
    pips: Optional[float]
    grade: Optional[str]
    entry_price: Optional[float]
    exit_price: Optional[float]
    checklist_completed: bool
    created_at: datetime

class CourseResponse(BaseModel):
    id: int
    title: str
    description: str
    level: str
    thumbnail_url: Optional[str]
    lessons: List[Dict[str, Any]]
    created_at: datetime

class BlogPostResponse(BaseModel):
    id: int
    title: str
    slug: str
    excerpt: Optional[str]
    category: Optional[str]
    tags: List[str]
    featured_image: Optional[str]
    published: bool
    created_at: datetime

class WebinarResponse(BaseModel):
    id: int
    title: str
    description: str
    level: str
    scheduled_at: datetime
    is_recorded: bool

class SubscriptionStatus(BaseModel):
    status: str
    trial_ends_at: Optional[datetime]
    subscription_ends_at: Optional[datetime]
    trades_used: int
    trades_limit: int
    analyses_used: int
    analyses_limit: int

class PaymentInitiate(BaseModel):
    plan: str = Field(..., pattern=r'^(monthly|yearly)$')

class QuizSubmit(BaseModel):
    answers: Dict[int, int]

class ProgressUpdate(BaseModel):
    lesson_id: int
    completed: bool

class BlogPostCreate(BaseModel):
    title: str
    slug: str
    content: str
    excerpt: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = []
    featured_image: Optional[str] = None
    published: bool = False

class CourseCreate(BaseModel):
    title: str
    description: str
    level: str = Field(..., pattern=r'^(beginner|intermediate|advanced)$')
    thumbnail_url: Optional[str] = None
    lessons: List[Dict[str, Any]] = []
    quiz_questions: List[Dict[str, Any]] = []
    passing_score: int = 70

class WebinarCreate(BaseModel):
    title: str
    description: str
    level: str = Field(..., pattern=r'^(beginner|intermediate|advanced)$')
    scheduled_at: datetime
    zoom_meeting_id: Optional[str] = None
    zoom_join_url: Optional[str] = None

# =============================================================================
# AUTHENTICATION UTILITIES
# =============================================================================

def hash_password(password: str) -> str:
    """Hash password with bcrypt (max 72 bytes)"""
    # Truncate to 72 bytes if needed (bcrypt limit)
    password_bytes = password.encode('utf-8')[:72]
    return pwd_context.hash(password_bytes)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: Dict[str, Any]) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=JWT_EXPIRATION_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Get current user from JWT token"""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT id, email, name, is_admin, subscription_status, trial_ends_at, subscription_ends_at FROM users WHERE id = $1",
                int(user_id)
            )
            if user is None:
                raise HTTPException(status_code=401, detail="User not found")
            
            return dict(user)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

async def get_admin_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Verify user is admin"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# =============================================================================
# SUBSCRIPTION UTILITIES
# =============================================================================

async def check_subscription_status(user_id: int) -> Dict[str, Any]:
    """Check user's subscription status and limits"""
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT subscription_status, trial_ends_at, subscription_ends_at FROM users WHERE id = $1",
            user_id
        )
        
        trades_count = await conn.fetchval(
            "SELECT COUNT(*) FROM trades WHERE user_id = $1",
            user_id
        )
        
        analyses_count = await conn.fetchval(
            "SELECT COUNT(*) FROM performance_analyses WHERE user_id = $1",
            user_id
        )
        
        now = datetime.utcnow()
        is_trial = user["subscription_status"] == "trial"
        is_active = (
            user["subscription_status"] == "active" and 
            user["subscription_ends_at"] and 
            user["subscription_ends_at"] > now
        )
        is_trial_active = is_trial and user["trial_ends_at"] and user["trial_ends_at"] > now
        
        if is_trial_active or is_active:
            status = "active" if is_active else "trial"
        else:
            status = "expired"
        
        return {
            "status": status,
            "is_premium": is_active,
            "trial_ends_at": user["trial_ends_at"],
            "subscription_ends_at": user["subscription_ends_at"],
            "trades_used": trades_count,
            "trades_limit": 5 if is_trial else 999999,
            "analyses_used": analyses_count,
            "analyses_limit": 1 if is_trial else 999999,
            "can_create_trade": trades_count < (5 if is_trial else 999999),
            "can_create_analysis": analyses_count < (1 if is_trial else 999999)
        }

# =============================================================================
# AI INTEGRATION
# =============================================================================

async def call_openrouter(messages: List[Dict[str, str]], max_retries: int = 2) -> str:
    """Call OpenRouter API with retry logic"""
    if not OPENROUTER_API_KEY:
        logger.warning("OpenRouter API key not configured")
        return "AI analysis is currently unavailable. Please try again later."
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://pipways.com",
        "X-Title": "Pipways Trading Journal"
    }
    
    payload = {
        "model": "anthropic/claude-3.5-sonnet",
        "messages": messages,
        "max_tokens": 2000,
        "temperature": 0.7
    }
    
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"OpenRouter API error (attempt {attempt + 1}): {e}")
            if attempt == max_retries:
                return "Unable to complete AI analysis at this time. Please try again later."
    
    return "AI analysis failed after multiple attempts."

# =============================================================================
# FASTAPI APPLICATION
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    await init_db_pool()
    await create_tables()
    await seed_initial_data()
    logger.info("Pipways API started successfully")
    
    yield
    
    # Shutdown
    await close_db_pool()
    logger.info("Pipways API shutdown complete")

app = FastAPI(
    title="Pipways API",
    description="Forex Trading Journal and Educational Platform",
    version="1.0.0",
    lifespan=lifespan
)

# =============================================================================
# CORS CONFIGURATION
# =============================================================================

# Build CORS origins list
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

# Add FRONTEND_URL from environment if set
if FRONTEND_URL:
    origins.append(FRONTEND_URL)
    # Also add www variant if not already present
    if FRONTEND_URL.startswith("https://") and not FRONTEND_URL.startswith("https://www."):
        www_variant = FRONTEND_URL.replace("https://", "https://www.")
        if www_variant not in origins:
            origins.append(www_variant)

# Allow all origins in development for easier testing
if ENVIRONMENT == "development":
    origins.append("*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)

logger.info(f"CORS configured with origins: {origins}")

# =============================================================================
# HEALTH CHECK
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

@app.post("/test/register")
async def test_register():
    """Test endpoint for registration debugging"""
    return {
        "message": "Test endpoint working",
        "db_connected": db_pool is not None,
        "timestamp": datetime.utcnow().isoformat()
    }

# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

@app.post("/auth/register", response_model=TokenResponse)
async def register(
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
                INSERT INTO users (email, password_hash, name, trial_ends_at)
                VALUES ($1, $2, $3, $4)
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
    except asyncpg.exceptions.ForeignKeyViolationError as e:
        logger.error(f"Registration FK error: {e}")
        raise HTTPException(status_code=400, detail="Invalid data provided")
    except Exception as e:
        logger.error(f"Registration error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)[:100]}")

@app.post("/auth/login", response_model=TokenResponse)
async def login(
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
                "is_admin": user["is_admin"],
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
async def get_trades(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get all trades for current user"""
    try:
        async with db_pool.acquire() as conn:
            trades = await conn.fetch("""
                SELECT id, pair, direction, pips, grade, entry_price, exit_price, checklist_completed, created_at
                FROM trades
                WHERE user_id = $1
                ORDER BY created_at DESC
            """, current_user["id"])
            
            return [dict(trade) for trade in trades]
    except Exception as e:
        logger.error(f"Get trades error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch trades")

@app.post("/trades", response_model=TradeResponse)
async def create_trade(
    trade_data: TradeCreate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Create a new trade (respects trial limits)"""
    try:
        # Check subscription limits
        sub_status = await check_subscription_status(current_user["id"])
        
        if not sub_status["can_create_trade"]:
            raise HTTPException(
                status_code=403, 
                detail="Trade limit reached. Please upgrade to continue."
            )
        
        async with db_pool.acquire() as conn:
            trade_id = await conn.fetchval("""
                INSERT INTO trades (user_id, pair, direction, pips, grade, entry_price, exit_price, checklist_completed, checklist_data, notes)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            """, 
                current_user["id"],
                trade_data.pair.upper(),
                trade_data.direction.lower(),
                trade_data.pips,
                trade_data.grade,
                trade_data.entry_price,
                trade_data.exit_price,
                trade_data.checklist_completed,
                json.dumps(trade_data.checklist_data) if trade_data.checklist_data else None,
                trade_data.notes
            )
            
            trade = await conn.fetchrow("""
                SELECT id, pair, direction, pips, grade, entry_price, exit_price, checklist_completed, created_at
                FROM trades WHERE id = $1
            """, trade_id)
            
            return dict(trade)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create trade error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create trade")

# =============================================================================
# ANALYTICS ENDPOINTS
# =============================================================================

@app.get("/analytics/dashboard")
async def get_dashboard_analytics(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get comprehensive analytics for dashboard"""
    try:
        async with db_pool.acquire() as conn:
            # Get all trades
            trades = await conn.fetch("""
                SELECT pair, direction, pips, grade, created_at
                FROM trades
                WHERE user_id = $1
                ORDER BY created_at ASC
            """, current_user["id"])
            
            if not trades:
                return {
                    "total_trades": 0,
                    "win_rate": 0,
                    "total_pips": 0,
                    "avg_pips_per_trade": 0,
                    "grade_distribution": {},
                    "pair_performance": {},
                    "equity_curve": [],
                    "recent_trades": []
                }
            
            # Calculate metrics
            total_trades = len(trades)
            winning_trades = sum(1 for t in trades if t["pips"] and t["pips"] > 0)
            win_rate = round((winning_trades / total_trades) * 100, 2) if total_trades > 0 else 0
            total_pips = sum(t["pips"] or 0 for t in trades)
            avg_pips = round(total_pips / total_trades, 2) if total_trades > 0 else 0
            
            # Grade distribution
            grade_distribution = {}
            for t in trades:
                grade = t["grade"] or "Ungraded"
                grade_distribution[grade] = grade_distribution.get(grade, 0) + 1
            
            # Pair performance
            pair_performance = {}
            for t in trades:
                pair = t["pair"]
                if pair not in pair_performance:
                    pair_performance[pair] = {"trades": 0, "pips": 0, "wins": 0}
                pair_performance[pair]["trades"] += 1
                pair_performance[pair]["pips"] += t["pips"] or 0
                if t["pips"] and t["pips"] > 0:
                    pair_performance[pair]["wins"] += 1
            
            # Calculate win rates for pairs
            for pair in pair_performance:
                pair_performance[pair]["win_rate"] = round(
                    (pair_performance[pair]["wins"] / pair_performance[pair]["trades"]) * 100, 2
                )
            
            # Equity curve (cumulative pips)
            equity_curve = []
            cumulative = 0
            for t in trades:
                cumulative += t["pips"] or 0
                equity_curve.append({
                    "date": t["created_at"].isoformat(),
                    "pips": cumulative
                })
            
            # Recent trades (last 5)
            recent_trades = [
                {
                    "pair": t["pair"],
                    "direction": t["direction"],
                    "pips": t["pips"],
                    "grade": t["grade"],
                    "date": t["created_at"].isoformat()
                }
                for t in list(trades)[-5:]
            ]
            
            return {
                "total_trades": total_trades,
                "win_rate": win_rate,
                "total_pips": round(total_pips, 2),
                "avg_pips_per_trade": avg_pips,
                "grade_distribution": grade_distribution,
                "pair_performance": pair_performance,
                "equity_curve": equity_curve,
                "recent_trades": recent_trades
            }
    except Exception as e:
        logger.error(f"Dashboard analytics error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")

# =============================================================================
# CHECKLIST ENDPOINTS
# =============================================================================

@app.get("/checklist/template")
async def get_checklist_template():
    """Get pre-trade checklist items"""
    return {
        "checklist": [
            {"id": 1, "item": "Identified clear trend direction", "category": "Analysis"},
            {"id": 2, "item": "Found support/resistance level", "category": "Analysis"},
            {"id": 3, "item": "Confirmed entry signal", "category": "Entry"},
            {"id": 4, "item": "Set stop loss", "category": "Risk Management"},
            {"id": 5, "item": "Calculated position size", "category": "Risk Management"},
            {"id": 6, "item": "Defined take profit target", "category": "Exit"},
            {"id": 7, "item": "Checked economic calendar", "category": "Fundamentals"},
            {"id": 8, "item": "Risk is less than 2% of account", "category": "Risk Management"}
        ]
    }

# =============================================================================
# CHART ANALYSIS ENDPOINTS
# =============================================================================

@app.post("/analyze-chart")
async def analyze_chart(
    file: UploadFile = File(...),
    question: Optional[str] = Form(None),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Upload chart image and get AI analysis"""
    try:
        # Read image file
        contents = await file.read()
        if len(contents) > 5 * 1024 * 1024:  # 5MB limit
            raise HTTPException(status_code=400, detail="Image too large (max 5MB)")
        
        # Convert to base64
        image_base64 = base64.b64encode(contents).decode('utf-8')
        
        # Determine MIME type
        mime_type = file.content_type or "image/jpeg"
        
        # Prepare prompt
        default_question = question or "Analyze this trading chart. Identify key levels, trends, and potential trade setups."
        
        messages = [
            {
                "role": "system",
                "content": "You are an expert forex trading analyst. Analyze trading charts and provide clear, actionable insights."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": default_question},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}
                    }
                ]
            }
        ]
        
        # Call AI
        analysis = await call_openrouter(messages)
        
        return {
            "analysis": analysis,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chart analysis error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze chart")

# =============================================================================
# PERFORMANCE ANALYSIS ENDPOINTS
# =============================================================================

@app.post("/performance/analyze")
async def analyze_performance(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Upload trading history for AI analysis"""
    try:
        # Check subscription limits
        sub_status = await check_subscription_status(current_user["id"])
        
        if not sub_status["can_create_analysis"]:
            raise HTTPException(
                status_code=403,
                detail="Analysis limit reached. Please upgrade to continue."
            )
        
        # Read file contents
        contents = await file.read()
        content_str = contents.decode('utf-8', errors='ignore')
        
        # Limit content length
        if len(content_str) > 50000:
            content_str = content_str[:50000] + "..."
        
        messages = [
            {
                "role": "system",
                "content": """You are an expert trading performance analyst. Analyze the provided trading history and provide:
1. Trader type classification (scalper, day trader, swing trader, position trader)
2. Performance score (0-100)
3. Risk appetite assessment (conservative, moderate, aggressive)
4. Key strengths identified
5. Areas for improvement
6. Specific actionable recommendations

Format your response as JSON with these keys: trader_type, performance_score, risk_appetite, strengths, weaknesses, recommendations"""
            },
            {
                "role": "user",
                "content": f"Analyze this trading history:\n\n{content_str}"
            }
        ]
        
        # Call AI
        analysis_text = await call_openrouter(messages)
        
        # Try to parse JSON response
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            if json_match:
                analysis_json = json.loads(json_match.group())
            else:
                analysis_json = {"raw_analysis": analysis_text}
        except json.JSONDecodeError:
            analysis_json = {"raw_analysis": analysis_text}
        
        # Save to database
        async with db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO performance_analyses (user_id, file_name, analysis_result, trader_type, performance_score, risk_appetite, recommendations)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
                current_user["id"],
                file.filename,
                analysis_text,
                analysis_json.get("trader_type", "Unknown"),
                analysis_json.get("performance_score", 0),
                analysis_json.get("risk_appetite", "Unknown"),
                json.dumps(analysis_json.get("recommendations", []))
            )
        
        return {
            "analysis": analysis_json,
            "raw_text": analysis_text,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Performance analysis error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze performance")

@app.get("/performance/history")
async def get_performance_history(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get past performance analyses"""
    try:
        async with db_pool.acquire() as conn:
            analyses = await conn.fetch("""
                SELECT id, file_name, analysis_result, trader_type, performance_score, risk_appetite, created_at
                FROM performance_analyses
                WHERE user_id = $1
                ORDER BY created_at DESC
            """, current_user["id"])
            
            return {
                "analyses": [dict(a) for a in analyses]
            }
    except Exception as e:
        logger.error(f"Get performance history error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch history")

# =============================================================================
# AI MENTOR ENDPOINTS
# =============================================================================

@app.get("/mentor-chat")
async def mentor_chat(
    message: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Chat with AI trading mentor"""
    try:
        messages = [
            {
                "role": "system",
                "content": """You are Pipways AI Mentor, an expert forex trading coach. You provide:
- Clear, actionable trading advice
- Educational explanations of trading concepts
- Risk management guidance
- Psychological support for traders
- Honest assessments (you don't promise guaranteed profits)

Be encouraging but realistic. Focus on education and risk management."""
            },
            {
                "role": "user",
                "content": message
            }
        ]
        
        response = await call_openrouter(messages)
        
        return {
            "response": response,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Mentor chat error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get mentor response")

# =============================================================================
# COURSES ENDPOINTS
# =============================================================================

@app.get("/courses", response_model=List[CourseResponse])
async def get_courses(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get all available courses"""
    try:
        async with db_pool.acquire() as conn:
            courses = await conn.fetch("""
                SELECT c.id, c.title, c.description, c.level, c.thumbnail_url, c.lessons, c.created_at,
                       uc.progress_percentage, uc.completed_lessons, uc.certificate_issued
                FROM courses c
                LEFT JOIN user_courses uc ON c.id = uc.course_id AND uc.user_id = $1
                ORDER BY c.created_at DESC
            """, current_user["id"])
            
            result = []
            for course in courses:
                course_dict = dict(course)
                course_dict["enrolled"] = course["progress_percentage"] is not None
                result.append(course_dict)
            
            return result
    except Exception as e:
        logger.error(f"Get courses error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch courses")

@app.get("/courses/{course_id}")
async def get_course(course_id: int, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get specific course details"""
    try:
        async with db_pool.acquire() as conn:
            course = await conn.fetchrow("""
                SELECT c.*, uc.progress_percentage, uc.completed_lessons, uc.quiz_score, uc.certificate_issued
                FROM courses c
                LEFT JOIN user_courses uc ON c.id = uc.course_id AND uc.user_id = $1
                WHERE c.id = $2
            """, current_user["id"], course_id)
            
            if not course:
                raise HTTPException(status_code=404, detail="Course not found")
            
            return dict(course)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get course error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch course")

@app.post("/courses/{course_id}/enroll")
async def enroll_course(course_id: int, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Enroll in a course"""
    try:
        async with db_pool.acquire() as conn:
            # Check if already enrolled
            existing = await conn.fetchval("""
                SELECT id FROM user_courses WHERE user_id = $1 AND course_id = $2
            """, current_user["id"], course_id)
            
            if existing:
                raise HTTPException(status_code=400, detail="Already enrolled in this course")
            
            # Check if course exists
            course = await conn.fetchval("SELECT id FROM courses WHERE id = $1", course_id)
            if not course:
                raise HTTPException(status_code=404, detail="Course not found")
            
            # Enroll user
            await conn.execute("""
                INSERT INTO user_courses (user_id, course_id, progress_percentage, completed_lessons)
                VALUES ($1, $2, 0, '{}')
            """, current_user["id"], course_id)
            
            return {"message": "Successfully enrolled", "course_id": course_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Enroll course error: {e}")
        raise HTTPException(status_code=500, detail="Failed to enroll")

@app.post("/courses/{course_id}/progress")
async def update_progress(
    course_id: int,
    progress: ProgressUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Update course progress"""
    try:
        async with db_pool.acquire() as conn:
            # Get current progress
            enrollment = await conn.fetchrow("""
                SELECT completed_lessons FROM user_courses WHERE user_id = $1 AND course_id = $2
            """, current_user["id"], course_id)
            
            if not enrollment:
                raise HTTPException(status_code=404, detail="Not enrolled in this course")
            
            completed_lessons = list(enrollment["completed_lessons"] or [])
            
            if progress.completed and progress.lesson_id not in completed_lessons:
                completed_lessons.append(progress.lesson_id)
            elif not progress.completed and progress.lesson_id in completed_lessons:
                completed_lessons.remove(progress.lesson_id)
            
            # Get total lessons
            total_lessons = await conn.fetchval("""
                SELECT jsonb_array_length(lessons) FROM courses WHERE id = $1
            """, course_id)
            
            progress_percentage = int((len(completed_lessons) / total_lessons) * 100) if total_lessons > 0 else 0
            
            # Update
            await conn.execute("""
                UPDATE user_courses
                SET completed_lessons = $1, progress_percentage = $2, completed_at = CASE WHEN $3 = 100 THEN NOW() ELSE completed_at END
                WHERE user_id = $4 AND course_id = $5
            """, completed_lessons, progress_percentage, progress_percentage, current_user["id"], course_id)
            
            return {
                "progress_percentage": progress_percentage,
                "completed_lessons": completed_lessons
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update progress error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update progress")

@app.post("/courses/{course_id}/quiz")
async def submit_quiz(
    course_id: int,
    quiz: QuizSubmit,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Submit quiz answers"""
    try:
        async with db_pool.acquire() as conn:
            # Get quiz questions
            questions = await conn.fetchval("""
                SELECT quiz_questions FROM courses WHERE id = $1
            """, course_id)
            
            if not questions:
                raise HTTPException(status_code=404, detail="No quiz found for this course")
            
            questions = json.loads(questions) if isinstance(questions, str) else questions
            
            # Calculate score
            correct = 0
            for q in questions:
                q_id = q.get("id") or questions.index(q) + 1
                if quiz.answers.get(q_id) == q.get("correct"):
                    correct += 1
            
            score = int((correct / len(questions)) * 100) if questions else 0
            
            # Get passing score
            passing_score = await conn.fetchval("""
                SELECT passing_score FROM courses WHERE id = $1
            """, course_id) or 70
            
            passed = score >= passing_score
            
            # Update quiz score and certificate
            await conn.execute("""
                UPDATE user_courses
                SET quiz_score = $1, certificate_issued = $2
                WHERE user_id = $3 AND course_id = $4
            """, score, passed, current_user["id"], course_id)
            
            return {
                "score": score,
                "passed": passed,
                "passing_score": passing_score,
                "certificate_issued": passed
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Submit quiz error: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit quiz")

# =============================================================================
# WEBINARS ENDPOINTS
# =============================================================================

@app.get("/webinars", response_model=List[WebinarResponse])
async def get_webinars(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get all webinars"""
    try:
        async with db_pool.acquire() as conn:
            webinars = await conn.fetch("""
                SELECT w.*, 
                       EXISTS(SELECT 1 FROM webinar_registrations WHERE webinar_id = w.id AND user_id = $1) as registered
                FROM webinars w
                ORDER BY w.scheduled_at DESC
            """, current_user["id"])
            
            return [dict(w) for w in webinars]
    except Exception as e:
        logger.error(f"Get webinars error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch webinars")

@app.post("/webinars/{webinar_id}/register")
async def register_webinar(webinar_id: int, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Register for a webinar"""
    try:
        async with db_pool.acquire() as conn:
            # Check if already registered
            existing = await conn.fetchval("""
                SELECT id FROM webinar_registrations WHERE webinar_id = $1 AND user_id = $2
            """, webinar_id, current_user["id"])
            
            if existing:
                raise HTTPException(status_code=400, detail="Already registered for this webinar")
            
            # Check if webinar exists
            webinar = await conn.fetchval("SELECT id FROM webinars WHERE id = $1", webinar_id)
            if not webinar:
                raise HTTPException(status_code=404, detail="Webinar not found")
            
            # Register
            await conn.execute("""
                INSERT INTO webinar_registrations (webinar_id, user_id)
                VALUES ($1, $2)
            """, webinar_id, current_user["id"])
            
            # Get zoom link
            zoom_url = await conn.fetchval("""
                SELECT zoom_join_url FROM webinars WHERE id = $1
            """, webinar_id)
            
            return {
                "message": "Successfully registered",
                "webinar_id": webinar_id,
                "zoom_join_url": zoom_url
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Register webinar error: {e}")
        raise HTTPException(status_code=500, detail="Failed to register")

# =============================================================================
# BLOG ENDPOINTS
# =============================================================================

@app.get("/blog/posts")
async def get_blog_posts(category: Optional[str] = None, limit: int = 10):
    """Get published blog posts"""
    try:
        async with db_pool.acquire() as conn:
            if category:
                posts = await conn.fetch("""
                    SELECT id, title, slug, excerpt, category, tags, featured_image, created_at
                    FROM blog_posts
                    WHERE published = TRUE AND category = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                """, category, limit)
            else:
                posts = await conn.fetch("""
                    SELECT id, title, slug, excerpt, category, tags, featured_image, created_at
                    FROM blog_posts
                    WHERE published = TRUE
                    ORDER BY created_at DESC
                    LIMIT $1
                """, limit)
            
            return {"posts": [dict(p) for p in posts]}
    except Exception as e:
        logger.error(f"Get blog posts error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch posts")

@app.get("/blog/posts/{slug}")
async def get_blog_post(slug: str):
    """Get specific blog post"""
    try:
        async with db_pool.acquire() as conn:
            post = await conn.fetchrow("""
                SELECT * FROM blog_posts WHERE slug = $1 AND published = TRUE
            """, slug)
            
            if not post:
                raise HTTPException(status_code=404, detail="Post not found")
            
            # Increment view count
            await conn.execute("""
                UPDATE blog_posts SET view_count = view_count + 1 WHERE id = $1
            """, post["id"])
            
            return dict(post)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get blog post error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch post")

# =============================================================================
# SUBSCRIPTION ENDPOINTS
# =============================================================================

@app.get("/subscription/status")
async def get_subscription_status(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get current subscription status"""
    try:
        status = await check_subscription_status(current_user["id"])
        return status
    except Exception as e:
        logger.error(f"Get subscription status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch status")

@app.post("/subscription/initiate")
async def initiate_payment(
    payment: PaymentInitiate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Initiate Paystack payment"""
    try:
        # Pricing
        prices = {"monthly": 19.99, "yearly": 199.99}
        amount = prices.get(payment.plan, 19.99)
        
        if not PAYSTACK_SECRET_KEY:
            # Development mode - simulate payment
            return {
                "authorization_url": f"/payment/simulate?plan={payment.plan}",
                "reference": f"sim_{current_user['id']}_{int(datetime.utcnow().timestamp())}",
                "amount": amount
            }
        
        # Call Paystack API
        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "email": current_user["email"],
            "amount": int(amount * 100),  # Paystack uses kobo/cents
            "reference": f"pipways_{payment.plan}_{current_user['id']}_{int(datetime.utcnow().timestamp())}",
            "callback_url": f"{FRONTEND_URL or 'https://pipways.com'}/payment/verify",
            "metadata": {
                "user_id": current_user["id"],
                "plan": payment.plan
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.paystack.co/transaction/initialize",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status"):
                return {
                    "authorization_url": data["data"]["authorization_url"],
                    "reference": data["data"]["reference"],
                    "amount": amount
                }
            else:
                raise HTTPException(status_code=400, detail="Payment initialization failed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Initiate payment error: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate payment")

@app.post("/subscription/verify")
async def verify_payment(
    reference: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Verify Paystack payment"""
    try:
        if reference.startswith("sim_"):
            # Development mode - simulate verification
            plan = "monthly" if "monthly" in reference else "yearly"
            subscription_ends = datetime.utcnow() + timedelta(days=30 if plan == "monthly" else 365)
            
            async with db_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE users
                    SET subscription_status = 'active', subscription_ends_at = $1
                    WHERE id = $2
                """, subscription_ends, current_user["id"])
            
            return {
                "status": "success",
                "message": "Payment verified (simulated)",
                "subscription_ends_at": subscription_ends.isoformat()
            }
        
        if not PAYSTACK_SECRET_KEY:
            raise HTTPException(status_code=400, detail="Payment verification not available")
        
        # Verify with Paystack
        headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.paystack.co/transaction/verify/{reference}",
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") and data["data"]["status"] == "success":
                metadata = data["data"].get("metadata", {})
                plan = metadata.get("plan", "monthly")
                subscription_ends = datetime.utcnow() + timedelta(days=30 if plan == "monthly" else 365)
                
                # Update user subscription
                async with db_pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE users
                        SET subscription_status = 'active', subscription_ends_at = $1
                        WHERE id = $2
                    """, subscription_ends, current_user["id"])
                    
                    # Record payment
                    await conn.execute("""
                        INSERT INTO payments (user_id, paystack_reference, amount, status, paid_at)
                        VALUES ($1, $2, $3, 'success', NOW())
                    """, current_user["id"], reference, data["data"]["amount"] / 100)
                
                return {
                    "status": "success",
                    "message": "Payment verified",
                    "subscription_ends_at": subscription_ends.isoformat()
                }
            else:
                raise HTTPException(status_code=400, detail="Payment verification failed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verify payment error: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify payment")

# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================

@app.get("/admin/stats")
async def get_admin_stats(admin: Dict[str, Any] = Depends(get_admin_user)):
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
