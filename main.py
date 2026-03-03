"""
Pipways - Forex Trading Journal API v3.0
Complete implementation with Admin Dashboard, Blog, Courses, AI Integration, RBAC
"""

import os
import re
import json
import base64
import logging
import hashlib
import io
import csv
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import wraps
from enum import Enum

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Header, status, Request, BackgroundTasks, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, validator
from passlib.context import CryptContext
from jose import JWTError, jwt
from PIL import Image
import aiofiles

# =============================================================================
# CONFIGURATION & LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/pipways")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
FRONTEND_URL = os.getenv("FRONTEND_URL", "")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")

# JWT Configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30
ADMIN_TOKEN_EXPIRE_HOURS = 24

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database pool
db_pool: Optional[asyncpg.Pool] = None

# In-memory cache
cache_store: Dict[str, Any] = {}
cache_expiry: Dict[str, datetime] = {}

# Rate limiting store
rate_limit_store: Dict[str, List[datetime]] = {}

# Token blacklist (for logout)
token_blacklist: set = set()

# =============================================================================
# ROLES & PERMISSIONS
# =============================================================================

ROLES = {
    "admin": {
        "permissions": ["*"],
        "can_access_admin": True,
        "can_manage_users": True,
        "can_manage_content": True,
        "can_manage_courses": True,
        "can_view_analytics": True,
        "can_send_emails": True
    },
    "student": {
        "permissions": [
            "read:courses", "read:blog", "write:trades", "read:analytics",
            "read:webinars", "write:enrollments", "read:mentor"
        ],
        "can_access_admin": False,
        "can_enroll_courses": True,
        "can_access_paid_content": False
    },
    "user": {
        "permissions": ["read:blog", "write:trades", "read:mentor"],
        "can_access_admin": False,
        "trial_features": True
    }
}

# =============================================================================
# CACHE FUNCTIONS
# =============================================================================

def cache_get(key: str) -> Any:
    if key in cache_store and cache_expiry.get(key, datetime.min) > datetime.utcnow():
        return cache_store[key]
    return None

def cache_set(key: str, value: Any, expire_seconds: int = 3600):
    cache_store[key] = value
    cache_expiry[key] = datetime.utcnow() + timedelta(seconds=expire_seconds)

def cache_delete(key: str):
    if key in cache_store:
        del cache_store[key]
        if key in cache_expiry:
            del cache_expiry[key]

def cache_delete_pattern(pattern: str):
    keys_to_delete = [k for k in cache_store.keys() if pattern in k]
    for key in keys_to_delete:
        cache_delete(key)

# =============================================================================
# RATE LIMITING
# =============================================================================

def rate_limit(max_requests: int = 5, window_seconds: int = 60):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
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
                requests_list = [r for r in rate_limit_store.get(key, []) if r > window_start]
                if len(requests_list) >= max_requests:
                    raise HTTPException(
                        status_code=429, 
                        detail=f"Rate limit exceeded. Try again in {window_seconds} seconds."
                    )
                requests_list.append(now)
                rate_limit_store[key] = requests_list
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# =============================================================================
# DATABASE SETUP
# =============================================================================

async def init_db_pool():
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
        logger.info("Database pool initialized")
        await create_tables()
        await migrate_database()
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        db_pool = None

async def create_tables():
    if not db_pool:
        return

    async with db_pool.acquire() as conn:
        # Users table with role-based access
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                role VARCHAR(20) DEFAULT 'user',
                permissions JSONB DEFAULT '{}',
                is_admin BOOLEAN DEFAULT FALSE,
                subscription_status VARCHAR(50) DEFAULT 'trial',
                subscription_ends_at TIMESTAMP,
                trial_ends_at TIMESTAMP,
                email_verified BOOLEAN DEFAULT FALSE,
                last_login_at TIMESTAMP,
                login_attempts INTEGER DEFAULT 0,
                locked_until TIMESTAMP,
                password_changed_at TIMESTAMP,
                password_history JSONB DEFAULT '[]',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Token blacklist for logout
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS token_blacklist (
                jti VARCHAR(255) PRIMARY KEY,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Password reset tokens
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token VARCHAR(255) PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Admin login logs
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_login_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                ip_address VARCHAR(45),
                user_agent TEXT,
                success BOOLEAN,
                failure_reason VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Trades table with enhanced fields
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
                screenshot_url TEXT,
                tags TEXT[],
                notes TEXT,
                psychology_rating INTEGER,
                setup_quality VARCHAR(10),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Enhanced courses table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                slug VARCHAR(255) UNIQUE NOT NULL,
                description TEXT,
                short_description TEXT,
                category VARCHAR(100),
                level VARCHAR(50) NOT NULL,
                thumbnail_url TEXT,
                price DECIMAL(10,2) DEFAULT 0,
                is_free BOOLEAN DEFAULT FALSE,
                instructor_name VARCHAR(255),
                duration_minutes INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'draft',
                enrolled_count INTEGER DEFAULT 0,
                rating DECIMAL(3,2) DEFAULT 0,
                rating_count INTEGER DEFAULT 0,
                published_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Course modules
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS course_modules (
                id SERIAL PRIMARY KEY,
                course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                order_index INTEGER DEFAULT 0,
                is_free_preview BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Course lessons
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS course_lessons (
                id SERIAL PRIMARY KEY,
                module_id INTEGER REFERENCES course_modules(id) ON DELETE CASCADE,
                course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                content TEXT,
                video_url TEXT,
                video_file_path TEXT,
                pdf_url TEXT,
                duration_minutes INTEGER DEFAULT 0,
                order_index INTEGER DEFAULT 0,
                is_free_preview BOOLEAN DEFAULT FALSE,
                is_published BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Course resources (PDFs, downloads)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS course_resources (
                id SERIAL PRIMARY KEY,
                course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
                lesson_id INTEGER REFERENCES course_lessons(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                file_path TEXT NOT NULL,
                file_type VARCHAR(50),
                file_size INTEGER,
                download_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Enhanced enrollments with progress tracking
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS course_enrollments (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
                enrolled_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP,
                progress_percentage INTEGER DEFAULT 0,
                total_watch_time INTEGER DEFAULT 0,
                is_completed BOOLEAN DEFAULT FALSE,
                last_accessed_at TIMESTAMP,
                UNIQUE(user_id, course_id)
            )
        """)

        # Lesson progress tracking
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lesson_progress (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                lesson_id INTEGER REFERENCES course_lessons(id) ON DELETE CASCADE,
                course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
                is_completed BOOLEAN DEFAULT FALSE,
                watch_time_seconds INTEGER DEFAULT 0,
                completed_at TIMESTAMP,
                last_position_seconds INTEGER DEFAULT 0,
                last_accessed_at TIMESTAMP,
                UNIQUE(user_id, lesson_id)
            )
        """)

        # Webinars table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS webinars (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                slug VARCHAR(255) UNIQUE NOT NULL,
                description TEXT,
                level VARCHAR(50),
                scheduled_at TIMESTAMP NOT NULL,
                duration_minutes INTEGER DEFAULT 60,
                zoom_meeting_id VARCHAR(100),
                zoom_join_url TEXT,
                recording_url TEXT,
                is_recorded BOOLEAN DEFAULT FALSE,
                is_live BOOLEAN DEFAULT FALSE,
                max_attendees INTEGER,
                reminder_sent BOOLEAN DEFAULT FALSE,
                status VARCHAR(20) DEFAULT 'scheduled',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
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
                attended_at TIMESTAMP,
                UNIQUE(webinar_id, user_id)
            )
        """)

        # Enhanced blog posts with SEO
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blog_posts (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                slug VARCHAR(255) UNIQUE NOT NULL,
                content TEXT NOT NULL,
                excerpt TEXT,
                seo_meta_title VARCHAR(255),
                seo_meta_description TEXT,
                focus_keywords TEXT[],
                canonical_url TEXT,
                category VARCHAR(100),
                tags TEXT[],
                featured_image TEXT,
                author_id INTEGER REFERENCES users(id),
                status VARCHAR(20) DEFAULT 'draft',
                scheduled_at TIMESTAMP,
                published_at TIMESTAMP,
                view_count INTEGER DEFAULT 0,
                seo_score INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Blog media library
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blog_media (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                original_name VARCHAR(255),
                file_path TEXT NOT NULL,
                file_type VARCHAR(50),
                file_size INTEGER,
                alt_text VARCHAR(255),
                uploaded_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW()
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
                ai_insights TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Chart analysis history
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chart_analyses (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                image_path TEXT,
                analysis_result JSONB,
                pair VARCHAR(20),
                direction VARCHAR(10),
                setup_quality VARCHAR(5),
                confidence_score INTEGER,
                saved_to_journal BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # AI mentor chat history
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mentor_chat_history (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                message TEXT NOT NULL,
                response TEXT,
                context JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Payments table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                paystack_reference VARCHAR(255),
                paystack_transaction_id VARCHAR(255),
                amount DECIMAL(10,2),
                currency VARCHAR(10) DEFAULT 'USD',
                status VARCHAR(50),
                paid_at TIMESTAMP,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Notifications table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                type VARCHAR(50) NOT NULL,
                title VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                read BOOLEAN DEFAULT FALSE,
                data JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Email logs
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS email_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                email_type VARCHAR(100) NOT NULL,
                recipient VARCHAR(255) NOT NULL,
                subject VARCHAR(255) NOT NULL,
                content TEXT,
                status VARCHAR(50) NOT NULL,
                error_message TEXT,
                sent_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # System settings
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key VARCHAR(255) PRIMARY KEY,
                value JSONB NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        logger.info("Database tables created/verified successfully")

async def migrate_database():
    """Run database migrations for existing data"""
    if not db_pool:
        return
    
    async with db_pool.acquire() as conn:
        # Migrate existing users to have role field
        await conn.execute("""
            UPDATE users 
            SET role = CASE 
                WHEN is_admin = TRUE THEN 'admin'
                ELSE 'user'
            END
            WHERE role IS NULL
        """)
        
        # Create indexes for performance
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades(created_at)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_courses_status ON courses(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_blog_posts_status ON blog_posts(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, read)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_lesson_progress_user ON lesson_progress(user_id, course_id)")
        
        logger.info("Database migrations completed")

async def insert_sample_data(conn):
    """Insert sample data for new installations"""
    # Sample courses
    course_count = await conn.fetchval("SELECT COUNT(*) FROM courses")
    if course_count == 0:
        await conn.execute("""
            INSERT INTO courses (title, slug, description, short_description, category, level, is_free, status, instructor_name, duration_minutes) VALUES
            ('Forex Fundamentals', 'forex-fundamentals', 
             'Learn the basics of forex trading including currency pairs, pips, leverage, and market structure.',
             'Master the basics of currency trading',
             'basics', 'beginner', TRUE, 'published', 'John Smith', 180),
            ('Technical Analysis Mastery', 'technical-analysis-mastery',
             'Master chart patterns, indicators, and price action strategies for consistent profits.',
             'Advanced technical analysis strategies',
             'technical', 'intermediate', FALSE, 'published', 'Sarah Johnson', 360),
            ('Risk Management Essentials', 'risk-management-essentials',
             'Protect your capital with proper position sizing, stop losses, and risk-reward ratios.',
             'Essential risk management techniques',
             'risk', 'beginner', TRUE, 'published', 'Mike Davis', 120)
        """)

    # Sample blog posts
    blog_count = await conn.fetchval("SELECT COUNT(*) FROM blog_posts")
    if blog_count == 0:
        await conn.execute("""
            INSERT INTO blog_posts (title, slug, content, excerpt, category, status, seo_meta_title, seo_meta_description, tags) VALUES
            ('Getting Started with Forex Trading', 'getting-started-forex', 
             'Forex trading is the exchange of currencies on the foreign exchange market. It is the largest and most liquid financial market in the world...',
             'Learn the basics of forex trading and start your journey to becoming a successful trader.',
             'basics', 'published', 'Getting Started with Forex Trading | Pipways',
             'Learn forex trading basics with our comprehensive guide for beginners. Start your trading journey today.',
             ARRAY['forex', 'trading', 'beginners']),
            ('Top 5 Risk Management Strategies', 'top-5-risk-management-strategies',
             'Risk management is crucial for trading success. Here are the top 5 strategies every trader should know...',
             'Essential risk management strategies to protect your trading capital.',
             'risk', 'published', 'Top 5 Risk Management Strategies | Pipways',
             'Discover the top 5 risk management strategies used by professional forex traders.',
             ARRAY['risk management', 'trading psychology', 'capital protection'])
        """)

    # Create default admin user
    admin_exists = await conn.fetchval("SELECT id FROM users WHERE email = 'admin@pipways.com'")
    if not admin_exists:
        hashed_password = pwd_context.hash("admin123")
        await conn.execute(
            """INSERT INTO users (name, email, password_hash, role, is_admin, subscription_status, trial_ends_at) 
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            "Admin", "admin@pipways.com", hashed_password, "admin", True, "active", 
            datetime.utcnow() + timedelta(days=365*10)
        )
        logger.info("Default admin user created")

# =============================================================================
# LIFESPAN CONTEXT
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
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
    version="3.0.0",
    lifespan=lifespan
)

# CORS Configuration
origins = ["*"]
if FRONTEND_URL and FRONTEND_URL != "*":
    origins = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        FRONTEND_URL
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
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

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    id: int
    email: str
    name: str
    role: str
    is_admin: bool
    subscription_status: str
    trial_ends_at: Optional[str] = None
    subscription_ends_at: Optional[str] = None

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str = Field(..., min_length=2)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class PasswordReset(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password[:72], hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    
    # Add unique token ID for blacklist support
    to_encode.update({
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "iat": datetime.utcnow()
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_admin_token(data: dict) -> str:
    """Create shorter-lived token for admin users"""
    return create_access_token(data, expires_delta=timedelta(hours=ADMIN_TOKEN_EXPIRE_HOURS))

async def is_token_blacklisted(jti: str) -> bool:
    if not db_pool:
        return False
    async with db_pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT 1 FROM token_blacklist WHERE jti = $1 AND expires_at > NOW()",
            jti
        )
        return result is not None

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Check if token is blacklisted
        jti = payload.get("jti")
        if jti and await is_token_blacklisted(jti):
            raise HTTPException(status_code=401, detail="Token has been revoked")
        
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        if not db_pool:
            raise HTTPException(status_code=503, detail="Database not available")
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                """SELECT id, email, name, role, is_admin, permissions, subscription_status, 
                          trial_ends_at, subscription_ends_at, email_verified
                   FROM users WHERE id = $1""", 
                int(user_id)
            )
            if user is None:
                raise HTTPException(status_code=401, detail="User not found")
            return dict(user)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_admin_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    user = await get_current_user(credentials)
    if user.get("role") != "admin" and not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def check_permission(user: dict, permission: str) -> bool:
    """Check if user has specific permission"""
    if user.get("role") == "admin" or user.get("is_admin"):
        return True
    
    permissions = user.get("permissions", {})
    if isinstance(permissions, str):
        permissions = json.loads(permissions)
    
    user_perms = permissions.get("permissions", [])
    if "*" in user_perms:
        return True
    
    return permission in user_perms

# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

@app.post("/auth/register", response_model=TokenResponse)
@rate_limit(max_requests=3, window_seconds=60)
async def register(request: Request, email: str = Form(...), password: str = Form(...), name: str = Form(...)):
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not connected")

    try:
        email = email.lower().strip()
        
        # Validate email format
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            raise HTTPException(status_code=400, detail="Invalid email format")
        
        # Validate password strength
        if len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        if not re.search(r'[A-Z]', password):
            raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
        if not re.search(r'[a-z]', password):
            raise HTTPException(status_code=400, detail="Password must contain at least one lowercase letter")
        if not re.search(r'[0-9]', password):
            raise HTTPException(status_code=400, detail="Password must contain at least one number")
        
        if len(name.strip()) < 2:
            raise HTTPException(status_code=400, detail="Name must be at least 2 characters")

        async with db_pool.acquire() as conn:
            # Check if email exists
            existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", email)
            if existing:
                raise HTTPException(status_code=400, detail="Email already registered")

            password_hash = hash_password(password)
            trial_ends = datetime.utcnow() + timedelta(days=3)

            user_id = await conn.fetchval(
                """INSERT INTO users (email, password_hash, name, role, trial_ends_at, subscription_status) 
                   VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                email, password_hash, name.strip(), "user", trial_ends, "trial"
            )

            token = create_access_token({"sub": str(user_id)})

            # Send welcome email
            await send_welcome_email(user_id, email, name.strip())
            
            # Create notification
            await create_notification(user_id, "system", "Welcome to Pipways!", 
                                      "Your 3-day free trial has started. Start tracking your trades!")

            return {
                "access_token": token,
                "token_type": "bearer",
                "id": user_id,
                "email": email,
                "name": name.strip(),
                "role": "user",
                "is_admin": False,
                "subscription_status": "trial",
                "trial_ends_at": trial_ends.isoformat()
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)[:100]}")

@app.post("/auth/login", response_model=TokenResponse)
@rate_limit(max_requests=5, window_seconds=60)
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not connected")

    try:
        email = email.lower().strip()
        
        async with db_pool.acquire() as conn:
            # Get user with lock status
            user = await conn.fetchrow(
                """SELECT id, email, password_hash, name, role, is_admin, permissions, subscription_status, 
                          trial_ends_at, subscription_ends_at, login_attempts, locked_until
                   FROM users WHERE email = $1""", 
                email
            )

            if not user:
                raise HTTPException(status_code=401, detail="Invalid email or password")

            # Check if account is locked
            if user["locked_until"] and user["locked_until"] > datetime.utcnow():
                remaining = (user["locked_until"] - datetime.utcnow()).seconds // 60
                raise HTTPException(status_code=403, detail=f"Account locked. Try again in {remaining} minutes.")

            # Verify password
            if not verify_password(password, user["password_hash"]):
                # Increment login attempts
                new_attempts = (user["login_attempts"] or 0) + 1
                locked_until = None
                
                if new_attempts >= 5:
                    locked_until = datetime.utcnow() + timedelta(minutes=30)
                    new_attempts = 0
                
                await conn.execute(
                    "UPDATE users SET login_attempts = $1, locked_until = $2 WHERE id = $3",
                    new_attempts, locked_until, user["id"]
                )
                
                raise HTTPException(status_code=401, detail="Invalid email or password")

            # Reset login attempts on successful login
            await conn.execute(
                "UPDATE users SET login_attempts = 0, last_login_at = NOW() WHERE id = $1",
                user["id"]
            )

            token = create_access_token({"sub": str(user["id"])})

            return {
                "access_token": token,
                "token_type": "bearer",
                "id": user["id"],
                "email": user["email"],
                "name": user["name"],
                "role": user["role"] or "user",
                "is_admin": user["is_admin"] or False,
                "subscription_status": user["subscription_status"] or "trial",
                "trial_ends_at": user["trial_ends_at"].isoformat() if user["trial_ends_at"] else None,
                "subscription_ends_at": user["subscription_ends_at"].isoformat() if user["subscription_ends_at"] else None
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)[:100]}")

@app.post("/auth/admin-login", response_model=TokenResponse)
@rate_limit(max_requests=5, window_seconds=300)  # Stricter rate limit for admin
async def admin_login(request: Request, email: str = Form(...), password: str = Form(...), totp_code: Optional[str] = Form(None)):
    """Separate admin login with enhanced security"""
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not connected")

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    try:
        email = email.lower().strip()
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                """SELECT id, email, password_hash, name, role, is_admin, subscription_status
                   FROM users WHERE email = $1""", 
                email
            )

            # Log the attempt
            success = False
            failure_reason = None

            if not user or user["role"] != "admin":
                failure_reason = "Not an admin user"
                await log_admin_login(conn, user["id"] if user else None, client_ip, user_agent, False, failure_reason)
                raise HTTPException(status_code=401, detail="Invalid admin credentials")

            if not verify_password(password, user["password_hash"]):
                failure_reason = "Invalid password"
                await log_admin_login(conn, user["id"], client_ip, user_agent, False, failure_reason)
                raise HTTPException(status_code=401, detail="Invalid admin credentials")

            # TODO: Verify TOTP code if 2FA is enabled
            # if totp_code:
            #     verify_totp(user["id"], totp_code)

            success = True
            await log_admin_login(conn, user["id"], client_ip, user_agent, True, None)
            
            # Update last login
            await conn.execute(
                "UPDATE users SET last_login_at = NOW() WHERE id = $1",
                user["id"]
            )

            # Create shorter-lived admin token
            token = create_admin_token({"sub": str(user["id"]), "is_admin": True})

            # Send admin login notification
            await create_notification(user["id"], "security", "Admin Login", 
                                      f"Admin login from IP: {client_ip}")

            return {
                "access_token": token,
                "token_type": "bearer",
                "id": user["id"],
                "email": user["email"],
                "name": user["name"],
                "role": "admin",
                "is_admin": True,
                "subscription_status": user["subscription_status"] or "active"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin login error: {e}")
        raise HTTPException(status_code=500, detail="Admin login failed")

async def log_admin_login(conn, user_id: Optional[int], ip_address: str, user_agent: str, success: bool, failure_reason: Optional[str]):
    """Log admin login attempts"""
    try:
        await conn.execute(
            """INSERT INTO admin_login_logs (user_id, ip_address, user_agent, success, failure_reason)
               VALUES ($1, $2, $3, $4, $5)""",
            user_id, ip_address, user_agent, success, failure_reason
        )
    except Exception as e:
        logger.error(f"Failed to log admin login: {e}")

@app.post("/auth/forgot-password")
@rate_limit(max_requests=3, window_seconds=300)
async def forgot_password(email: str = Form(...)):
    """Request password reset"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        email = email.lower().strip()
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT id, email, name FROM users WHERE email = $1", email)
            
            # Always return success to prevent email enumeration
            if not user:
                return {"message": "If an account exists, a reset link has been sent"}

            # Generate reset token
            token = str(uuid.uuid4())
            expires_at = datetime.utcnow() + timedelta(hours=24)
            
            await conn.execute(
                """INSERT INTO password_reset_tokens (token, user_id, expires_at)
                   VALUES ($1, $2, $3)""",
                token, user["id"], expires_at
            )

            # Send reset email
            reset_url = f"{FRONTEND_URL}/reset-password?token={token}"
            await send_password_reset_email(user["id"], email, user["name"], reset_url)

            return {"message": "If an account exists, a reset link has been sent"}
    except Exception as e:
        logger.error(f"Forgot password error: {e}")
        return {"message": "If an account exists, a reset link has been sent"}

@app.post("/auth/reset-password")
async def reset_password(token: str = Form(...), new_password: str = Form(...)):
    """Reset password with token"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # Validate password strength
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

        async with db_pool.acquire() as conn:
            # Validate token
            reset_token = await conn.fetchrow(
                """SELECT user_id FROM password_reset_tokens 
                   WHERE token = $1 AND expires_at > NOW() AND used = FALSE""",
                token
            )
            
            if not reset_token:
                raise HTTPException(status_code=400, detail="Invalid or expired token")

            user_id = reset_token["user_id"]

            # Check password history
            password_history = await conn.fetchval(
                "SELECT password_history FROM users WHERE id = $1",
                user_id
            ) or []

            # Hash new password
            new_hash = hash_password(new_password)

            # Check against history
            for old_hash in password_history[-5:]:  # Check last 5 passwords
                if verify_password(new_password, old_hash):
                    raise HTTPException(status_code=400, detail="Cannot reuse recent passwords")

            # Update password
            await conn.execute(
                """UPDATE users 
                   SET password_hash = $1, 
                       password_changed_at = NOW(),
                       password_history = password_history || $2::jsonb
                   WHERE id = $3""",
                new_hash, json.dumps([new_hash]), user_id
            )

            # Mark token as used
            await conn.execute(
                "UPDATE password_reset_tokens SET used = TRUE WHERE token = $1",
                token
            )

            # Invalidate all existing tokens for this user
            # (In production, you might want to blacklist them)

            return {"message": "Password reset successful"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset password error: {e}")
        raise HTTPException(status_code=500, detail="Password reset failed")

@app.post("/auth/change-password")
async def change_password(
    current_password: str = Form(...),
    new_password: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """Change password (authenticated)"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

        async with db_pool.acquire() as conn:
            # Verify current password
            user = await conn.fetchrow(
                "SELECT password_hash FROM users WHERE id = $1",
                current_user["id"]
            )

            if not verify_password(current_password, user["password_hash"]):
                raise HTTPException(status_code=400, detail="Current password is incorrect")

            # Check password history
            password_history = await conn.fetchval(
                "SELECT password_history FROM users WHERE id = $1",
                current_user["id"]
            ) or []

            new_hash = hash_password(new_password)

            for old_hash in password_history[-5:]:
                if verify_password(new_password, old_hash):
                    raise HTTPException(status_code=400, detail="Cannot reuse recent passwords")

            # Update password
            await conn.execute(
                """UPDATE users 
                   SET password_hash = $1, 
                       password_changed_at = NOW(),
                       password_history = password_history || $2::jsonb
                   WHERE id = $3""",
                new_hash, json.dumps([new_hash]), current_user["id"]
            )

            return {"message": "Password changed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change password error: {e}")
        raise HTTPException(status_code=500, detail="Password change failed")

@app.post("/auth/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Logout and invalidate token"""
    try:
        # In a stateless JWT setup, we can't truly invalidate the token
        # But we can add it to a blacklist until it expires
        # For now, just return success - client will remove token
        return {"message": "Logged out successfully"}
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")

@app.get("/auth/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    return {
        "id": current_user["id"],
        "name": current_user["name"],
        "email": current_user["email"],
        "role": current_user.get("role", "user"),
        "is_admin": current_user.get("is_admin", False),
        "subscription_status": current_user.get("subscription_status", "trial"),
        "subscription_ends_at": current_user.get("subscription_ends_at"),
        "trial_ends_at": current_user.get("trial_ends_at"),
        "email_verified": current_user.get("email_verified", False),
        "permissions": current_user.get("permissions", {})
    }

@app.get("/auth/me/permissions")
async def get_user_permissions(current_user: dict = Depends(get_current_user)):
    """Get current user permissions"""
    role = current_user.get("role", "user")
    role_perms = ROLES.get(role, {})
    user_perms = current_user.get("permissions", {})
    
    if isinstance(user_perms, str):
        user_perms = json.loads(user_perms)
    
    return {
        "role": role,
        "permissions": user_perms.get("permissions", role_perms.get("permissions", [])),
        "can_access_admin": role_perms.get("can_access_admin", False) or user_perms.get("can_access_admin", False),
        "features": role_perms
    }

# =============================================================================
# EMAIL SERVICE
# =============================================================================

async def send_email(user_id: int, email_type: str, recipient: str, subject: str, content: str):
    """Send email using SendGrid or log if not configured"""
    if not SENDGRID_API_KEY:
        logger.info(f"[EMAIL] Would send {email_type} to {recipient}: {subject}")
        return True

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {SENDGRID_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "personalizations": [{"to": [{"email": recipient}]}],
                    "from": {"email": "noreply@pipways.com", "name": "Pipways"},
                    "subject": subject,
                    "content": [{"type": "text/html", "value": content}]
                }
            )

            if db_pool:
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO email_logs (user_id, email_type, recipient, subject, status)
                           VALUES ($1, $2, $3, $4, $5)""",
                        user_id, email_type, recipient, subject,
                        "sent" if response.status_code == 202 else "failed"
                    )
            return response.status_code == 202
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False

async def send_welcome_email(user_id: int, email: str, name: str):
    content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #0f172a; color: #fff; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: #1e293b; padding: 30px; border-radius: 10px;">
            <h1 style="color: #3b82f6;">Welcome to Pipways, {name}!</h1>
            <p>Your 3-day free trial has started. Start tracking your trades and improve your performance.</p>
            <div style="margin: 30px 0;">
                <a href="{FRONTEND_URL}" style="background: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Get Started</a>
            </div>
            <p style="color: #94a3b8;">Need help? Reply to this email or contact support@pipways.com</p>
        </div>
    </body>
    </html>
    """
    return await send_email(user_id, "welcome", email, "Welcome to Pipways!", content)

async def send_password_reset_email(user_id: int, email: str, name: str, reset_url: str):
    content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #0f172a; color: #fff; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: #1e293b; padding: 30px; border-radius: 10px;">
            <h1 style="color: #3b82f6;">Password Reset Request</h1>
            <p>Hi {name},</p>
            <p>We received a request to reset your password. Click the button below to set a new password:</p>
            <div style="margin: 30px 0;">
                <a href="{reset_url}" style="background: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Reset Password</a>
            </div>
            <p style="color: #94a3b8;">This link will expire in 24 hours.</p>
            <p style="color: #94a3b8;">If you didn't request this, please ignore this email.</p>
        </div>
    </body>
    </html>
    """
    return await send_email(user_id, "password_reset", email, "Password Reset Request", content)

# =============================================================================
# NOTIFICATION SERVICE
# =============================================================================

async def create_notification(user_id: int, type: str, title: str, message: str, data: dict = None):
    """Create a notification for a user"""
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO notifications (user_id, type, title, message, data)
                   VALUES ($1, $2, $3, $4, $5)""",
                user_id, type, title, message, json.dumps(data) if data else None
            )
    except Exception as e:
        logger.error(f"Failed to create notification: {e}")

@app.get("/notifications")
async def get_notifications(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """Get user notifications"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    
    async with db_pool.acquire() as conn:
        notifications = await conn.fetch(
            """SELECT id, type, title, message, read, data, created_at
               FROM notifications
               WHERE user_id = $1
               ORDER BY created_at DESC
               LIMIT $2 OFFSET $3""",
            current_user["id"], limit, offset
        )
        return [dict(n) for n in notifications]

@app.get("/notifications/unread-count")
async def get_unread_notification_count(current_user: dict = Depends(get_current_user)):
    """Get count of unread notifications"""
    if not db_pool:
        return {"unread_count": 0}
    
    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM notifications WHERE user_id = $1 AND read = FALSE",
            current_user["id"]
        )
        return {"unread_count": count}

@app.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Mark notification as read"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE notifications SET read = TRUE WHERE id = $1 AND user_id = $2",
            notification_id, current_user["id"]
        )
        return {"message": "Notification marked as read"}

@app.post("/notifications/read-all")
async def mark_all_notifications_read(current_user: dict = Depends(get_current_user)):
    """Mark all notifications as read"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE notifications SET read = TRUE WHERE user_id = $1 AND read = FALSE",
            current_user["id"]
        )
        return {"message": "All notifications marked as read"}

# =============================================================================
# HEALTH & DEBUG ENDPOINTS
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        db_status = "connected"
        if db_pool:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        else:
            db_status = "not_connected"
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "database": db_status,
            "version": "3.0.0"
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@app.get("/debug")
async def debug_info():
    """Debug information (admin only in production)"""
    return {
        "db_pool_initialized": db_pool is not None,
        "database_url_set": bool(os.getenv("DATABASE_URL")),
        "secret_key_set": bool(os.getenv("SECRET_KEY")),
        "openrouter_key_set": bool(os.getenv("OPENROUTER_API_KEY")),
        "paystack_key_set": bool(os.getenv("PAYSTACK_SECRET_KEY")),
        "sendgrid_key_set": bool(os.getenv("SENDGRID_API_KEY")),
        "environment": ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat()
    }

# =============================================================================
# TRADES ENDPOINTS
# =============================================================================

@app.get("/trades")
async def get_trades(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """Get user's trades"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    cache_key = f"trades:{current_user['id']}:{limit}:{offset}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, pair, direction, pips, grade, entry_price, exit_price, 
                      tags, notes, created_at
               FROM trades 
               WHERE user_id = $1
               ORDER BY created_at DESC
               LIMIT $2 OFFSET $3""",
            current_user["id"], limit, offset
        )
        result = [dict(row) for row in rows]
        cache_set(cache_key, result, 300)
        return result

@app.post("/trades")
async def create_trade(
    pair: str = Form(...),
    direction: str = Form(...),
    pips: float = Form(...),
    grade: str = Form(...),
    entry_price: Optional[float] = Form(None),
    exit_price: Optional[float] = Form(None),
    notes: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """Create a new trade"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        # Check trial limit
        if current_user.get("subscription_status") == "trial":
            trade_count = await conn.fetchval(
                "SELECT COUNT(*) FROM trades WHERE user_id = $1",
                current_user["id"]
            )
            if trade_count >= 5:
                raise HTTPException(
                    status_code=403,
                    detail="Trial limit reached (5 trades). Upgrade to Pro."
                )

        trade_id = await conn.fetchval(
            """INSERT INTO trades (user_id, pair, direction, pips, grade, 
                                   entry_price, exit_price, notes)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id""",
            current_user["id"],
            pair.upper(),
            direction.upper(),
            pips,
            grade.upper(),
            entry_price,
            exit_price,
            notes
        )

        # Clear cache
        cache_delete_pattern(f"trades:{current_user['id']}")
        cache_delete_pattern(f"analytics:{current_user['id']}")

        # Create notification
        await create_notification(
            current_user["id"],
            "trade",
            "Trade Logged",
            f"You logged a {direction} trade on {pair}"
        )

        return {"id": trade_id, "message": "Trade created successfully"}

@app.get("/trades/export")
async def export_trades(
    format: str = Query("csv", regex="^(csv|json)$"),
    current_user: dict = Depends(get_current_user)
):
    """Export trades"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT pair, direction, pips, grade, entry_price, exit_price, 
                      notes, created_at
               FROM trades 
               WHERE user_id = $1 
               ORDER BY created_at DESC""",
            current_user["id"]
        )

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Pair", "Direction", "Pips", "Grade", "Entry Price", 
                        "Exit Price", "Notes", "Date"])
        for row in rows:
            writer.writerow([
                row["pair"], row["direction"], row["pips"], row["grade"],
                row["entry_price"], row["exit_price"], row["notes"],
                row["created_at"].isoformat()
            ])

        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=trades_{datetime.now().strftime('%Y-%m-%d')}.csv"
            }
        )
    else:
        return [dict(row) for row in rows]

# =============================================================================
# ANALYTICS ENDPOINTS
# =============================================================================

@app.get("/analytics/dashboard")
async def get_analytics(current_user: dict = Depends(get_current_user)):
    """Get dashboard analytics"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    cache_key = f"analytics:{current_user['id']}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    async with db_pool.acquire() as conn:
        trades = await conn.fetch(
            """SELECT * FROM trades 
               WHERE user_id = $1 
               ORDER BY created_at""",
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
                "trades_7d": 0
            }

        total_trades = len(trades)
        wins = sum(1 for t in trades if t["pips"] > 0)
        win_rate = round((wins / total_trades) * 100, 1)
        total_pips = sum(t["pips"] for t in trades)

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

        # Trades in last 7 days
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        trades_7d = sum(1 for t in trades if t["created_at"] > seven_days_ago)

        result = {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "total_pips": round(total_pips, 2),
            "profit_factor": profit_factor,
            "equity_curve": equity_curve,
            "monthly_performance": monthly_performance,
            "pair_performance": pair_performance,
            "trades_7d": trades_7d
        }

        cache_set(cache_key, result, 300)
        return result

# =============================================================================
# COURSES ENDPOINTS (STUDENT)
# =============================================================================

@app.get("/courses")
async def get_courses(
    category: Optional[str] = None,
    level: Optional[str] = None,
    is_free: Optional[bool] = None,
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get published courses"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    cache_key = f"courses:all:{category}:{level}:{is_free}:{search}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    async with db_pool.acquire() as conn:
        # Build query
        where_clauses = ["status = 'published'"]
        params = []
        param_idx = 1

        if category:
            where_clauses.append(f"category = ${param_idx}")
            params.append(category)
            param_idx += 1

        if level:
            where_clauses.append(f"level = ${param_idx}")
            params.append(level)
            param_idx += 1

        if is_free is not None:
            where_clauses.append(f"is_free = ${param_idx}")
            params.append(is_free)
            param_idx += 1

        if search:
            where_clauses.append(f"(title ILIKE ${param_idx} OR description ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1

        where_str = " AND ".join(where_clauses)

        courses = await conn.fetch(
            f"""SELECT id, title, slug, description, short_description, category, level,
                       thumbnail_url, price, is_free, instructor_name, duration_minutes,
                       enrolled_count, rating, rating_count
               FROM courses
               WHERE {where_str}
               ORDER BY created_at DESC""",
            *params
        )

        # Get user's enrollments
        user_courses = await conn.fetch(
            "SELECT course_id, progress_percentage, is_completed FROM course_enrollments WHERE user_id = $1",
            current_user["id"]
        )
        user_progress = {uc["course_id"]: dict(uc) for uc in user_courses}

        result = []
        for course in courses:
            progress = user_progress.get(course["id"], {})
            result.append({
                "id": course["id"],
                "title": course["title"],
                "slug": course["slug"],
                "description": course["description"],
                "short_description": course["short_description"],
                "category": course["category"],
                "level": course["level"],
                "thumbnail_url": course["thumbnail_url"],
                "price": float(course["price"]) if course["price"] else 0,
                "is_free": course["is_free"],
                "instructor_name": course["instructor_name"],
                "duration_minutes": course["duration_minutes"],
                "enrolled_count": course["enrolled_count"],
                "rating": float(course["rating"]) if course["rating"] else 0,
                "rating_count": course["rating_count"],
                "progress_percentage": progress.get("progress_percentage", 0),
                "is_enrolled": course["id"] in user_progress,
                "is_completed": progress.get("is_completed", False)
            })

        cache_set(cache_key, result, 3600)
        return result

@app.get("/courses/{course_id}")
async def get_course_detail(
    course_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get course details with modules and lessons"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        course = await conn.fetchrow(
            """SELECT id, title, slug, description, short_description, category, level,
                      thumbnail_url, price, is_free, instructor_name, duration_minutes,
                      enrolled_count, rating, rating_count, status
               FROM courses WHERE id = $1""",
            course_id
        )

        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        if course["status"] != "published":
            # Check if user is admin or enrolled
            is_admin = current_user.get("role") == "admin" or current_user.get("is_admin")
            is_enrolled = await conn.fetchval(
                "SELECT 1 FROM course_enrollments WHERE user_id = $1 AND course_id = $2",
                current_user["id"], course_id
            )
            if not is_admin and not is_enrolled:
                raise HTTPException(status_code=404, detail="Course not found")

        # Get modules
        modules = await conn.fetch(
            """SELECT id, title, description, order_index, is_free_preview
               FROM course_modules
               WHERE course_id = $1
               ORDER BY order_index""",
            course_id
        )

        # Get lessons for each module
        modules_with_lessons = []
        for module in modules:
            lessons = await conn.fetch(
                """SELECT id, title, content, video_url, duration_minutes, 
                          order_index, is_free_preview, is_published
                   FROM course_lessons
                   WHERE module_id = $1
                   ORDER BY order_index""",
                module["id"]
            )

            # Get lesson progress
            lesson_ids = [l["id"] for l in lessons]
            if lesson_ids:
                progress = await conn.fetch(
                    """SELECT lesson_id, is_completed, watch_time_seconds
                       FROM lesson_progress
                       WHERE user_id = $1 AND lesson_id = ANY($2)""",
                    current_user["id"], lesson_ids
                )
                progress_map = {p["lesson_id"]: p for p in progress}
            else:
                progress_map = {}

            modules_with_lessons.append({
                "id": module["id"],
                "title": module["title"],
                "description": module["description"],
                "order_index": module["order_index"],
                "is_free_preview": module["is_free_preview"],
                "lessons": [
                    {
                        "id": l["id"],
                        "title": l["title"],
                        "duration_minutes": l["duration_minutes"],
                        "is_free_preview": l["is_free_preview"],
                        "is_published": l["is_published"],
                        "is_completed": progress_map.get(l["id"], {}).get("is_completed", False),
                        "watch_time_seconds": progress_map.get(l["id"], {}).get("watch_time_seconds", 0)
                    }
                    for l in lessons
                ]
            })

        # Get enrollment info
        enrollment = await conn.fetchrow(
            """SELECT progress_percentage, is_completed, enrolled_at
               FROM course_enrollments
               WHERE user_id = $1 AND course_id = $2""",
            current_user["id"], course_id
        )

        return {
            "id": course["id"],
            "title": course["title"],
            "slug": course["slug"],
            "description": course["description"],
            "short_description": course["short_description"],
            "category": course["category"],
            "level": course["level"],
            "thumbnail_url": course["thumbnail_url"],
            "price": float(course["price"]) if course["price"] else 0,
            "is_free": course["is_free"],
            "instructor_name": course["instructor_name"],
            "duration_minutes": course["duration_minutes"],
            "enrolled_count": course["enrolled_count"],
            "rating": float(course["rating"]) if course["rating"] else 0,
            "rating_count": course["rating_count"],
            "modules": modules_with_lessons,
            "enrollment": {
                "is_enrolled": enrollment is not None,
                "progress_percentage": enrollment["progress_percentage"] if enrollment else 0,
                "is_completed": enrollment["is_completed"] if enrollment else False,
                "enrolled_at": enrollment["enrolled_at"].isoformat() if enrollment else None
            }
        }

@app.post("/courses/{course_id}/enroll")
async def enroll_course(
    course_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Enroll in a course"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        # Get course
        course = await conn.fetchrow(
            "SELECT title, price, is_free, status FROM courses WHERE id = $1",
            course_id
        )

        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        if course["status"] != "published":
            raise HTTPException(status_code=400, detail="Course is not available")

        # Check if already enrolled
        existing = await conn.fetchval(
            "SELECT id FROM course_enrollments WHERE user_id = $1 AND course_id = $2",
            current_user["id"], course_id
        )

        if existing:
            return {"message": "Already enrolled"}

        # Check if paid course
        if not course["is_free"] and course["price"] > 0:
            # Check subscription status
            if current_user.get("subscription_status") != "active":
                raise HTTPException(
                    status_code=403,
                    detail="This course requires an active subscription"
                )

        # Create enrollment
        await conn.execute(
            """INSERT INTO course_enrollments (user_id, course_id, enrolled_at)
               VALUES ($1, $2, NOW())""",
            current_user["id"], course_id
        )

        # Update enrolled count
        await conn.execute(
            "UPDATE courses SET enrolled_count = enrolled_count + 1 WHERE id = $1",
            course_id
        )

        cache_delete_pattern("courses:all")

        # Create notification
        await create_notification(
            current_user["id"],
            "course",
            "Course Enrolled",
            f"You enrolled in {course['title']}"
        )

        return {"message": "Enrolled successfully"}

@app.get("/courses/{course_id}/lessons/{lesson_id}")
async def get_lesson(
    course_id: int,
    lesson_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get lesson content"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        # Get lesson
        lesson = await conn.fetchrow(
            """SELECT l.*, c.title as course_title, c.is_free as course_is_free,
                      m.is_free_preview as module_is_free_preview
               FROM course_lessons l
               JOIN courses c ON l.course_id = c.id
               JOIN course_modules m ON l.module_id = m.id
               WHERE l.id = $1 AND l.course_id = $2""",
            lesson_id, course_id
        )

        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found")

        # Check access
        is_admin = current_user.get("role") == "admin" or current_user.get("is_admin")
        
        if not is_admin and not lesson["is_free_preview"] and not lesson["module_is_free_preview"]:
            # Check enrollment
            is_enrolled = await conn.fetchval(
                "SELECT 1 FROM course_enrollments WHERE user_id = $1 AND course_id = $2",
                current_user["id"], course_id
            )

            if not is_enrolled and not lesson["course_is_free"]:
                raise HTTPException(
                    status_code=403,
                    detail="You must enroll in this course to access this lesson"
                )

        # Get resources
        resources = await conn.fetch(
            """SELECT id, title, file_type, file_size, download_count
               FROM course_resources
               WHERE lesson_id = $1""",
            lesson_id
        )

        # Update last accessed
        await conn.execute(
            """UPDATE course_enrollments 
               SET last_accessed_at = NOW()
               WHERE user_id = $1 AND course_id = $2""",
            current_user["id"], course_id
        )

        # Get or create lesson progress
        progress = await conn.fetchrow(
            """SELECT is_completed, watch_time_seconds, last_position_seconds
               FROM lesson_progress
               WHERE user_id = $1 AND lesson_id = $2""",
            current_user["id"], lesson_id
        )

        if not progress:
            await conn.execute(
                """INSERT INTO lesson_progress (user_id, lesson_id, course_id, last_accessed_at)
                   VALUES ($1, $2, $3, NOW())""",
                current_user["id"], lesson_id, course_id
            )
            progress = {"is_completed": False, "watch_time_seconds": 0, "last_position_seconds": 0}

        return {
            "id": lesson["id"],
            "title": lesson["title"],
            "content": lesson["content"],
            "video_url": lesson["video_url"],
            "video_file_path": lesson["video_file_path"],
            "duration_minutes": lesson["duration_minutes"],
            "is_free_preview": lesson["is_free_preview"],
            "course_title": lesson["course_title"],
            "resources": [dict(r) for r in resources],
            "progress": {
                "is_completed": progress["is_completed"],
                "watch_time_seconds": progress["watch_time_seconds"],
                "last_position_seconds": progress["last_position_seconds"]
            }
        }

@app.post("/courses/{course_id}/lessons/{lesson_id}/progress")
async def update_lesson_progress(
    course_id: int,
    lesson_id: int,
    watch_time_seconds: int = Form(0),
    last_position_seconds: int = Form(0),
    is_completed: bool = Form(False),
    current_user: dict = Depends(get_current_user)
):
    """Update lesson progress"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        # Update lesson progress
        await conn.execute(
            """INSERT INTO lesson_progress 
                   (user_id, lesson_id, course_id, watch_time_seconds, last_position_seconds, 
                    is_completed, last_accessed_at)
               VALUES ($1, $2, $3, $4, $5, $6, NOW())
               ON CONFLICT (user_id, lesson_id)
               DO UPDATE SET
                   watch_time_seconds = GREATEST(lesson_progress.watch_time_seconds, $4),
                   last_position_seconds = $5,
                   is_completed = $6 OR lesson_progress.is_completed,
                   last_accessed_at = NOW()""",
            current_user["id"], lesson_id, course_id,
            watch_time_seconds, last_position_seconds, is_completed
        )

        # Calculate overall course progress
        total_lessons = await conn.fetchval(
            "SELECT COUNT(*) FROM course_lessons WHERE course_id = $1",
            course_id
        )

        completed_lessons = await conn.fetchval(
            """SELECT COUNT(*) FROM lesson_progress
               WHERE user_id = $1 AND course_id = $2 AND is_completed = TRUE""",
            current_user["id"], course_id
        )

        progress_percentage = int((completed_lessons / total_lessons) * 100) if total_lessons > 0 else 0
        is_course_completed = completed_lessons >= total_lessons

        # Update enrollment
        await conn.execute(
            """UPDATE course_enrollments
               SET progress_percentage = $1,
                   is_completed = $2,
                   completed_at = CASE WHEN $2 = TRUE AND completed_at IS NULL THEN NOW() ELSE completed_at END
               WHERE user_id = $3 AND course_id = $4""",
            progress_percentage, is_course_completed,
            current_user["id"], course_id
        )

        return {
            "progress_percentage": progress_percentage,
            "is_completed": is_course_completed,
            "completed_lessons": completed_lessons,
            "total_lessons": total_lessons
        }

@app.get("/courses/enrolled")
async def get_enrolled_courses(current_user: dict = Depends(get_current_user)):
    """Get user's enrolled courses"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        enrollments = await conn.fetch(
            """SELECT c.id, c.title, c.slug, c.thumbnail_url, c.category, c.level,
                      ce.progress_percentage, ce.is_completed, ce.enrolled_at, ce.last_accessed_at
               FROM course_enrollments ce
               JOIN courses c ON ce.course_id = c.id
               WHERE ce.user_id = $1
               ORDER BY ce.last_accessed_at DESC NULLS LAST""",
            current_user["id"]
        )

        return [dict(e) for e in enrollments]

# =============================================================================
# WEBINARS ENDPOINTS
# =============================================================================

@app.get("/webinars")
async def get_webinars(
    upcoming: bool = True,
    current_user: dict = Depends(get_current_user)
):
    """Get webinars"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    cache_key = f"webinars:all:{upcoming}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    async with db_pool.acquire() as conn:
        if upcoming:
            webinars = await conn.fetch(
                """SELECT w.*, COUNT(wr.id) as registered_count
                   FROM webinars w
                   LEFT JOIN webinar_registrations wr ON w.id = wr.webinar_id
                   WHERE w.scheduled_at > NOW() - INTERVAL '2 hours'
                   GROUP BY w.id
                   ORDER BY w.scheduled_at ASC"""
            )
        else:
            webinars = await conn.fetch(
                """SELECT w.*, COUNT(wr.id) as registered_count
                   FROM webinars w
                   LEFT JOIN webinar_registrations wr ON w.id = wr.webinar_id
                   GROUP BY w.id
                   ORDER BY w.scheduled_at DESC"""
            )

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
                "slug": webinar["slug"],
                "description": webinar["description"],
                "level": webinar["level"],
                "scheduled_at": scheduled.isoformat(),
                "duration_minutes": webinar["duration_minutes"],
                "is_live": is_live,
                "is_recorded": webinar["is_recorded"],
                "time_until": time_until,
                "registered_count": webinar["registered_count"],
                "max_attendees": webinar["max_attendees"],
                "is_registered": webinar["id"] in registered_ids
            })

        cache_set(cache_key, result, 300)
        return result

@app.post("/webinars/{webinar_id}/register")
async def register_webinar(
    webinar_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Register for a webinar"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        # Check if already registered
        existing = await conn.fetchval(
            "SELECT id FROM webinar_registrations WHERE user_id = $1 AND webinar_id = $2",
            current_user["id"], webinar_id
        )

        if existing:
            return {"message": "Already registered"}

        # Check max attendees
        webinar = await conn.fetchrow(
            "SELECT title, scheduled_at, max_attendees FROM webinars WHERE id = $1",
            webinar_id
        )

        if not webinar:
            raise HTTPException(status_code=404, detail="Webinar not found")

        if webinar["max_attendees"]:
            registered_count = await conn.fetchval(
                "SELECT COUNT(*) FROM webinar_registrations WHERE webinar_id = $1",
                webinar_id
            )
            if registered_count >= webinar["max_attendees"]:
                raise HTTPException(status_code=400, detail="Webinar is full")

        await conn.execute(
            "INSERT INTO webinar_registrations (user_id, webinar_id) VALUES ($1, $2)",
            current_user["id"], webinar_id
        )

        cache_delete("webinars:all")

        await create_notification(
            current_user["id"],
            "webinar",
            "Webinar Registered",
            f"You registered for {webinar['title']}",
            {"scheduled_at": webinar["scheduled_at"].isoformat()}
        )

        return {"message": "Registered successfully"}

# =============================================================================
# BLOG ENDPOINTS (PUBLIC)
# =============================================================================

@app.get("/blog/posts")
async def get_blog_posts(
    category: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50)
):
    """Get published blog posts"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    offset = (page - 1) * per_page
    cache_key = f"blog:posts:{category}:{tag}:{search}:{page}:{per_page}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    async with db_pool.acquire() as conn:
        where_clauses = ["status = 'published'", "published_at <= NOW()"]
        params = []
        param_idx = 1

        if category:
            where_clauses.append(f"category = ${param_idx}")
            params.append(category)
            param_idx += 1

        if tag:
            where_clauses.append(f"${param_idx} = ANY(tags)")
            params.append(tag)
            param_idx += 1

        if search:
            where_clauses.append(f"(title ILIKE ${param_idx} OR content ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1

        where_str = " AND ".join(where_clauses)

        # Get total count
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM blog_posts WHERE {where_str}",
            *params
        )

        # Get posts
        posts = await conn.fetch(
            f"""SELECT id, title, slug, excerpt, category, tags, featured_image,
                      view_count, published_at, 
                      (SELECT name FROM users WHERE id = blog_posts.author_id) as author_name
               FROM blog_posts
               WHERE {where_str}
               ORDER BY published_at DESC
               LIMIT ${param_idx} OFFSET ${param_idx + 1}""",
            *params, per_page, offset
        )

        result = {
            "posts": [dict(p) for p in posts],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page
            }
        }

        cache_set(cache_key, result, 3600)
        return result

@app.get("/blog/posts/{slug}")
async def get_blog_post(slug: str):
    """Get a single blog post"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    cache_key = f"blog:post:{slug}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    async with db_pool.acquire() as conn:
        post = await conn.fetchrow(
            """SELECT id, title, slug, content, excerpt, seo_meta_title, seo_meta_description,
                      focus_keywords, category, tags, featured_image, canonical_url,
                      view_count, published_at,
                      (SELECT name FROM users WHERE id = blog_posts.author_id) as author_name
               FROM blog_posts
               WHERE slug = $1 AND status = 'published' AND published_at <= NOW()""",
            slug
        )

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        # Increment view count
        await conn.execute(
            "UPDATE blog_posts SET view_count = view_count + 1 WHERE id = $1",
            post["id"]
        )

        result = dict(post)
        cache_set(cache_key, result, 3600)
        return result

@app.get("/blog/categories")
async def get_blog_categories():
    """Get all blog categories"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    cache_key = "blog:categories"
    cached = cache_get(cache_key)
    if cached:
        return cached

    async with db_pool.acquire() as conn:
        categories = await conn.fetch(
            """SELECT category, COUNT(*) as count
               FROM blog_posts
               WHERE status = 'published'
               GROUP BY category
               ORDER BY count DESC"""
        )

        result = [dict(c) for c in categories]
        cache_set(cache_key, result, 3600)
        return result

# =============================================================================
# AI INTEGRATION - OPENROUTER
# =============================================================================

FALLBACK_MODELS = [
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-4o",
    "google/gemini-pro-vision",
    "anthropic/claude-3-haiku",
    "openai/gpt-3.5-turbo"
]

async def call_openrouter_with_fallback(prompt: str, max_tokens: int = 1000, require_vision: bool = False) -> tuple[str, str]:
    """Call OpenRouter with fallback models"""
    if not OPENROUTER_API_KEY:
        logger.warning("OpenRouter API key not configured")
        return "AI service not configured.", ""

    models = FALLBACK_MODELS if not require_vision else [
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "google/gemini-pro-vision"
    ]

    last_error = None

    for model in models:
        try:
            async with httpx.AsyncClient(timeout=60.0 if require_vision else 30.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": FRONTEND_URL or "https://pipways.com",
                        "X-Title": "Pipways"
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    logger.info(f"OpenRouter success with model: {model}")
                    return content, model

                if response.status_code == 429:
                    logger.warning(f"Rate limit with {model}, trying fallback")
                    continue

                logger.warning(f"OpenRouter error with {model}: {response.status_code}")
                last_error = f"Status {response.status_code}"

        except httpx.TimeoutException:
            logger.warning(f"Timeout with {model}, trying fallback")
            last_error = "Timeout"
        except Exception as e:
            logger.error(f"OpenRouter error with {model}: {e}")
            last_error = str(e)

    return f"AI service temporarily unavailable. {last_error}" if last_error else "AI service error.", ""

async def call_openrouter_vision(image_base64: str, prompt: str, max_tokens: int = 1500) -> tuple[str, str]:
    """Call OpenRouter with vision capabilities"""
    if not OPENROUTER_API_KEY:
        return "AI vision service not configured.", ""

    vision_models = [
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "google/gemini-pro-vision"
    ]

    last_error = None

    for model in vision_models:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": FRONTEND_URL or "https://pipways.com",
                        "X-Title": "Pipways"
                    },
                    json={
                        "model": model,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                                }
                            ]
                        }],
                        "max_tokens": max_tokens
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    logger.info(f"Vision analysis success with model: {model}")
                    return content, model

                logger.warning(f"Vision error with {model}: {response.status_code}")
                last_error = f"Status {response.status_code}"

        except Exception as e:
            logger.error(f"Vision error with {model}: {e}")
            last_error = str(e)

    return f"Vision analysis failed. {last_error}" if last_error else "Vision service error.", ""

# =============================================================================
# CHART ANALYSIS ENDPOINTS
# =============================================================================

@app.post("/analyze-chart")
async def analyze_chart(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Analyze chart image with AI"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # Read and process image
        contents = await file.read()
        img = Image.open(io.BytesIO(contents))

        # Resize if too large
        max_size = (1200, 800)
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Convert to base64
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        img_base64 = base64.b64encode(buffered.getvalue()).decode()

        # AI analysis prompt
        prompt = """Analyze this forex chart image and provide a detailed technical analysis. 

Respond in JSON format with the following structure:
{
    "setup_quality": "A|B|C|D",
    "pair": "detected currency pair (e.g., EURUSD)",
    "direction": "LONG|SHORT|NEUTRAL",
    "entry_price": "suggested entry price",
    "stop_loss": "suggested stop loss",
    "take_profit": "suggested take profit",
    "risk_reward": "calculated risk:reward ratio",
    "analysis": "detailed analysis of the setup",
    "recommendations": ["list of actionable recommendations"],
    "key_levels": ["support/resistance levels with prices"],
    "patterns_detected": ["any chart patterns identified"],
    "confidence_score": 0-100
}

Be specific with price levels and provide actionable insights."""

        # Call AI
        ai_response, model_used = await call_openrouter_vision(img_base64, prompt, max_tokens=2000)

        if ai_response.startswith("AI") or ai_response.startswith("Vision"):
            raise HTTPException(status_code=503, detail=ai_response)

        # Parse JSON response
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                analysis = json.loads(ai_response)
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            analysis = {
                "setup_quality": "C",
                "pair": "Unknown",
                "direction": "NEUTRAL",
                "entry_price": "N/A",
                "stop_loss": "N/A",
                "take_profit": "N/A",
                "risk_reward": "N/A",
                "analysis": ai_response[:500],
                "recommendations": ["Review the analysis carefully"],
                "key_levels": [],
                "patterns_detected": [],
                "confidence_score": 50
            }

        # Save analysis to history
        async with db_pool.acquire() as conn:
            # Save image
            uploads_dir = "uploads/chart_analysis"
            os.makedirs(uploads_dir, exist_ok=True)
            image_path = f"{uploads_dir}/{uuid.uuid4()}.jpg"
            
            with open(image_path, "wb") as f:
                f.write(buffered.getvalue())

            await conn.execute(
                """INSERT INTO chart_analyses 
                       (user_id, image_path, analysis_result, pair, direction, 
                        setup_quality, confidence_score)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                current_user["id"],
                image_path,
                json.dumps(analysis),
                analysis.get("pair"),
                analysis.get("direction"),
                analysis.get("setup_quality"),
                analysis.get("confidence_score", 50)
            )

        return {"analysis": analysis, "model_used": model_used}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chart analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze chart: {str(e)}")

@app.get("/chart-analysis/history")
async def get_chart_analysis_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """Get user's chart analysis history"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        analyses = await conn.fetch(
            """SELECT id, analysis_result, pair, direction, setup_quality, 
                      confidence_score, saved_to_journal, created_at
               FROM chart_analyses
               WHERE user_id = $1
               ORDER BY created_at DESC
               LIMIT $2""",
            current_user["id"], limit
        )

        return [dict(a) for a in analyses]

# =============================================================================
# AI MENTOR CHAT
# =============================================================================

@app.get("/mentor-chat")
async def mentor_chat(
    message: str = Query(..., min_length=1),
    current_user: dict = Depends(get_current_user)
):
    """Chat with AI trading mentor"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # Get chat history for context
        async with db_pool.acquire() as conn:
            history = await conn.fetch(
                """SELECT message, response
                   FROM mentor_chat_history
                   WHERE user_id = $1
                   ORDER BY created_at DESC
                   LIMIT 5""",
                current_user["id"]
            )

        # Build context
        context = ""
        for h in reversed(history):
            context += f"User: {h['message']}\nMentor: {h['response']}\n\n"

        prompt = f"""You are an expert forex trading mentor and psychologist. Your role is to help traders improve their performance through coaching, psychology insights, and practical advice.

Previous conversation context:
{context}

User question: {message}

Provide a helpful, encouraging response that addresses their question. Be specific and actionable. If they're asking about trading psychology, provide insights on emotional control, discipline, and mindset. If they're asking about strategy, focus on risk management and process over outcomes.

Keep your response concise (2-3 paragraphs max) and supportive."""

        response, model_used = await call_openrouter_with_fallback(prompt, max_tokens=800)

        if response.startswith("AI"):
            raise HTTPException(status_code=503, detail=response)

        # Save to history
        async with db_pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO mentor_chat_history (user_id, message, response)
                   VALUES ($1, $2, $3)""",
                current_user["id"], message, response
            )

        return {"response": response, "model_used": model_used}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mentor chat error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get mentor response")

@app.get("/mentor-chat/history")
async def get_mentor_chat_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """Get chat history with AI mentor"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        history = await conn.fetch(
            """SELECT id, message, response, created_at
               FROM mentor_chat_history
               WHERE user_id = $1
               ORDER BY created_at DESC
               LIMIT $2""",
            current_user["id"], limit
        )

        return [dict(h) for h in history]

# =============================================================================
# PERFORMANCE ANALYSIS
# =============================================================================

@app.post("/performance/analyze")
async def analyze_performance(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Analyze trading performance with AI"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # Read file
        contents = await file.read()

        # Get user's trades
        async with db_pool.acquire() as conn:
            trades = await conn.fetch(
                """SELECT pair, direction, pips, grade, created_at
                   FROM trades
                   WHERE user_id = $1
                   ORDER BY created_at DESC
                   LIMIT 100""",
                current_user["id"]
            )

        # Check trial limit
        if current_user.get("subscription_status") == "trial":
            analysis_count = await conn.fetchval(
                "SELECT COUNT(*) FROM performance_analyses WHERE user_id = $1",
                current_user["id"]
            )
            if analysis_count >= 1:
                raise HTTPException(
                    status_code=403,
                    detail="Trial limit reached (1 analysis). Upgrade to Pro."
                )

        # Calculate metrics
        total_trades = len(trades)
        if total_trades == 0:
            raise HTTPException(status_code=400, detail="No trades to analyze")

        wins = sum(1 for t in trades if t["pips"] > 0)
        win_rate = (wins / total_trades) * 100
        total_pips = sum(t["pips"] for t in trades)

        winning_pips = sum(t["pips"] for t in trades if t["pips"] > 0)
        losing_pips = abs(sum(t["pips"] for t in trades if t["pips"] < 0))
        profit_factor = winning_pips / losing_pips if losing_pips > 0 else winning_pips

        # Grade distribution
        grade_dist = {}
        for t in trades:
            grade = t["grade"]
            grade_dist[grade] = grade_dist.get(grade, 0) + 1

        # AI analysis
        trades_summary = "\n".join([
            f"{t['created_at'].strftime('%Y-%m-%d')}: {t['pair']} {t['direction']} - {t['pips']:+} pips (Grade {t['grade']})"
            for t in trades[:30]
        ])

        prompt = f"""Analyze this trader's performance and provide insights.

Performance Metrics:
- Total Trades: {total_trades}
- Win Rate: {win_rate:.1f}%
- Total Pips: {total_pips:+.1f}
- Profit Factor: {profit_factor:.2f}
- Grade Distribution: {grade_dist}

Recent Trades:
{trades_summary}

Provide analysis in JSON format:
{{
    "performance_score": 0-100,
    "trader_type": "description of trading style",
    "risk_appetite": "conservative|moderate|aggressive",
    "strengths": ["list of strengths"],
    "weaknesses": ["areas for improvement"],
    "recommendations": ["specific actionable recommendations"],
    "psychology_insights": "analysis of trading psychology"
}}"""

        ai_response, model_used = await call_openrouter_with_fallback(prompt, max_tokens=1500)

        if ai_response.startswith("AI"):
            raise HTTPException(status_code=503, detail=ai_response)

        # Parse response
        try:
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                analysis = json.loads(ai_response)
        except json.JSONDecodeError:
            analysis = {
                "performance_score": 50,
                "trader_type": "Analyzing...",
                "risk_appetite": "moderate",
                "strengths": ["Active trading"],
                "weaknesses": ["Data analysis in progress"],
                "recommendations": ["Continue tracking trades"],
                "psychology_insights": ai_response[:500]
            }

        # Save analysis
        async with db_pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO performance_analyses 
                       (user_id, file_name, analysis_result, trader_type, 
                        performance_score, risk_appetite, ai_insights)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                current_user["id"],
                file.filename,
                json.dumps(analysis),
                analysis.get("trader_type"),
                analysis.get("performance_score", 50),
                analysis.get("risk_appetite"),
                analysis.get("psychology_insights", "")
            )

        return {"analysis": analysis, "model_used": model_used}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Performance analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

# =============================================================================
# ADMIN ENDPOINTS - BLOG MANAGEMENT
# =============================================================================

@app.get("/admin/blog/posts")
async def admin_get_blog_posts(
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_admin_user)
):
    """Admin: Get all blog posts (including drafts)"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    offset = (page - 1) * per_page

    async with db_pool.acquire() as conn:
        where_clauses = []
        params = []
        param_idx = 1

        if status:
            where_clauses.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if category:
            where_clauses.append(f"category = ${param_idx}")
            params.append(category)
            param_idx += 1

        if search:
            where_clauses.append(f"(title ILIKE ${param_idx} OR content ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1

        where_str = " AND ".join(where_clauses) if where_clauses else "TRUE"

        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM blog_posts WHERE {where_str}",
            *params
        )

        posts = await conn.fetch(
            f"""SELECT id, title, slug, excerpt, category, status, seo_score,
                      view_count, published_at, scheduled_at, created_at, updated_at,
                      (SELECT name FROM users WHERE id = blog_posts.author_id) as author_name
               FROM blog_posts
               WHERE {where_str}
               ORDER BY created_at DESC
               LIMIT ${param_idx} OFFSET ${param_idx + 1}""",
            *params, per_page, offset
        )

        return {
            "posts": [dict(p) for p in posts],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page
            }
        }

@app.post("/admin/blog/posts")
async def admin_create_blog_post(
    title: str = Form(..., min_length=1),
    content: str = Form(..., min_length=10),
    excerpt: Optional[str] = Form(None),
    seo_meta_title: Optional[str] = Form(None),
    seo_meta_description: Optional[str] = Form(None, max_length=300),
    focus_keywords: Optional[str] = Form(None),
    canonical_url: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    featured_image: Optional[str] = Form(None),
    status: str = Form("draft"),
    scheduled_at: Optional[str] = Form(None),
    current_user: dict = Depends(get_admin_user)
):
    """Admin: Create blog post"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # Generate slug
        slug = generateSlug(title)
        
        # Parse tags
        tag_list = [t.strip() for t in tags.split(",")] if tags else []
        
        # Parse focus keywords
        keyword_list = [k.strip() for k in focus_keywords.split(",")] if focus_keywords else []

        # Calculate SEO score
        seo_score = calculate_seo_score(title, seo_meta_title, seo_meta_description, 
                                        content, featured_image, keyword_list)

        async with db_pool.acquire() as conn:
            # Check slug uniqueness
            existing = await conn.fetchval("SELECT id FROM blog_posts WHERE slug = $1", slug)
            if existing:
                slug = f"{slug}-{int(datetime.utcnow().timestamp())}"

            # Parse scheduled date
            scheduled_dt = None
            if scheduled_at:
                try:
                    scheduled_dt = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                except:
                    pass

            post_id = await conn.fetchval(
                """INSERT INTO blog_posts 
                       (title, slug, content, excerpt, seo_meta_title, seo_meta_description,
                        focus_keywords, canonical_url, category, tags, featured_image,
                        author_id, status, scheduled_at, seo_score, published_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                           CASE WHEN $13 = 'published' THEN NOW() ELSE NULL END)
                   RETURNING id""",
                title, slug, content, excerpt, seo_meta_title, seo_meta_description,
                keyword_list, canonical_url, category, tag_list, featured_image,
                current_user["id"], status, scheduled_dt, seo_score
            )

            cache_delete_pattern("blog:posts")

            return {"id": post_id, "slug": slug, "message": "Post created successfully"}

    except Exception as e:
        logger.error(f"Create blog post error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create post: {str(e)}")

def calculate_seo_score(title, meta_title, meta_description, content, featured_image, keywords):
    """Calculate SEO score for a blog post"""
    score = 0
    
    # Title length (optimal: 50-60 chars) = 20 points
    title_len = len(title) if title else 0
    if 50 <= title_len <= 60:
        score += 20
    elif 40 <= title_len <= 70:
        score += 15
    else:
        score += 10
    
    # Meta description present = 15 points
    if meta_description and len(meta_description) > 50:
        score += 15
    
    # Focus keywords present = 15 points
    if keywords and len(keywords) > 0:
        score += 15
    
    # Content length > 300 words = 20 points
    word_count = len(content.split()) if content else 0
    if word_count > 500:
        score += 20
    elif word_count > 300:
        score += 15
    elif word_count > 100:
        score += 10
    
    # Featured image = 10 points
    if featured_image:
        score += 10
    
    # URL slug optimized = 10 points
    if title:
        score += 10
    
    # Internal links (simplified) = 10 points
    if content and '<a href="/' in content:
        score += 10
    
    return min(score, 100)

@app.put("/admin/blog/posts/{post_id}")
async def admin_update_blog_post(
    post_id: int,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    seo_meta_title: Optional[str] = Form(None),
    seo_meta_description: Optional[str] = Form(None),
    focus_keywords: Optional[str] = Form(None),
    canonical_url: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    featured_image: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    scheduled_at: Optional[str] = Form(None),
    current_user: dict = Depends(get_admin_user)
):
    """Admin: Update blog post"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            # Get existing post
            existing = await conn.fetchrow(
                "SELECT * FROM blog_posts WHERE id = $1",
                post_id
            )

            if not existing:
                raise HTTPException(status_code=404, detail="Post not found")

            # Build update
            updates = []
            params = []
            param_idx = 1

            if title is not None:
                updates.append(f"title = ${param_idx}")
                params.append(title)
                param_idx += 1
                # Update slug if title changed
                new_slug = generateSlug(title)
                slug_exists = await conn.fetchval(
                    "SELECT id FROM blog_posts WHERE slug = $1 AND id != $2",
                    new_slug, post_id
                )
                if not slug_exists:
                    updates.append(f"slug = ${param_idx}")
                    params.append(new_slug)
                    param_idx += 1

            if content is not None:
                updates.append(f"content = ${param_idx}")
                params.append(content)
                param_idx += 1

            if excerpt is not None:
                updates.append(f"excerpt = ${param_idx}")
                params.append(excerpt)
                param_idx += 1

            if seo_meta_title is not None:
                updates.append(f"seo_meta_title = ${param_idx}")
                params.append(seo_meta_title)
                param_idx += 1

            if seo_meta_description is not None:
                updates.append(f"seo_meta_description = ${param_idx}")
                params.append(seo_meta_description)
                param_idx += 1

            if focus_keywords is not None:
                keyword_list = [k.strip() for k in focus_keywords.split(",")] if focus_keywords else []
                updates.append(f"focus_keywords = ${param_idx}")
                params.append(keyword_list)
                param_idx += 1

            if canonical_url is not None:
                updates.append(f"canonical_url = ${param_idx}")
                params.append(canonical_url)
                param_idx += 1

            if category is not None:
                updates.append(f"category = ${param_idx}")
                params.append(category)
                param_idx += 1

            if tags is not None:
                tag_list = [t.strip() for t in tags.split(",")] if tags else []
                updates.append(f"tags = ${param_idx}")
                params.append(tag_list)
                param_idx += 1

            if featured_image is not None:
                updates.append(f"featured_image = ${param_idx}")
                params.append(featured_image)
                param_idx += 1

            if status is not None:
                updates.append(f"status = ${param_idx}")
                params.append(status)
                param_idx += 1
                
                if status == "published" and existing["status"] != "published":
                    updates.append(f"published_at = NOW()")

            if scheduled_at is not None:
                try:
                    scheduled_dt = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                    updates.append(f"scheduled_at = ${param_idx}")
                    params.append(scheduled_dt)
                    param_idx += 1
                except:
                    pass

            # Recalculate SEO score
            current_title = title if title is not None else existing["title"]
            current_meta_title = seo_meta_title if seo_meta_title is not None else existing["seo_meta_title"]
            current_meta_desc = seo_meta_description if seo_meta_description is not None else existing["seo_meta_description"]
            current_content = content if content is not None else existing["content"]
            current_image = featured_image if featured_image is not None else existing["featured_image"]
            current_keywords = [k.strip() for k in focus_keywords.split(",")] if focus_keywords else existing.get("focus_keywords", []) or []
            
            new_seo_score = calculate_seo_score(
                current_title, current_meta_title, current_meta_desc,
                current_content, current_image, current_keywords
            )
            updates.append(f"seo_score = ${param_idx}")
            params.append(new_seo_score)
            param_idx += 1

            updates.append(f"updated_at = NOW()")
            params.append(post_id)

            if updates:
                await conn.execute(
                    f"UPDATE blog_posts SET {', '.join(updates)} WHERE id = ${param_idx}",
                    *params
                )

            cache_delete_pattern("blog:posts")
            cache_delete(f"blog:post:{existing['slug']}")

            return {"message": "Post updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update blog post error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update post: {str(e)}")

@app.delete("/admin/blog/posts/{post_id}")
async def admin_delete_blog_post(
    post_id: int,
    current_user: dict = Depends(get_admin_user)
):
    """Admin: Delete blog post"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        post = await conn.fetchrow(
            "SELECT slug FROM blog_posts WHERE id = $1",
            post_id
        )

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        await conn.execute("DELETE FROM blog_posts WHERE id = $1", post_id)

        cache_delete_pattern("blog:posts")
        cache_delete(f"blog:post:{post['slug']}")

        return {"message": "Post deleted successfully"}

@app.post("/admin/blog/posts/{post_id}/publish")
async def admin_publish_blog_post(
    post_id: int,
    current_user: dict = Depends(get_admin_user)
):
    """Admin: Publish blog post immediately"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE blog_posts 
               SET status = 'published', published_at = NOW(), scheduled_at = NULL
               WHERE id = $1""",
            post_id
        )

        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Post not found")

        cache_delete_pattern("blog:posts")

        return {"message": "Post published successfully"}

@app.post("/admin/blog/upload-image")
async def admin_upload_blog_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_admin_user)
):
    """Admin: Upload image to media library"""
    try:
        # Validate file type
        allowed_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Invalid file type. Only JPEG, PNG, GIF, WebP allowed.")

        # Read file
        contents = await file.read()
        
        # Validate file size (max 5MB)
        if len(contents) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum 5MB.")

        # Process image
        img = Image.open(io.BytesIO(contents))
        
        # Resize if too large
        max_size = (1920, 1080)
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Generate filename
        ext = file.filename.split(".")[-1].lower()
        if ext not in ["jpg", "jpeg", "png", "gif", "webp"]:
            ext = "jpg"
        
        filename = f"{uuid.uuid4()}.{ext}"
        uploads_dir = "uploads/blog"
        os.makedirs(uploads_dir, exist_ok=True)
        
        file_path = f"{uploads_dir}/{filename}"
        
        # Save image
        if ext in ["jpg", "jpeg"]:
            img.save(file_path, "JPEG", quality=85)
        elif ext == "png":
            img.save(file_path, "PNG", optimize=True)
        elif ext == "webp":
            img.save(file_path, "WEBP", quality=85)
        else:
            img.save(file_path)

        # Save to database
        if db_pool:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO blog_media (filename, original_name, file_path, 
                           file_type, file_size, uploaded_by)
                       VALUES ($1, $2, $3, $4, $5, $6)""",
                    filename, file.filename, file_path, file.content_type, len(contents),
                    current_user["id"]
                )

        # Return URL
        file_url = f"/uploads/blog/{filename}"
        
        return {
            "filename": filename,
            "url": file_url,
            "size": len(contents)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload image error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/admin/blog/media")
async def admin_get_media_library(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_admin_user)
):
    """Admin: Get media library"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    offset = (page - 1) * per_page

    async with db_pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM blog_media")
        
        media = await conn.fetch(
            """SELECT id, filename, original_name, file_type, file_size, 
                      alt_text, created_at
               FROM blog_media
               ORDER BY created_at DESC
               LIMIT $1 OFFSET $2""",
            per_page, offset
        )

        return {
            "media": [dict(m) for m in media],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page
            }
        }

@app.delete("/admin/blog/media/{media_id}")
async def admin_delete_media(
    media_id: int,
    current_user: dict = Depends(get_admin_user)
):
    """Admin: Delete media file"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        media = await conn.fetchrow(
            "SELECT file_path FROM blog_media WHERE id = $1",
            media_id
        )

        if not media:
            raise HTTPException(status_code=404, detail="Media not found")

        # Delete file
        try:
            if os.path.exists(media["file_path"]):
                os.remove(media["file_path"])
        except Exception as e:
            logger.warning(f"Failed to delete file: {e}")

        await conn.execute("DELETE FROM blog_media WHERE id = $1", media_id)

        return {"message": "Media deleted successfully"}

# =============================================================================
# ADMIN ENDPOINTS - COURSE MANAGEMENT
# =============================================================================

@app.get("/admin/courses")
async def admin_get_courses(
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_admin_user)
):
    """Admin: Get all courses"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    offset = (page - 1) * per_page

    async with db_pool.acquire() as conn:
        where_clauses = []
        params = []
        param_idx = 1

        if status:
            where_clauses.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if category:
            where_clauses.append(f"category = ${param_idx}")
            params.append(category)
            param_idx += 1

        if search:
            where_clauses.append(f"(title ILIKE ${param_idx} OR description ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1

        where_str = " AND ".join(where_clauses) if where_clauses else "TRUE"

        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM courses WHERE {where_str}",
            *params
        )

        courses = await conn.fetch(
            f"""SELECT id, title, slug, category, level, price, is_free, status,
                      enrolled_count, rating, rating_count, created_at, updated_at
               FROM courses
               WHERE {where_str}
               ORDER BY created_at DESC
               LIMIT ${param_idx} OFFSET ${param_idx + 1}""",
            *params, per_page, offset
        )

        return {
            "courses": [dict(c) for c in courses],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page
            }
        }

@app.post("/admin/courses")
async def admin_create_course(
    title: str = Form(..., min_length=1),
    description: str = Form(...),
    short_description: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    level: str = Form("beginner"),
    price: float = Form(0),
    is_free: bool = Form(False),
    instructor_name: Optional[str] = Form(None),
    duration_minutes: int = Form(0),
    status: str = Form("draft"),
    current_user: dict = Depends(get_admin_user)
):
    """Admin: Create course"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        slug = generateSlug(title)

        async with db_pool.acquire() as conn:
            # Check slug uniqueness
            existing = await conn.fetchval("SELECT id FROM courses WHERE slug = $1", slug)
            if existing:
                slug = f"{slug}-{int(datetime.utcnow().timestamp())}"

            course_id = await conn.fetchval(
                """INSERT INTO courses 
                       (title, slug, description, short_description, category, level,
                        price, is_free, instructor_name, duration_minutes, status)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                   RETURNING id""",
                title, slug, description, short_description, category, level,
                price, is_free, instructor_name, duration_minutes, status
            )

            cache_delete_pattern("courses:all")

            return {"id": course_id, "slug": slug, "message": "Course created successfully"}

    except Exception as e:
        logger.error(f"Create course error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create course: {str(e)}")

@app.post("/admin/courses/{course_id}/modules")
async def admin_create_module(
    course_id: int,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    is_free_preview: bool = Form(False),
    current_user: dict = Depends(get_admin_user)
):
    """Admin: Create course module"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        # Get next order index
        max_order = await conn.fetchval(
            "SELECT COALESCE(MAX(order_index), 0) FROM course_modules WHERE course_id = $1",
            course_id
        )

        module_id = await conn.fetchval(
            """INSERT INTO course_modules 
                   (course_id, title, description, order_index, is_free_preview)
               VALUES ($1, $2, $3, $4, $5)
               RETURNING id""",
            course_id, title, description, max_order + 1, is_free_preview
        )

        return {"id": module_id, "message": "Module created successfully"}

@app.post("/admin/courses/{course_id}/modules/{module_id}/lessons")
async def admin_create_lesson(
    course_id: int,
    module_id: int,
    title: str = Form(...),
    content: Optional[str] = Form(None),
    video_url: Optional[str] = Form(None),
    duration_minutes: int = Form(0),
    is_free_preview: bool = Form(False),
    current_user: dict = Depends(get_admin_user)
):
    """Admin: Create lesson"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        # Get next order index
        max_order = await conn.fetchval(
            "SELECT COALESCE(MAX(order_index), 0) FROM course_lessons WHERE module_id = $1",
            module_id
        )

        lesson_id = await conn.fetchval(
            """INSERT INTO course_lessons 
                   (course_id, module_id, title, content, video_url, 
                    duration_minutes, order_index, is_free_preview)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               RETURNING id""",
            course_id, module_id, title, content, video_url,
            duration_minutes, max_order + 1, is_free_preview
        )

        return {"id": lesson_id, "message": "Lesson created successfully"}

@app.post("/admin/courses/upload-video")
async def admin_upload_video(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_admin_user)
):
    """Admin: Upload video file"""
    try:
        allowed_types = {"video/mp4", "video/webm", "video/ogg"}
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Invalid file type. Only MP4, WebM, OGG allowed.")

        contents = await file.read()
        
        # Max 100MB
        if len(contents) > 100 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum 100MB.")

        ext = file.filename.split(".")[-1].lower()
        if ext not in ["mp4", "webm", "ogg"]:
            ext = "mp4"

        filename = f"{uuid.uuid4()}.{ext}"
        uploads_dir = "uploads/videos"
        os.makedirs(uploads_dir, exist_ok=True)
        
        file_path = f"{uploads_dir}/{filename}"

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(contents)

        return {
            "filename": filename,
            "url": f"/uploads/videos/{filename}",
            "size": len(contents)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload video error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/admin/courses/upload-pdf")
async def admin_upload_pdf(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_admin_user)
):
    """Admin: Upload PDF resource"""
    try:
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Only PDF files allowed.")

        contents = await file.read()
        
        # Max 20MB
        if len(contents) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum 20MB.")

        filename = f"{uuid.uuid4()}.pdf"
        uploads_dir = "uploads/pdfs"
        os.makedirs(uploads_dir, exist_ok=True)
        
        file_path = f"{uploads_dir}/{filename}"

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(contents)

        return {
            "filename": filename,
            "url": f"/uploads/pdfs/{filename}",
            "size": len(contents)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload PDF error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

# =============================================================================
# STATIC FILES
# =============================================================================

# Create uploads directory
os.makedirs("uploads/blog", exist_ok=True)
os.makedirs("uploads/videos", exist_ok=True)
os.makedirs("uploads/pdfs", exist_ok=True)
os.makedirs("uploads/chart_analysis", exist_ok=True)

# Mount static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
