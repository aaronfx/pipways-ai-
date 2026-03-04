"""
Pipways - Forex Trading Journal API v3.0
SQLite Backend (No PostgreSQL needed) - Complete Working Version
"""

import os
import re
import json
import base64
import logging
import io
import uuid
import sqlite3
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from jose import JWTError, jwt
from PIL import Image

# =============================================================================
# CONFIGURATION & LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
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

# Database path
DATABASE_PATH = os.getenv("DATABASE_PATH", "pipways.db")

# In-memory cache
cache_store: Dict[str, Any] = {}
cache_expiry: Dict[str, datetime] = {}

# Rate limiting store
rate_limit_store: Dict[str, List[datetime]] = {}

# Token blacklist (for logout)
token_blacklist: set = set()

# =============================================================================
# SQLITE DATABASE SETUP (From your Tkinter code, adapted for FastAPI)
# =============================================================================

def get_db_connection():
    """Get SQLite database connection"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initialize SQLite database with all tables"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users table (from your Tkinter code, enhanced)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        phone TEXT,
        country TEXT,
        role TEXT DEFAULT 'user',
        is_active BOOLEAN DEFAULT 1,
        avatar_url TEXT,
        login_attempts INTEGER DEFAULT 0,
        locked_until TIMESTAMP,
        last_login_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # User settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        settings_json TEXT DEFAULT '{}',
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # Trades table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        account_id INTEGER DEFAULT 1,
        symbol TEXT NOT NULL,
        trade_type TEXT NOT NULL,
        entry_price REAL NOT NULL,
        exit_price REAL,
        stop_loss REAL,
        take_profit REAL,
        position_size REAL,
        lot_size REAL,
        strategy TEXT,
        timeframe TEXT,
        setup_type TEXT,
        entry_date TIMESTAMP NOT NULL,
        exit_date TIMESTAMP,
        emotions TEXT,
        notes TEXT,
        lessons_learned TEXT,
        tags TEXT DEFAULT '[]',
        status TEXT DEFAULT 'open',
        profit_loss REAL,
        ai_analysis TEXT,
        screenshots TEXT DEFAULT '[]',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # Accounts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT DEFAULT 'Main Account',
        balance REAL DEFAULT 0,
        currency TEXT DEFAULT 'USD',
        is_active BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # Courses table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        instructor_id INTEGER,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        description TEXT NOT NULL,
        short_description TEXT,
        thumbnail_url TEXT,
        preview_video_url TEXT,
        category TEXT,
        level TEXT DEFAULT 'beginner',
        price REAL DEFAULT 0,
        duration_hours INTEGER DEFAULT 0,
        is_published BOOLEAN DEFAULT 0,
        is_featured BOOLEAN DEFAULT 0,
        seo_title TEXT,
        seo_description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (instructor_id) REFERENCES users(id) ON DELETE SET NULL
    )
    """)

    # Course modules table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS course_modules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        sort_order INTEGER DEFAULT 0,
        is_published BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
    )
    """)

    # Course lessons table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS course_lessons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        module_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        content TEXT,
        video_url TEXT,
        video_duration INTEGER DEFAULT 0,
        is_preview BOOLEAN DEFAULT 0,
        sort_order INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (module_id) REFERENCES course_modules(id) ON DELETE CASCADE
    )
    """)

    # User enrollments table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        payment_status TEXT DEFAULT 'pending',
        progress_percent INTEGER DEFAULT 0,
        enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
        UNIQUE(user_id, course_id)
    )
    """)

    # Lesson progress table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lesson_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        lesson_id INTEGER NOT NULL,
        is_completed BOOLEAN DEFAULT 0,
        watch_time_seconds INTEGER DEFAULT 0,
        completed_at TIMESTAMP,
        last_watched_at TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (lesson_id) REFERENCES course_lessons(id) ON DELETE CASCADE,
        UNIQUE(user_id, lesson_id)
    )
    """)

    # Blog posts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS blog_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author_id INTEGER,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        excerpt TEXT,
        content TEXT NOT NULL,
        featured_image TEXT,
        category TEXT,
        tags TEXT DEFAULT '[]',
        seo_title TEXT,
        seo_description TEXT,
        seo_keywords TEXT,
        status TEXT DEFAULT 'draft',
        view_count INTEGER DEFAULT 0,
        published_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE SET NULL
    )
    """)

    # Blog media table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS blog_media (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uploaded_by INTEGER,
        filename TEXT NOT NULL,
        original_name TEXT,
        file_path TEXT NOT NULL,
        file_size INTEGER,
        mime_type TEXT,
        alt_text TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE SET NULL
    )
    """)

    conn.commit()

    # Create default admin user if none exists
    cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    if not cursor.fetchone():
        admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
        cursor.execute("""
            INSERT INTO users (email, password_hash, full_name, role, is_active)
            VALUES (?, ?, ?, ?, ?)
        """, ("admin@pipways.com", admin_hash, "Administrator", "admin", 1))
        conn.commit()
        logger.info("Created default admin user: admin@pipways.com / admin123")

    conn.close()
    logger.info("SQLite database initialized successfully")

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
        "permissions": [
            "read:blog", "write:trades", "read:analytics", "read:mentor"
        ],
        "can_access_admin": False,
        "can_enroll_courses": True,
        "can_access_paid_content": False
    }
}

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2)
    phone: Optional[str] = None
    country: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class AdminLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]

class TradeCreate(BaseModel):
    account_id: int = 1
    symbol: str
    trade_type: str = Field(..., pattern="^(BUY|SELL)$")
    entry_price: float = Field(..., gt=0)
    exit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size: Optional[float] = None
    lot_size: Optional[float] = None
    strategy: Optional[str] = None
    timeframe: Optional[str] = None
    setup_type: Optional[str] = None
    entry_date: datetime
    exit_date: Optional[datetime] = None
    emotions: Optional[str] = None
    notes: Optional[str] = None
    lessons_learned: Optional[str] = None
    tags: Optional[List[str]] = []

class TradeUpdate(BaseModel):
    exit_price: Optional[float] = None
    exit_date: Optional[datetime] = None
    status: Optional[str] = Field(None, pattern="^(open|closed|cancelled)$")
    emotions: Optional[str] = None
    notes: Optional[str] = None
    lessons_learned: Optional[str] = None
    tags: Optional[List[str]] = None

class BlogPostCreate(BaseModel):
    title: str = Field(..., min_length=5)
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    content: str = Field(..., min_length=10)
    featured_image: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = []
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_keywords: Optional[str] = None
    status: str = Field(default="draft", pattern="^(draft|published|archived)$")

class BlogPostUpdate(BaseModel):
    title: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = None
    featured_image: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_keywords: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(draft|published|archived)$")

class CourseCreate(BaseModel):
    title: str = Field(..., min_length=5)
    slug: Optional[str] = None
    description: str = Field(..., min_length=10)
    short_description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    preview_video_url: Optional[str] = None
    category: Optional[str] = None
    level: str = Field(default="beginner", pattern="^(beginner|intermediate|advanced)$")
    price: float = Field(default=0, ge=0)
    duration_hours: int = Field(default=0, ge=0)
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None

class CourseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    preview_video_url: Optional[str] = None
    category: Optional[str] = None
    level: Optional[str] = Field(None, pattern="^(beginner|intermediate|advanced)$")
    price: Optional[float] = Field(None, ge=0)
    duration_hours: Optional[int] = Field(None, ge=0)
    is_published: Optional[bool] = None
    is_featured: Optional[bool] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None

class ModuleCreate(BaseModel):
    course_id: int
    title: str = Field(..., min_length=3)
    description: Optional[str] = None
    sort_order: int = 0

class LessonCreate(BaseModel):
    module_id: int
    title: str = Field(..., min_length=3)
    description: Optional[str] = None
    content: Optional[str] = None
    video_url: Optional[str] = None
    video_duration: int = 0
    is_preview: bool = False
    sort_order: int = 0

class AIAnalysisRequest(BaseModel):
    trade_id: int
    prompt: Optional[str] = "Analyze this trade setup and provide feedback on entry, stop loss, take profit, and risk management."
    model: Optional[str] = "anthropic/claude-3.5-sonnet"

class ChartAnalysisRequest(BaseModel):
    image_base64: str = Field(..., description="Base64 encoded chart image")
    prompt: Optional[str] = "Analyze this forex chart and identify patterns, support/resistance levels, and potential trade setups."
    symbol: Optional[str] = None
    timeframe: Optional[str] = None

# =============================================================================
# AUTHENTICATION HELPERS (From your Tkinter code, adapted)
# =============================================================================

def hash_password(password: str) -> str:
    """Simple SHA256 hash (from your Tkinter code)"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return hash_password(plain_password) == hashed_password

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_admin_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=ADMIN_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire, "token_type": "admin"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    token = credentials.credentials

    if token in token_blacklist:
        raise HTTPException(status_code=401, detail="Token has been revoked")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, email, full_name, role, avatar_url, is_active FROM users WHERE id = ?",
                (int(user_id),)
            )
            user = cursor.fetchone()

            if user is None:
                raise HTTPException(status_code=401, detail="User not found")
            if not user["is_active"]:
                raise HTTPException(status_code=401, detail="User account is deactivated")
            return dict(user)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_admin_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    user = await get_current_user(credentials)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def check_permission(user: dict, permission: str) -> bool:
    role = user.get("role", "user")
    role_perms = ROLES.get(role, {}).get("permissions", [])
    return "*" in role_perms or permission in role_perms

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def generate_slug(text: str) -> str:
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug[:500]

def format_datetime(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None

def save_upload_file_sync(upload_file: UploadFile, folder: str) -> str:
    """Save uploaded file synchronously (SQLite is sync)"""
    upload_dir = f"uploads/{folder}"
    os.makedirs(upload_dir, exist_ok=True)

    file_ext = os.path.splitext(upload_file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(upload_dir, unique_filename)

    # Read and write file
    content = upload_file.file.read()
    with open(file_path, 'wb') as f:
        f.write(content)

    return file_path

def process_image(image_data: bytes, max_size: tuple = (1920, 1080), quality: int = 85) -> bytes:
    """Process and optimize image"""
    img = Image.open(io.BytesIO(image_data))

    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')

    img.thumbnail(max_size, Image.Resampling.LANCZOS)

    output = io.BytesIO()
    img.save(output, format='JPEG', quality=quality, optimize=True)
    return output.getvalue()

# =============================================================================
# CACHE & RATE LIMITING
# =============================================================================

def get_cached(key: str) -> Any:
    if key in cache_store:
        if cache_expiry.get(key, datetime.min) > datetime.utcnow():
            return cache_store[key]
        else:
            del cache_store[key]
            del cache_expiry[key]
    return None

def set_cached(key: str, value: Any, ttl_seconds: int = 300):
    cache_store[key] = value
    cache_expiry[key] = datetime.utcnow() + timedelta(seconds=ttl_seconds)

def rate_limit(key: str, max_requests: int = 100, window_seconds: int = 60) -> bool:
    now = datetime.utcnow()
    if key not in rate_limit_store:
        rate_limit_store[key] = []

    rate_limit_store[key] = [
        t for t in rate_limit_store[key]
        if (now - t).seconds < window_seconds
    ]

    if len(rate_limit_store[key]) >= max_requests:
        return False

    rate_limit_store[key].append(now)
    return True

# =============================================================================
# FASTAPI APPLICATION
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create uploads directory on startup
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("uploads/blog", exist_ok=True)

    # Initialize SQLite database
    init_db()

    logger.info("Application startup complete")
    yield

    logger.info("Application shutdown")

app = FastAPI(
    title="Pipways API",
    description="Forex Trading Journal with AI Analysis, Courses, and Blog",
    version="3.0.0",
    lifespan=lifespan
)

# =============================================================================
# CORS MIDDLEWARE - MUST BE FIRST
# =============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

# Create uploads directory BEFORE mounting StaticFiles
os.makedirs("uploads", exist_ok=True)
os.makedirs("uploads/blog", exist_ok=True)

# Mount static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# =============================================================================
# GLOBAL OPTIONS HANDLER FOR PREFLIGHT
# =============================================================================

@app.options("/{rest_of_path:path}")
async def global_preflight_handler(request: Request, rest_of_path: str = ""):
    """
    Handle ALL OPTIONS preflight requests globally. This ensures CORS preflight never fails with 405.
    """
    origin = request.headers.get("origin", "*")
    requested_method = request.headers.get("access-control-request-method", "*")
    requested_headers = request.headers.get("access-control-request-headers", "*")

    response = Response(status_code=204)  # No Content
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD"
    response.headers["Access-Control-Allow-Headers"] = requested_headers if requested_headers != "*" else "*"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Max-Age"] = "86400"

    logger.info(f"Preflight request for: {request.url.path} | Method: {requested_method}")
    return response

# =============================================================================
# ROOT & HEALTH ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    return {"status": "ok", "message": "Pipways API v3.0 - Use POST /api/auth/login"}

@app.get("/health")
async def health_check():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            db_status = "connected" if result else "error"
    except Exception as e:
        db_status = f"error: {str(e)[:100]}"

    return {
        "status": "healthy" if db_status == "connected" else "unhealthy",
        "version": "3.0.0",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/info")
async def api_info():
    return {
        "name": "Pipways API",
        "version": "3.0.0",
        "features": [
            "trading_journal", "analytics", "ai_analysis", "courses", "blog", "admin_dashboard", "rbac"
        ]
    }

# =============================================================================
# AUTHENTICATION ENDPOINTS (From your Tkinter code, adapted for FastAPI)
# =============================================================================

@app.post("/api/auth/register", response_model=TokenResponse)
@app.post("/api/auth/register/", response_model=TokenResponse)
async def register(user_data: UserRegister):
    """
    Register endpoint - adapted from your Tkinter register() function.
    Handles both /register and /register/ to avoid trailing slash issues.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Check if email exists (like your username check)
        cursor.execute("SELECT id FROM users WHERE email = ?", (user_data.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")

        # Hash password (from your Tkinter code)
        password_hash = hash_password(user_data.password)

        # Insert user (like your INSERT INTO user)
        cursor.execute("""
            INSERT INTO users (email, password_hash, full_name, phone, country, role)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_data.email, password_hash, user_data.full_name,
              user_data.phone, user_data.country, "user"))

        user_id = cursor.lastrowid

        # Create user settings
        cursor.execute("INSERT INTO user_settings (user_id) VALUES (?)", (user_id,))

        # Create default account for user
        cursor.execute("""
            INSERT INTO accounts (user_id, name, balance, currency)
            VALUES (?, ?, ?, ?)
        """, (user_id, "Main Account", 10000.0, "USD"))

        conn.commit()

        # Create access token
        access_token = create_access_token({"sub": str(user_id), "role": "user"})

        return TokenResponse(
            access_token=access_token,
            expires_in=ACCESS_TOKEN_EXPIRE_DAYS * 86400,
            user={
                "id": user_id,
                "email": user_data.email,
                "full_name": user_data.full_name,
                "role": "user"
            }
        )

@app.post("/api/auth/login", response_model=TokenResponse)
@app.post("/api/auth/login/", response_model=TokenResponse)
async def login(login_data: UserLogin):
    """
    Login endpoint - adapted from your Tkinter login() function.
    Handles both /login and /login/ to avoid trailing slash redirect issues.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Query user (like your SELECT * FROM user WHERE username=? AND password=?)
        cursor.execute("""
            SELECT * FROM users WHERE email = ?
        """, (login_data.email,))

        user = cursor.fetchone()

        # Check if user exists and password matches
        if not user or not verify_password(login_data.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Check if account is locked
        if user["locked_until"]:
            locked_until = datetime.fromisoformat(user["locked_until"]) if isinstance(user["locked_until"], str) else user["locked_until"]
            if locked_until > datetime.utcnow():
                remaining = (locked_until - datetime.utcnow()).seconds // 60
                raise HTTPException(status_code=401, detail=f"Account locked. Try again in {remaining} minutes")

        # Update login info
        cursor.execute("""
            UPDATE users
            SET login_attempts = 0, locked_until = NULL, last_login_at = ?
            WHERE id = ?
        """, (datetime.utcnow().isoformat(), user["id"]))

        conn.commit()

        # Create access token
        access_token = create_access_token({"sub": str(user["id"]), "role": user["role"]})

        return TokenResponse(
            access_token=access_token,
            expires_in=ACCESS_TOKEN_EXPIRE_DAYS * 86400,
            user={
                "id": user["id"],
                "email": user["email"],
                "full_name": user["full_name"],
                "role": user["role"],
                "avatar_url": user["avatar_url"]
            }
        )

@app.post("/api/admin/login", response_model=TokenResponse)
@app.post("/api/admin/login/", response_model=TokenResponse)
async def admin_login(login_data: AdminLogin):
    """Admin login - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM users WHERE email = ? AND role = 'admin'
        """, (login_data.email,))

        user = cursor.fetchone()

        if not user or not verify_password(login_data.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid admin credentials")

        access_token = create_admin_token({"sub": str(user["id"]), "role": "admin"})

        return TokenResponse(
            access_token=access_token,
            expires_in=ADMIN_TOKEN_EXPIRE_HOURS * 3600,
            user={
                "id": user["id"],
                "email": user["email"],
                "full_name": user["full_name"],
                "role": "admin"
            }
        )

@app.post("/api/auth/logout")
@app.post("/api/auth/logout/")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    """Logout - handles both trailing slash variations"""
    token = credentials.credentials
    token_blacklist.add(token)
    return {"message": "Logged out successfully"}

@app.get("/api/auth/me")
@app.get("/api/auth/me/")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user - handles both trailing slash variations"""
    return {"user": current_user}

# Debug endpoint
@app.api_route("/api/auth/login-debug", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"])
async def login_debug(request: Request):
    """Debug endpoint to diagnose request issues"""
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        try:
            body = await request.json()
        except:
            body = await request.body()

    return {
        "method_received": request.method,
        "url": str(request.url),
        "headers": dict(request.headers),
        "query_params": dict(request.query_params),
        "body": body,
        "client": request.client.host if request.client else None
    }

# =============================================================================
# TRADING ENDPOINTS
# =============================================================================

@app.post("/api/trades")
@app.post("/api/trades/")
async def create_trade(trade: TradeCreate, current_user: dict = Depends(get_current_user)):
    """Create trade - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Verify account exists
        cursor.execute(
            "SELECT id FROM accounts WHERE id = ? AND user_id = ?",
            (trade.account_id, current_user["id"])
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Account not found")

        # Calculate profit/loss if trade is closed
        profit_loss = None
        if trade.exit_price:
            if trade.trade_type == "BUY":
                profit_loss = (trade.exit_price - trade.entry_price) * (trade.position_size or 1)
            else:
                profit_loss = (trade.entry_price - trade.exit_price) * (trade.position_size or 1)

        cursor.execute("""
            INSERT INTO trades (
                user_id, account_id, symbol, trade_type, entry_price, exit_price,
                stop_loss, take_profit, position_size, lot_size, strategy,
                timeframe, setup_type, entry_date, exit_date, emotions, notes,
                lessons_learned, tags, status, profit_loss
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            current_user["id"], trade.account_id, trade.symbol, trade.trade_type,
            trade.entry_price, trade.exit_price, trade.stop_loss, trade.take_profit,
            trade.position_size, trade.lot_size, trade.strategy, trade.timeframe,
            trade.setup_type, trade.entry_date.isoformat(),
            trade.exit_date.isoformat() if trade.exit_date else None,
            trade.emotions, trade.notes, trade.lessons_learned,
            json.dumps(trade.tags), "closed" if trade.exit_price else "open",
            profit_loss
        ))

        trade_id = cursor.lastrowid
        conn.commit()

        return {"id": trade_id, "message": "Trade created successfully"}

@app.get("/api/trades")
@app.get("/api/trades/")
async def list_trades(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    current_user: dict = Depends(get_current_user)
):
    """List trades - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()

        where_clauses = ["user_id = ?"]
        params = [current_user["id"]]

        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if symbol:
            where_clauses.append("symbol LIKE ?")
            params.append(f"%{symbol}%")
        if strategy:
            where_clauses.append("strategy = ?")
            params.append(strategy)

        where_sql = " AND ".join(where_clauses)

        # Get total count
        cursor.execute(f"SELECT COUNT(*) as total FROM trades WHERE {where_sql}", params)
        total = cursor.fetchone()["total"]

        # Get trades with pagination
        offset = (page - 1) * per_page
        cursor.execute(f"""
            SELECT * FROM trades WHERE {where_sql}
            ORDER BY entry_date DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset])

        trades = cursor.fetchall()

        return {
            "trades": [dict(t) for t in trades],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        }

@app.get("/api/trades/{trade_id}")
async def get_trade(trade_id: int, current_user: dict = Depends(get_current_user)):
    """Get specific trade"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM trades WHERE id = ? AND user_id = ?",
            (trade_id, current_user["id"])
        )
        trade = cursor.fetchone()

        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")
        return dict(trade)

@app.put("/api/trades/{trade_id}")
async def update_trade(
    trade_id: int,
    trade_update: TradeUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update trade"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM trades WHERE id = ? AND user_id = ?",
            (trade_id, current_user["id"])
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Trade not found")

        update_fields = []
        params = []

        if trade_update.exit_price is not None:
            update_fields.append("exit_price = ?")
            params.append(trade_update.exit_price)
        if trade_update.exit_date is not None:
            update_fields.append("exit_date = ?")
            params.append(trade_update.exit_date.isoformat())
        if trade_update.status is not None:
            update_fields.append("status = ?")
            params.append(trade_update.status)
        if trade_update.emotions is not None:
            update_fields.append("emotions = ?")
            params.append(trade_update.emotions)
        if trade_update.notes is not None:
            update_fields.append("notes = ?")
            params.append(trade_update.notes)
        if trade_update.lessons_learned is not None:
            update_fields.append("lessons_learned = ?")
            params.append(trade_update.lessons_learned)
        if trade_update.tags is not None:
            update_fields.append("tags = ?")
            params.append(json.dumps(trade_update.tags))

        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")

        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        params.extend([trade_id, current_user["id"]])

        cursor.execute(f"""
            UPDATE trades SET {', '.join(update_fields)}
            WHERE id = ? AND user_id = ?
        """, params)

        conn.commit()
        return {"message": "Trade updated successfully"}

@app.delete("/api/trades/{trade_id}")
async def delete_trade(trade_id: int, current_user: dict = Depends(get_current_user)):
    """Delete trade"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM trades WHERE id = ? AND user_id = ?",
            (trade_id, current_user["id"])
        )
        conn.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Trade not found")
        return {"message": "Trade deleted successfully"}

# =============================================================================
# ANALYTICS ENDPOINTS
# =============================================================================

@app.get("/api/analytics/dashboard")
@app.get("/api/analytics/dashboard/")
async def get_dashboard_analytics(current_user: dict = Depends(get_current_user)):
    """Dashboard analytics - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Overall stats
        cursor.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) as losing_trades,
                SUM(profit_loss) as net_pnl,
                AVG(profit_loss) as avg_pnl,
                AVG(CASE WHEN profit_loss > 0 THEN profit_loss END) as avg_win,
                AVG(CASE WHEN profit_loss < 0 THEN profit_loss END) as avg_loss,
                MAX(profit_loss) as max_win,
                MIN(profit_loss) as max_loss
            FROM trades
            WHERE user_id = ? AND status = 'closed'
        """, (current_user["id"],))

        overall = cursor.fetchone()

        total_trades = overall["total_trades"] or 0
        winning_trades = overall["winning_trades"] or 0
        losing_trades = overall["losing_trades"] or 0

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        avg_win = overall["avg_win"] or 0
        avg_loss = abs(overall["avg_loss"] or 0)
        profit_factor = (avg_win * winning_trades) / (avg_loss * losing_trades) if (avg_loss * losing_trades) > 0 else 0
        expectancy = ((win_rate / 100) * avg_win) - ((1 - win_rate / 100) * avg_loss) if total_trades > 0 else 0

        # Monthly performance
        cursor.execute("""
            SELECT
                strftime('%Y-%m', entry_date) as month,
                COUNT(*) as trades,
                SUM(profit_loss) as pnl,
                SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as wins
            FROM trades
            WHERE user_id = ? AND status = 'closed'
            GROUP BY strftime('%Y-%m', entry_date)
            ORDER BY month DESC
            LIMIT 12
        """, (current_user["id"],))

        monthly_data = cursor.fetchall()

        # Strategy performance
        cursor.execute("""
            SELECT
                strategy,
                COUNT(*) as trades,
                SUM(profit_loss) as total_pnl,
                AVG(profit_loss) as avg_pnl,
                SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate
            FROM trades
            WHERE user_id = ? AND status = 'closed' AND strategy IS NOT NULL
            GROUP BY strategy
            ORDER BY total_pnl DESC
        """, (current_user["id"],))

        strategy_performance = cursor.fetchall()

        return {
            "overall": {
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": round(win_rate, 2),
                "net_pnl": round(overall["net_pnl"] or 0, 2),
                "avg_pnl": round(overall["avg_pnl"] or 0, 2),
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
                "profit_factor": round(profit_factor, 2),
                "expectancy": round(expectancy, 2),
                "max_win": round(overall["max_win"] or 0, 2),
                "max_loss": round(overall["max_loss"] or 0, 2)
            },
            "monthly_performance": [dict(m) for m in monthly_data],
            "strategy_performance": [dict(s) for s in strategy_performance]
        }

# =============================================================================
# AI ANALYSIS ENDPOINTS
# =============================================================================

@app.post("/api/ai/analyze-trade")
@app.post("/api/ai/analyze-trade/")
async def analyze_trade_with_ai(
    request: AIAnalysisRequest,
    current_user: dict = Depends(get_current_user)
):
    """AI trade analysis - handles both trailing slash variations"""
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=503, detail="AI service not configured")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM trades WHERE id = ? AND user_id = ?
        """, (request.trade_id, current_user["id"]))

        trade = cursor.fetchone()

        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")

        screenshots = json.loads(trade["screenshots"]) if trade["screenshots"] else []

        prompt = f"""
        Analyze this forex trade and provide detailed feedback:

        Symbol: {trade['symbol']}
        Type: {trade['trade_type']}
        Entry Price: {trade['entry_price']}
        Exit Price: {trade['exit_price'] or 'N/A (still open)'}
        Stop Loss: {trade['stop_loss'] or 'Not set'}
        Take Profit: {trade['take_profit'] or 'Not set'}
        Position Size: {trade['position_size'] or 'N/A'}
        Strategy: {trade['strategy'] or 'N/A'}
        Timeframe: {trade['timeframe'] or 'N/A'}

        User question: {request.prompt}

        Provide analysis covering:
        1. Entry quality and timing
        2. Stop loss placement and risk management
        3. Take profit targeting
        4. Position sizing assessment
        5. Risk-reward ratio evaluation
        6. Areas for improvement
        """

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": FRONTEND_URL or "https://pipways.com"
                    },
                    json={
                        "model": request.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7,
                        "max_tokens": 2000
                    },
                    timeout=60.0
                )

                if response.status_code != 200:
                    logger.error(f"OpenRouter error: {response.text}")
                    raise HTTPException(status_code=502, detail="AI service error")

                result = response.json()
                analysis_text = result["choices"][0]["message"]["content"]

                analysis_data = {
                    "analysis": analysis_text,
                    "model_used": request.model,
                    "analyzed_at": datetime.utcnow().isoformat()
                }

                cursor.execute("""
                    UPDATE trades SET ai_analysis = ? WHERE id = ?
                """, (json.dumps(analysis_data), request.trade_id))
                conn.commit()

                return analysis_data

        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="AI service timeout")
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            raise HTTPException(status_code=500, detail="Failed to analyze trade")

@app.post("/api/ai/analyze-chart")
@app.post("/api/ai/analyze-chart/")
async def analyze_chart_with_ai(
    request: ChartAnalysisRequest,
    current_user: dict = Depends(get_current_user)
):
    """AI chart analysis - handles both trailing slash variations"""
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=503, detail="AI service not configured")

    try:
        image_data = base64.b64decode(request.image_base64.split(",")[-1])

        if len(image_data) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Image too large (max 5MB)")

        processed_image = process_image(image_data, max_size=(1024, 1024), quality=80)
        image_base64 = base64.b64encode(processed_image).decode()

        prompt = f"""
        Analyze this forex chart image and provide detailed technical analysis.

        Symbol: {request.symbol or 'Unknown'}
        Timeframe: {request.timeframe or 'Unknown'}

        {request.prompt}

        Please provide:
        1. Key support and resistance levels
        2. Visible chart patterns
        3. Trend direction and strength
        4. Potential entry/exit points
        5. Risk management considerations
        """

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": FRONTEND_URL or "https://pipways.com"
                },
                json={
                    "model": "anthropic/claude-3.5-sonnet",
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
                    "temperature": 0.7,
                    "max_tokens": 2000
                },
                timeout=60.0
            )

            if response.status_code != 200:
                logger.error(f"OpenRouter error: {response.text}")
                raise HTTPException(status_code=502, detail="AI service error")

            result = response.json()
            analysis_text = result["choices"][0]["message"]["content"]

            return {
                "analysis": analysis_text,
                "model_used": "anthropic/claude-3.5-sonnet",
                "analyzed_at": datetime.utcnow().isoformat()
            }

    except base64.binascii.Error:
        raise HTTPException(status_code=400, detail="Invalid image data")
    except Exception as e:
        logger.error(f"Chart analysis error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze chart")

# =============================================================================
# COURSE ENDPOINTS
# =============================================================================

@app.get("/api/courses")
@app.get("/api/courses/")
async def list_courses(
    category: Optional[str] = None,
    level: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 12
):
    """List courses - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()

        where_clauses = ["is_published = 1"]
        params = []

        if category:
            where_clauses.append("category = ?")
            params.append(category)
        if level:
            where_clauses.append("level = ?")
            params.append(level)
        if search:
            where_clauses.append("(title LIKE ? OR description LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where_sql = " AND ".join(where_clauses)

        # Get total count
        cursor.execute(f"SELECT COUNT(*) as total FROM courses WHERE {where_sql}", params)
        total = cursor.fetchone()["total"]

        # Get courses with pagination
        offset = (page - 1) * per_page
        cursor.execute(f"""
            SELECT c.*, u.full_name as instructor_name,
                   (SELECT COUNT(*) FROM course_modules WHERE course_id = c.id) as module_count,
                   (SELECT COUNT(*) FROM course_lessons l
                    JOIN course_modules m ON l.module_id = m.id WHERE m.course_id = c.id) as lesson_count
            FROM courses c
            LEFT JOIN users u ON c.instructor_id = u.id
            WHERE {where_sql}
            ORDER BY c.is_featured DESC, c.created_at DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset])

        courses = cursor.fetchall()

        return {
            "courses": [dict(c) for c in courses],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        }

@app.get("/api/courses/{course_id}")
async def get_course(course_id: int, current_user: dict = Depends(get_current_user)):
    """Get specific course"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT c.*, u.full_name as instructor_name
            FROM courses c
            LEFT JOIN users u ON c.instructor_id = u.id
            WHERE c.id = ?
        """, (course_id,))

        course = cursor.fetchone()

        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        cursor.execute("""
            SELECT * FROM course_modules
            WHERE course_id = ? AND is_published = 1
            ORDER BY sort_order
        """, (course_id,))

        modules = cursor.fetchall()

        modules_with_lessons = []
        for module in modules:
            cursor.execute("""
                SELECT id, title, description, video_duration, is_preview, sort_order
                FROM course_lessons
                WHERE module_id = ?
                ORDER BY sort_order
            """, (module["id"],))

            lessons = cursor.fetchall()
            module_dict = dict(module)
            module_dict["lessons"] = [dict(l) for l in lessons]
            modules_with_lessons.append(module_dict)

        cursor.execute("""
            SELECT * FROM user_enrollments
            WHERE user_id = ? AND course_id = ?
        """, (current_user["id"], course_id))

        enrollment = cursor.fetchone()

        return {
            "course": dict(course),
            "modules": modules_with_lessons,
            "enrolled": enrollment is not None,
            "enrollment": dict(enrollment) if enrollment else None
        }

@app.post("/api/courses/{course_id}/enroll")
@app.post("/api/courses/{course_id}/enroll/")
async def enroll_in_course(course_id: int, current_user: dict = Depends(get_current_user)):
    """Enroll in course - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, price FROM courses WHERE id = ? AND is_published = 1",
            (course_id,)
        )
        course = cursor.fetchone()

        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        cursor.execute(
            "SELECT id FROM user_enrollments WHERE user_id = ? AND course_id = ?",
            (current_user["id"], course_id)
        )
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Already enrolled")

        cursor.execute("""
            INSERT INTO user_enrollments (user_id, course_id, payment_status)
            VALUES (?, ?, ?)
        """, (current_user["id"], course_id, "completed" if course["price"] == 0 else "pending"))

        conn.commit()
        return {"message": "Enrolled successfully"}

@app.get("/api/courses/{course_id}/lessons/{lesson_id}")
async def get_lesson(
    course_id: int,
    lesson_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get specific lesson"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM user_enrollments
            WHERE user_id = ? AND course_id = ?
        """, (current_user["id"], course_id))

        enrollment = cursor.fetchone()

        cursor.execute("""
            SELECT l.*, m.course_id
            FROM course_lessons l
            JOIN course_modules m ON l.module_id = m.id
            WHERE l.id = ? AND m.course_id = ?
        """, (lesson_id, course_id))

        lesson = cursor.fetchone()

        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found")

        if not lesson["is_preview"] and not enrollment:
            raise HTTPException(status_code=403, detail="Enroll to access this lesson")

        cursor.execute("""
            SELECT * FROM lesson_progress
            WHERE user_id = ? AND lesson_id = ?
        """, (current_user["id"], lesson_id))

        progress = cursor.fetchone()

        return {
            "lesson": dict(lesson),
            "progress": dict(progress) if progress else None
        }

@app.post("/api/courses/{course_id}/lessons/{lesson_id}/progress")
@app.post("/api/courses/{course_id}/lessons/{lesson_id}/progress/")
async def update_lesson_progress(
    course_id: int,
    lesson_id: int,
    is_completed: bool = Form(False),
    watch_time: int = Form(0),
    current_user: dict = Depends(get_current_user)
):
    """Update lesson progress - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM user_enrollments
            WHERE user_id = ? AND course_id = ?
        """, (current_user["id"], course_id))

        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Not enrolled in this course")

        completed_at = datetime.utcnow().isoformat() if is_completed else None

        cursor.execute("""
            INSERT INTO lesson_progress (user_id, lesson_id, is_completed, watch_time_seconds, completed_at, last_watched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, lesson_id) DO UPDATE SET
                is_completed = excluded.is_completed,
                watch_time_seconds = watch_time_seconds + excluded.watch_time_seconds,
                completed_at = COALESCE(completed_at, excluded.completed_at),
                last_watched_at = excluded.last_watched_at
        """, (current_user["id"], lesson_id, is_completed, watch_time, completed_at, datetime.utcnow().isoformat()))

        # Update enrollment progress
        cursor.execute("""
            SELECT COUNT(*) FROM course_lessons l
            JOIN course_modules m ON l.module_id = m.id
            WHERE m.course_id = ?
        """, (course_id,))

        total_lessons = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM lesson_progress lp
            JOIN course_lessons l ON lp.lesson_id = l.id
            JOIN course_modules m ON l.module_id = m.id
            WHERE m.course_id = ? AND lp.user_id = ? AND lp.is_completed = 1
        """, (course_id, current_user["id"]))

        completed_lessons = cursor.fetchone()[0]

        progress_percent = int((completed_lessons / total_lessons) * 100) if total_lessons > 0 else 0

        cursor.execute("""
            UPDATE user_enrollments
            SET progress_percent = ?
            WHERE user_id = ? AND course_id = ?
        """, (progress_percent, current_user["id"], course_id))

        conn.commit()

        return {"progress_percent": progress_percent, "completed_lessons": completed_lessons}

# =============================================================================
# BLOG ENDPOINTS
# =============================================================================

@app.get("/api/blog/posts")
@app.get("/api/blog/posts/")
async def list_blog_posts(
    category: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 10
):
    """List blog posts - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()

        where_clauses = ["status = 'published'"]
        params = []

        if category:
            where_clauses.append("category = ?")
            params.append(category)
        if tag:
            where_clauses.append("tags LIKE ?")
            params.append(f'%{tag}%')
        if search:
            where_clauses.append("(title LIKE ? OR content LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where_sql = " AND ".join(where_clauses)

        # Get total count
        cursor.execute(f"SELECT COUNT(*) as total FROM blog_posts WHERE {where_sql}", params)
        total = cursor.fetchone()["total"]

        # Get posts with pagination
        offset = (page - 1) * per_page
        cursor.execute(f"""
            SELECT p.*, u.full_name as author_name
            FROM blog_posts p
            LEFT JOIN users u ON p.author_id = u.id
            WHERE {where_sql}
            ORDER BY p.published_at DESC NULLS LAST, p.created_at DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset])

        posts = cursor.fetchall()

        return {
            "posts": [dict(p) for p in posts],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        }

@app.get("/api/blog/posts/{slug}")
async def get_blog_post(slug: str):
    """Get specific blog post"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, u.full_name as author_name
            FROM blog_posts p
            LEFT JOIN users u ON p.author_id = u.id
            WHERE p.slug = ? AND p.status = 'published'
        """, (slug,))

        post = cursor.fetchone()

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        # Increment view count
        cursor.execute("""
            UPDATE blog_posts SET view_count = view_count + 1 WHERE id = ?
        """, (post["id"],))

        # Get related posts
        cursor.execute("""
            SELECT slug, title, excerpt, featured_image FROM blog_posts
            WHERE status = 'published' AND category = ? AND id != ?
            ORDER BY published_at DESC LIMIT 3
        """, (post["category"], post["id"]))

        related = cursor.fetchall()

        conn.commit()

        return {
            "post": dict(post),
            "related_posts": [dict(r) for r in related]
        }

# =============================================================================
# ADMIN ENDPOINTS - BLOG MANAGEMENT
# =============================================================================

@app.post("/api/admin/blog/posts")
@app.post("/api/admin/blog/posts/")
async def admin_create_post(
    post: BlogPostCreate,
    current_user: dict = Depends(get_admin_user)
):
    """Create blog post - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()
        slug = post.slug or generate_slug(post.title)

        cursor.execute("SELECT id FROM blog_posts WHERE slug = ?", (slug,))
        if cursor.fetchone():
            slug = f"{slug}-{uuid.uuid4().hex[:8]}"

        cursor.execute("""
            INSERT INTO blog_posts (
                author_id, title, slug, excerpt, content, featured_image,
                category, tags, seo_title, seo_description, seo_keywords, status, published_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            current_user["id"], post.title, slug, post.excerpt, post.content,
            post.featured_image, post.category, json.dumps(post.tags),
            post.seo_title, post.seo_description, post.seo_keywords,
            post.status, datetime.utcnow() if post.status == "published" else None
        ))

        post_id = cursor.lastrowid
        conn.commit()

        return {"id": post_id, "slug": slug, "message": "Post created"}

@app.put("/api/admin/blog/posts/{post_id}")
async def admin_update_post(
    post_id: int,
    post: BlogPostUpdate,
    current_user: dict = Depends(get_admin_user)
):
    """Update blog post"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,))
        existing = cursor.fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Post not found")

        update_fields = []
        params = []

        if post.title is not None:
            update_fields.append("title = ?")
            params.append(post.title)
        if post.excerpt is not None:
            update_fields.append("excerpt = ?")
            params.append(post.excerpt)
        if post.content is not None:
            update_fields.append("content = ?")
            params.append(post.content)
        if post.featured_image is not None:
            update_fields.append("featured_image = ?")
            params.append(post.featured_image)
        if post.category is not None:
            update_fields.append("category = ?")
            params.append(post.category)
        if post.tags is not None:
            update_fields.append("tags = ?")
            params.append(json.dumps(post.tags))
        if post.seo_title is not None:
            update_fields.append("seo_title = ?")
            params.append(post.seo_title)
        if post.seo_description is not None:
            update_fields.append("seo_description = ?")
            params.append(post.seo_description)
        if post.seo_keywords is not None:
            update_fields.append("seo_keywords = ?")
            params.append(post.seo_keywords)
        if post.status is not None:
            update_fields.append("status = ?")
            params.append(post.status)
            if post.status == "published" and existing["status"] != "published":
                update_fields.append("published_at = ?")
                params.append(datetime.utcnow().isoformat())

        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")

        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(post_id)

        cursor.execute(f"""
            UPDATE blog_posts SET {', '.join(update_fields)} WHERE id = ?
        """, params)

        conn.commit()
        return {"message": "Post updated"}

@app.delete("/api/admin/blog/posts/{post_id}")
async def admin_delete_post(post_id: int, current_user: dict = Depends(get_admin_user)):
    """Delete blog post"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM blog_posts WHERE id = ?", (post_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Post not found")
        conn.commit()
        return {"message": "Post deleted"}

@app.get("/api/admin/blog/posts")
@app.get("/api/admin/blog/posts/")
async def admin_list_posts(
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    current_user: dict = Depends(get_admin_user)
):
    """List admin blog posts - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()
        where_clauses = []
        params = []

        if status:
            where_clauses.append("status = ?")
            params.append(status)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Get total count
        cursor.execute(f"SELECT COUNT(*) as total FROM blog_posts WHERE {where_sql}", params)
        total = cursor.fetchone()["total"]

        # Get posts with pagination
        offset = (page - 1) * per_page
        cursor.execute(f"""
            SELECT p.*, u.full_name as author_name
            FROM blog_posts p
            LEFT JOIN users u ON p.author_id = u.id
            WHERE {where_sql}
            ORDER BY p.created_at DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset])

        posts = cursor.fetchall()

        return {
            "posts": [dict(p) for p in posts],
            "total": total,
            "page": page,
            "per_page": per_page
        }

@app.post("/api/admin/blog/media")
@app.post("/api/admin/blog/media/")
async def admin_upload_media(
    file: UploadFile = File(...),
    alt_text: Optional[str] = Form(None),
    current_user: dict = Depends(get_admin_user)
):
    """Upload media - handles both trailing slash variations"""
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type")

    file_path = save_upload_file_sync(file, "blog")
    file_size = os.path.getsize(file_path)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO blog_media (uploaded_by, filename, original_name, file_path, file_size, mime_type, alt_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (current_user["id"], os.path.basename(file_path), file.filename, file_path, file_size, file.content_type, alt_text))

        media_id = cursor.lastrowid
        conn.commit()

        return {
            "id": media_id,
            "url": f"/uploads/{os.path.basename(file_path)}",
            "filename": os.path.basename(file_path)
        }

# =============================================================================
# ADMIN ENDPOINTS - COURSE MANAGEMENT
# =============================================================================

@app.post("/api/admin/courses")
@app.post("/api/admin/courses/")
async def admin_create_course(
    course: CourseCreate,
    current_user: dict = Depends(get_admin_user)
):
    """Create course - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()
        slug = course.slug or generate_slug(course.title)

        cursor.execute("SELECT id FROM courses WHERE slug = ?", (slug,))
        if cursor.fetchone():
            slug = f"{slug}-{uuid.uuid4().hex[:8]}"

        cursor.execute("""
            INSERT INTO courses (
                instructor_id, title, slug, description, short_description,
                thumbnail_url, preview_video_url, category, level, price,
                duration_hours, seo_title, seo_description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            current_user["id"], course.title, slug, course.description,
            course.short_description, course.thumbnail_url, course.preview_video_url,
            course.category, course.level, course.price, course.duration_hours,
            course.seo_title, course.seo_description
        ))

        course_id = cursor.lastrowid
        conn.commit()

        return {"id": course_id, "slug": slug, "message": "Course created"}

@app.put("/api/admin/courses/{course_id}")
async def admin_update_course(
    course_id: int,
    course: CourseUpdate,
    current_user: dict = Depends(get_admin_user)
):
    """Update course"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM courses WHERE id = ?", (course_id,))
        existing = cursor.fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Course not found")

        update_fields = []
        params = []

        fields = [
            ("title", course.title),
            ("description", course.description),
            ("short_description", course.short_description),
            ("thumbnail_url", course.thumbnail_url),
            ("preview_video_url", course.preview_video_url),
            ("category", course.category),
            ("level", course.level),
            ("price", course.price),
            ("duration_hours", course.duration_hours),
            ("is_published", course.is_published),
            ("is_featured", course.is_featured),
            ("seo_title", course.seo_title),
            ("seo_description", course.seo_description),
        ]

        for field, value in fields:
            if value is not None:
                update_fields.append(f"{field} = ?")
                params.append(value)

        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")

        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(course_id)

        cursor.execute(f"""
            UPDATE courses SET {', '.join(update_fields)} WHERE id = ?
        """, params)

        conn.commit()
        return {"message": "Course updated"}

@app.delete("/api/admin/courses/{course_id}")
async def admin_delete_course(course_id: int, current_user: dict = Depends(get_admin_user)):
    """Delete course"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM courses WHERE id = ?", (course_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Course not found")
        conn.commit()
        return {"message": "Course deleted"}

@app.post("/api/admin/courses/{course_id}/modules")
@app.post("/api/admin/courses/{course_id}/modules/")
async def admin_create_module(
    course_id: int,
    module: ModuleCreate,
    current_user: dict = Depends(get_admin_user)
):
    """Create module - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM courses WHERE id = ?", (course_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Course not found")

        cursor.execute("""
            INSERT INTO course_modules (course_id, title, description, sort_order)
            VALUES (?, ?, ?, ?)
        """, (course_id, module.title, module.description, module.sort_order))

        module_id = cursor.lastrowid
        conn.commit()
        return {"id": module_id, "message": "Module created"}

@app.post("/api/admin/modules/{module_id}/lessons")
@app.post("/api/admin/modules/{module_id}/lessons/")
async def admin_create_lesson(
    module_id: int,
    lesson: LessonCreate,
    current_user: dict = Depends(get_admin_user)
):
    """Create lesson - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM course_modules WHERE id = ?", (module_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Module not found")

        cursor.execute("""
            INSERT INTO course_lessons (module_id, title, description, content, video_url, video_duration, is_preview, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (module_id, lesson.title, lesson.description, lesson.content,
              lesson.video_url, lesson.video_duration, lesson.is_preview, lesson.sort_order))

        lesson_id = cursor.lastrowid
        conn.commit()
        return {"id": lesson_id, "message": "Lesson created"}

# =============================================================================
# ADMIN ENDPOINTS - USER MANAGEMENT
# =============================================================================

@app.get("/api/admin/users")
@app.get("/api/admin/users/")
async def admin_list_users(
    role: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    current_user: dict = Depends(get_admin_user)
):
    """List users - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()
        where_clauses = []
        params = []

        if role:
            where_clauses.append("role = ?")
            params.append(role)
        if search:
            where_clauses.append("(email LIKE ? OR full_name LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Get total count
        cursor.execute(f"SELECT COUNT(*) as total FROM users WHERE {where_sql}", params)
        total = cursor.fetchone()["total"]

        # Get users with pagination
        offset = (page - 1) * per_page
        cursor.execute(f"""
            SELECT id, email, full_name, role, is_active, created_at, last_login_at
            FROM users
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset])

        users = cursor.fetchall()

        return {
            "users": [dict(u) for u in users],
            "total": total,
            "page": page,
            "per_page": per_page
        }

@app.put("/api/admin/users/{user_id}")
async def admin_update_user(
    user_id: int,
    role: Optional[str] = Form(None),
    is_active: Optional[bool] = Form(None),
    current_user: dict = Depends(get_admin_user)
):
    """Update user"""
    with get_db() as conn:
        cursor = conn.cursor()

        if user_id == current_user["id"] and role and role != "admin":
            raise HTTPException(status_code=400, detail="Cannot remove your own admin role")

        update_fields = []
        params = []

        if role is not None:
            update_fields.append("role = ?")
            params.append(role)
        if is_active is not None:
            update_fields.append("is_active = ?")
            params.append(is_active)

        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")

        params.append(user_id)

        cursor.execute(f"""
            UPDATE users SET {', '.join(update_fields)} WHERE id = ?
        """, params)

        conn.commit()
        return {"message": "User updated"}

# =============================================================================
# ADMIN DASHBOARD ENDPOINTS
# =============================================================================

@app.get("/api/admin/dashboard/stats")
@app.get("/api/admin/dashboard/stats/")
async def admin_dashboard_stats(current_user: dict = Depends(get_admin_user)):
    """Dashboard stats - handles both trailing slash variations"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as total FROM users")
        total_users = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM trades")
        total_trades = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM courses")
        total_courses = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM blog_posts")
        total_posts = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM users WHERE DATE(created_at) = DATE('now')")
        new_users_today = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM trades WHERE DATE(created_at) = DATE('now')")
        new_trades_today = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM user_enrollments")
        enrollments = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT id, email, full_name, role, created_at
            FROM users
            ORDER BY created_at DESC LIMIT 5
        """)
        recent_users = cursor.fetchall()

        return {
            "overview": {
                "total_users": total_users,
                "total_trades": total_trades,
                "total_courses": total_courses,
                "total_posts": total_posts,
                "new_users_today": new_users_today,
                "new_trades_today": new_trades_today,
                "total_enrollments": enrollments
            },
            "recent_users": [dict(u) for u in recent_users]
        }

# =============================================================================
# SPA CATCH-ALL MUST BE LAST
# =============================================================================

@app.get("/{path:path}")
async def serve_spa_routes(path: str):
    """
    Serve SPA for all non-API routes. This MUST be defined AFTER all API routes.
    """
    # Skip API routes - they should have been caught above
    if path.startswith("api/") or path.startswith("health") or path.startswith("uploads/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")

    try:
        with open("index.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="""<h1>Pipways API v3.0</h1>
<p>Frontend not built yet. API is running correctly.</p>
<p>Default admin credentials: admin@pipways.com / admin123</p>
""")

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
