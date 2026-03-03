"""
Pipways - Forex Trading Journal API
Complete implementation with Admin Dashboard, Email, Paystack, Notifications, Analytics
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
from enum import Enum

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Header, status, Request, BackgroundTasks, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from pydantic import BaseModel, EmailStr, Field, validator
from passlib.context import CryptContext
from jose import JWTError, jwt
from PIL import Image

# =============================================================================
# CONFIGURATION & LOGGING
# =============================================================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/pipways")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
FRONTEND_URL = os.getenv("FRONTEND_URL", "")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")

# JWT Configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database pool
db_pool: Optional[asyncpg.Pool] = None

# In-memory cache
cache_store: Dict[str, Any] = {}
cache_expiry: Dict[str, datetime] = {}

# Rate limiting store
rate_limit_store: Dict[str, List[datetime]] = {}

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
                requests = [r for r in rate_limit_store.get(key, []) if r > window_start]
                if len(requests) >= max_requests:
                    raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Try again in {window_seconds} seconds.")
                requests.append(now)
                rate_limit_store[key] = requests
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# =============================================================================
# DATABASE SETUP - FIXED WITH ALL COLUMNS
# =============================================================================

async def init_db_pool():
    global db_pool
    try:
        ssl_mode = "require" if ENVIRONMENT == "production" else "prefer"
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10, command_timeout=60, ssl=ssl_mode)
        logger.info("Database pool initialized")
        await create_tables()
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        db_pool = None

async def create_tables():
    if not db_pool:
        return

    async with db_pool.acquire() as conn:
        # Users table with ALL required columns
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
                email_verified BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Add missing columns if they don't exist
        columns_to_add = [
            ("is_admin", "BOOLEAN DEFAULT FALSE"),
            ("subscription_status", "VARCHAR(50) DEFAULT 'trial'"),
            ("subscription_ends_at", "TIMESTAMP"),
            ("trial_ends_at", "TIMESTAMP"),
            ("email_verified", "BOOLEAN DEFAULT FALSE")
        ]

        for col_name, col_type in columns_to_add:
            try:
                await conn.fetch(f"SELECT {col_name} FROM users LIMIT 1")
            except:
                await conn.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                logger.info(f"Added column: {col_name}")

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
                status VARCHAR(50) NOT NULL,
                error_message TEXT,
                sent_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Insert sample data if empty
        await insert_sample_data(conn)

        logger.info("Database tables created/verified successfully")

async def insert_sample_data(conn):
    # Sample courses
    course_count = await conn.fetchval("SELECT COUNT(*) FROM courses")
    if course_count == 0:
        await conn.execute("""
            INSERT INTO courses (title, description, category, level, lessons, quiz_questions, passing_score) VALUES
            ('Forex Fundamentals', 'Learn the basics of forex trading', 'basics', 'beginner', 
             '[{"id": 1, "title": "What is Forex?", "duration": "10 min"}, {"id": 2, "title": "Currency Pairs", "duration": "15 min"}]'::jsonb,
             '[{"question": "What does EUR/USD represent?", "options": ["Euro vs US Dollar", "US Dollar vs Euro"], "correct": 0}]'::jsonb, 70),
            ('Technical Analysis', 'Master chart patterns and indicators', 'technical', 'intermediate',
             '[{"id": 1, "title": "Support and Resistance", "duration": "20 min"}]'::jsonb, '[]'::jsonb, 70),
            ('Risk Management', 'Protect your capital', 'risk', 'beginner',
             '[{"id": 1, "title": "Position Sizing", "duration": "25 min"}]'::jsonb, '[]'::jsonb, 80)
        """)

    # Sample webinars
    webinar_count = await conn.fetchval("SELECT COUNT(*) FROM webinars")
    if webinar_count == 0:
        await conn.execute("""
            INSERT INTO webinars (title, description, level, scheduled_at, zoom_join_url) VALUES
            ('Live Trading Session', 'Join us for live market analysis', 'all_levels', NOW() + INTERVAL '7 days', 'https://zoom.us/j/example'),
            ('Q&A with Pro Traders', 'Ask questions from experienced traders', 'all_levels', NOW() + INTERVAL '14 days', 'https://zoom.us/j/example2')
        """)

    # Sample blog posts
    blog_count = await conn.fetchval("SELECT COUNT(*) FROM blog_posts")
    if blog_count == 0:
        await conn.execute("""
            INSERT INTO blog_posts (title, slug, content, excerpt, category, published) VALUES
            ('Getting Started with Forex Trading', 'getting-started-forex', 
             'Forex trading is the exchange of currencies...', 'Learn the basics of forex trading', 'basics', TRUE),
            ('Top 5 Risk Management Strategies', 'risk-management-strategies',
             'Risk management is crucial for trading success...', 'Essential risk management tips', 'risk', TRUE)
        """)

    # Create default admin user if not exists
    admin_exists = await conn.fetchval("SELECT id FROM users WHERE email = 'admin@pipways.com'")
    if not admin_exists:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        hashed_password = pwd_context.hash("admin123")
        
        admin_id = await conn.fetchval(
            """INSERT INTO users (name, email, password_hash, is_admin, subscription_status, trial_ends_at) 
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
            "Admin", "admin@pipways.com", hashed_password, True, "active", 
            datetime.utcnow() + timedelta(days=365*10)  # 10 year trial for admin
        )
        logger.info(f"Default admin user created with ID: {admin_id}")
    else:
        # Ensure admin user has admin privileges
        await conn.execute("UPDATE users SET is_admin = TRUE WHERE email = 'admin@pipways.com'")
        logger.info("Default admin user already exists, ensured admin privileges")

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

app = FastAPI(title="Pipways API", description="Forex Trading Journal and Educational Platform", version="2.0.0", lifespan=lifespan)

# CORS Configuration - Allow all origins for debugging
origins = ["*"]
if FRONTEND_URL and FRONTEND_URL != "*":
    origins = ["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:3000", "http://127.0.0.1:8000",
               "https://pipways-web.onrender.com", "https://pipways-web-nhem.onrender.com", 
               "https://www.pipways.com", "https://pipways.com", FRONTEND_URL]

app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"], expose_headers=["*"])

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
    is_admin: bool
    subscription_status: str
    trial_ends_at: Optional[str] = None
    subscription_ends_at: Optional[str] = None

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password[:72], hashed_password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
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
                """SELECT id, email, name, is_admin, subscription_status, trial_ends_at, subscription_ends_at 
                   FROM users WHERE id = $1""", int(user_id))
            if user is None:
                raise HTTPException(status_code=401, detail="User not found")
            return dict(user)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_admin_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    user = await get_current_user(credentials)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

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
                headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
                json={
                    "personalizations": [{"to": [{"email": recipient}]}],
                    "from": {"email": "noreply@pipways.com", "name": "Pipways"},
                    "subject": subject,
                    "content": [{"type": "text/html", "value": content}]
                }
            )

            async with db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO email_logs (user_id, email_type, recipient, subject, status) VALUES ($1, $2, $3, $4, $5)",
                    user_id, email_type, recipient, subject, "sent" if response.status_code == 202 else "failed"
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
            <a href="{FRONTEND_URL}" style="background: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin-top: 20px;">Get Started</a>
        </div>
    </body>
    </html>
    """
    return await send_email(user_id, "welcome", email, "Welcome to Pipways!", content)

# =============================================================================
# NOTIFICATION SERVICE
# =============================================================================

async def create_notification(user_id: int, type: str, title: str, message: str, data: dict = None):
    """Create a notification for a user"""
    if not db_pool:
        return
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO notifications (user_id, type, title, message, data) VALUES ($1, $2, $3, $4, $5)",
            user_id, type, title, message, json.dumps(data) if data else None
        )

# =============================================================================
# HEALTH & DEBUG ENDPOINTS
# =============================================================================

@app.get("/health")
async def health_check():
    try:
        if db_pool:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        return {"status": "healthy", "timestamp": datetime.utcnow().isoformat(), "database": "connected" if db_pool else "not_connected"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})

@app.get("/debug")
async def debug_info():
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
# AUTHENTICATION ENDPOINTS
# =============================================================================

@app.post("/auth/register", response_model=TokenResponse)
@rate_limit(max_requests=3, window_seconds=60)
async def register(request: Request, email: str = Form(...), password: str = Form(...), name: str = Form(...)):
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not connected")

    try:
        email = email.lower().strip()
        if '@' not in email or '.' not in email.split('@')[1]:
            raise HTTPException(status_code=400, detail="Invalid email format")
        if len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        if len(name.strip()) < 2:
            raise HTTPException(status_code=400, detail="Name must be at least 2 characters")

        async with db_pool.acquire() as conn:
            existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", email)
            if existing:
                raise HTTPException(status_code=400, detail="Email already registered")

            password_hash = hash_password(password)
            trial_ends = datetime.utcnow() + timedelta(days=3)

            user_id = await conn.fetchval(
                "INSERT INTO users (email, password_hash, name, trial_ends_at, is_admin, subscription_status) VALUES ($1, $2, $3, $4, FALSE, 'trial') RETURNING id",
                email, password_hash, name.strip(), trial_ends
            )

            token = create_access_token({"sub": str(user_id)})

            # Send welcome email in background
            await send_welcome_email(user_id, email, name.strip())

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
            user = await conn.fetchrow(
                """SELECT id, email, password_hash, name, is_admin, subscription_status, trial_ends_at, subscription_ends_at 
                   FROM users WHERE email = $1""", email
            )

            if not user or not verify_password(password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="Invalid email or password")

            token = create_access_token({"sub": str(user["id"])})

            return {
                "access_token": token,
                "token_type": "bearer",
                "id": user["id"],
                "email": user["email"],
                "name": user["name"],
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

# =============================================================================
# TRADES ENDPOINTS
# =============================================================================

@app.get("/trades")
async def get_trades(current_user: dict = Depends(get_current_user)):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    cache_key = f"trades:{current_user['id']}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM trades WHERE user_id = $1 ORDER BY created_at DESC", current_user["id"])
        result = [dict(row) for row in rows]
        cache_set(cache_key, result, 300)
        return result

@app.post("/trades")
async def create_trade(
    pair: str = Form(...),
    direction: str = Form(...),
    pips: float = Form(...),
    grade: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        # Check trial limit
        if current_user.get("subscription_status") == "trial":
            trade_count = await conn.fetchval("SELECT COUNT(*) FROM trades WHERE user_id = $1", current_user["id"])
            if trade_count >= 5:
                raise HTTPException(status_code=403, detail="Trial limit reached (5 trades). Upgrade to Pro.")

        trade_id = await conn.fetchval(
            "INSERT INTO trades (user_id, pair, direction, pips, grade) VALUES ($1, $2, $3, $4, $5) RETURNING id",
            current_user["id"], pair.upper(), direction.upper(), pips, grade.upper()
        )

        cache_delete(f"trades:{current_user['id']}")
        cache_delete(f"analytics:{current_user['id']}")

        # Create notification
        await create_notification(current_user["id"], "trade", "Trade Logged", f"You logged a {direction} trade on {pair}")

        return {"id": trade_id, "message": "Trade created successfully"}

@app.get("/trades/export")
async def export_trades(format: str = "csv", current_user: dict = Depends(get_current_user)):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

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
            writer.writerow([row["pair"], row["direction"], row["pips"], row["grade"], row["entry_price"], row["exit_price"], row["created_at"].isoformat()])

        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=trades_{datetime.now().strftime('%Y-%m-%d')}.csv"}
        )
    raise HTTPException(status_code=400, detail="Format not supported")

# =============================================================================
# ANALYTICS ENDPOINTS
# =============================================================================

@app.get("/analytics/dashboard")
async def get_analytics(current_user: dict = Depends(get_current_user)):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    cache_key = f"analytics:{current_user['id']}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    async with db_pool.acquire() as conn:
        trades = await conn.fetch("SELECT * FROM trades WHERE user_id = $1 ORDER BY created_at", current_user["id"])

        if not trades:
            return {"total_trades": 0, "win_rate": 0, "total_pips": 0, "profit_factor": 0, "equity_curve": [], "monthly_performance": [], "pair_performance": []}

        total_trades = len(trades)
        wins = sum(1 for t in trades if t["pips"] > 0)
        win_rate = round((wins / total_trades) * 100, 1)
        total_pips = sum(t["pips"] for t in trades)

        winning_pips = sum(t["pips"] for t in trades if t["pips"] > 0)
        losing_pips = abs(sum(t["pips"] for t in trades if t["pips"] < 0))
        profit_factor = round(winning_pips / losing_pips, 2) if losing_pips > 0 else winning_pips

        cumulative = 0
        equity_curve = []
        for trade in trades:
            cumulative += trade["pips"]
            equity_curve.append({"date": trade["created_at"].isoformat(), "cumulative_pips": round(cumulative, 2)})

        monthly = {}
        for trade in trades:
            month = trade["created_at"].strftime("%Y-%m")
            if month not in monthly:
                monthly[month] = {"pips": 0, "trades": 0}
            monthly[month]["pips"] += trade["pips"]
            monthly[month]["trades"] += 1

        monthly_performance = [{"month": k, "pips": round(v["pips"], 2), "trades": v["trades"]} for k, v in sorted(monthly.items())]

        pair_stats = {}
        for trade in trades:
            pair = trade["pair"]
            if pair not in pair_stats:
                pair_stats[pair] = {"trades": 0, "wins": 0, "total_pips": 0}
            pair_stats[pair]["trades"] += 1
            if trade["pips"] > 0:
                pair_stats[pair]["wins"] += 1
            pair_stats[pair]["total_pips"] += trade["pips"]

        pair_performance = [{"pair": k, "trades": v["trades"], "win_rate": round((v["wins"] / v["trades"]) * 100, 1), "total_pips": round(v["total_pips"], 2)} for k, v in pair_stats.items()]

        result = {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "total_pips": round(total_pips, 2),
            "profit_factor": profit_factor,
            "equity_curve": equity_curve,
            "monthly_performance": monthly_performance,
            "pair_performance": pair_performance
        }

        cache_set(cache_key, result, 300)
        return result

# =============================================================================
# COURSES ENDPOINTS
# =============================================================================

@app.get("/courses")
async def get_courses(current_user: dict = Depends(get_current_user)):
    cache_key = "courses:all"
    cached = cache_get(cache_key)

    async with db_pool.acquire() as conn:
        courses = await conn.fetch("SELECT * FROM courses ORDER BY created_at DESC")
        user_courses = await conn.fetch("SELECT * FROM user_courses WHERE user_id = $1", current_user["id"])
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
                "certificate_issued": progress.get("certificate_issued", False)
            })

        cache_set(cache_key, result, 3600)
        return result

@app.post("/courses/{course_id}/enroll")
async def enroll_course(course_id: int, current_user: dict = Depends(get_current_user)):
    async with db_pool.acquire() as conn:
        existing = await conn.fetchval("SELECT id FROM user_courses WHERE user_id = $1 AND course_id = $2", current_user["id"], course_id)
        if existing:
            return {"message": "Already enrolled"}

        await conn.execute("INSERT INTO user_courses (user_id, course_id) VALUES ($1, $2)", current_user["id"], course_id)
        cache_delete("courses:all")

        # Create notification
        course = await conn.fetchrow("SELECT title FROM courses WHERE id = $1", course_id)
        await create_notification(current_user["id"], "course", "Course Enrolled", f"You enrolled in {course['title']}")

        return {"message": "Enrolled successfully"}

# =============================================================================
# WEBINARS ENDPOINTS
# =============================================================================

@app.get("/webinars")
async def get_webinars(current_user: dict = Depends(get_current_user)):
    cache_key = "webinars:all"
    cached = cache_get(cache_key)

    async with db_pool.acquire() as conn:
        webinars = await conn.fetch("""
            SELECT w.*, COUNT(wr.id) as registered_count
            FROM webinars w
            LEFT JOIN webinar_registrations wr ON w.id = wr.webinar_id
            GROUP BY w.id
            ORDER BY w.scheduled_at ASC
        """)

        user_regs = await conn.fetch("SELECT webinar_id FROM webinar_registrations WHERE user_id = $1", current_user["id"])
        registered_ids = {r["webinar_id"] for r in user_regs}

        result = []
        now = datetime.utcnow()
        for webinar in webinars:
            scheduled = webinar["scheduled_at"]
            is_live = scheduled <= now < scheduled + timedelta(hours=2)

            time_until = {"days": 0, "hours": 0, "minutes": 0}
            if scheduled > now:
                diff = scheduled - now
                time_until = {"days": diff.days, "hours": diff.seconds // 3600, "minutes": (diff.seconds % 3600) // 60}

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

@app.post("/webinars/{webinar_id}/register")
async def register_webinar(webinar_id: int, current_user: dict = Depends(get_current_user)):
    async with db_pool.acquire() as conn:
        existing = await conn.fetchval("SELECT id FROM webinar_registrations WHERE user_id = $1 AND webinar_id = $2", current_user["id"], webinar_id)
        if existing:
            return {"message": "Already registered"}

        await conn.execute("INSERT INTO webinar_registrations (user_id, webinar_id) VALUES ($1, $2)", current_user["id"], webinar_id)
        cache_delete("webinars:all")

        webinar = await conn.fetchrow("SELECT title, scheduled_at FROM webinars WHERE id = $1", webinar_id)
        await create_notification(current_user["id"], "webinar", "Webinar Registered", f"You registered for {webinar['title']}", {"scheduled_at": webinar["scheduled_at"].isoformat()})

        return {"message": "Registered successfully"}

# =============================================================================
# AI ANALYSIS ENDPOINTS
# =============================================================================

async def call_openrouter(prompt: str, max_tokens: int = 1000) -> str:
    if not OPENROUTER_API_KEY:
        return "AI service not configured."
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://pipways.com",
                    "X-Title": "Pipways"
                },
                json={
                    "model": "anthropic/claude-3.5-sonnet",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens
                }
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            return "AI service temporarily unavailable."
    except Exception as e:
        logger.error(f"OpenRouter error: {e}")
        return "AI service error."

@app.post("/analyze-chart")
async def analyze_chart(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    try:
        contents = await file.read()
        img = Image.open(io.BytesIO(contents))

        max_size = (1200, 800)
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Mock analysis (replace with actual AI call)
        analysis = {
            "setup_quality": "B",
            "pair": "EURUSD",
            "direction": "LONG",
            "entry_price": "1.0850",
            "stop_loss": "1.0820",
            "take_profit": "1.0900",
            "risk_reward": "1:1.67",
            "analysis": "Price is testing support at 1.0850 with bullish divergence on RSI. Good risk:reward setup.",
            "recommendations": "Consider entering on confirmation candle close above 1.0855.",
            "key_levels": ["1.0850 (Support)", "1.0900 (Resistance)", "1.0820 (Stop)"]
        }

        return {"analysis": analysis}
    except Exception as e:
        logger.error(f"Chart analysis error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze chart")

@app.post("/performance/analyze")
async def analyze_performance(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with db_pool.acquire() as conn:
        # Check trial limit
        if current_user.get("subscription_status") == "trial":
            analysis_count = await conn.fetchval("SELECT COUNT(*) FROM performance_analyses WHERE user_id = $1", current_user["id"])
            if analysis_count >= 1:
                raise HTTPException(status_code=403, detail="Trial limit reached (1 analysis). Upgrade to Pro.")

        # Get user's trades for analysis
        trades = await conn.fetch("SELECT * FROM trades WHERE user_id = $1 ORDER BY created_at", current_user["id"])

        # Generate analysis
        analysis = {
            "performance_score": 72,
            "trader_type": "Trend Following Scalper",
            "risk_appetite": "Moderate",
            "score_breakdown": {"profitability": 75, "risk_management": 68, "consistency": 70, "psychology": 75},
            "strengths": ["Good win rate on trending markets", "Disciplined stop loss placement", "Consistent position sizing"],
            "weaknesses": ["Overtrading during consolidation", "Missing major moves due to early exits", "Revenge trading after losses"],
            "suggested_goal": {"id": "reduce_trades", "title": "Reduce Daily Trades by 30%", "description": "Focus on quality over quantity"}
        }

        await conn.execute(
            "INSERT INTO performance_analyses (user_id, file_name, analysis_result, trader_type, performance_score, risk_appetite) VALUES ($1, $2, $3, $4, $5, $6)",
            current_user["id"], file.filename, json.dumps(analysis), analysis["trader_type"], analysis["performance_score"], analysis["risk_appetite"]
        )

        # Create notification
        await create_notification(current_user["id"], "analysis", "Analysis Complete", f"Your performance score is {analysis['performance_score']}/100")

        return {"analysis": analysis}

@app.get("/performance/history")
async def get_performance_history(current_user: dict = Depends(get_current_user)):
    async with db_pool.acquire() as conn:
        history = await conn.fetch("""
            SELECT id, performance_score, analysis_result, created_at
            FROM performance_analyses WHERE user_id = $1 ORDER BY created_at DESC LIMIT 10
        """, current_user["id"])

        result = []
        for h in history:
            analysis = json.loads(h["analysis_result"]) if isinstance(h["analysis_result"], str) else h["analysis_result"]
            result.append({"id": h["id"], "performance_score": h["performance_score"], "score_breakdown": analysis.get("score_breakdown", {}), "created_at": h["created_at"].isoformat()})

        improvement = 0
        if len(result) >= 2:
            improvement = result[0]["performance_score"] - result[-1]["performance_score"]

        return {"history": result, "improvement": improvement, "trend": "improving" if improvement > 0 else "declining" if improvement < 0 else "stable"}

@app.get("/mentor-chat")
async def mentor_chat(message: str, current_user: dict = Depends(get_current_user)):
    prompt = f"You are an experienced forex trading mentor. The trader asks: '{message}'. Provide helpful, practical advice in 2-3 paragraphs."
    response = await call_openrouter(prompt, max_tokens=500)
    return {"response": response}

# =============================================================================
# SUBSCRIPTION & PAYMENT ENDPOINTS (PAYSTACK)
# =============================================================================

@app.get("/subscription/status")
async def get_subscription_status(current_user: dict = Depends(get_current_user)):
    return {
        "subscription_status": current_user.get("subscription_status"),
        "trial_ends_at": current_user.get("trial_ends_at"),
        "subscription_ends_at": current_user.get("subscription_ends_at")
    }

@app.post("/subscription/initiate")
async def initiate_payment(current_user: dict = Depends(get_current_user)):
    """Initiate Paystack payment for Pro subscription"""
    if not PAYSTACK_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payment service not configured")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.paystack.co/transaction/initialize",
                headers={"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}", "Content-Type": "application/json"},
                json={
                    "email": current_user["email"],
                    "amount": 1500,  # $15.00 in cents
                    "callback_url": f"{FRONTEND_URL}/subscription/verify",
                    "metadata": {"user_id": current_user["id"], "plan": "pro"}
                }
            )

            data = response.json()
            if data.get("status"):
                # Save payment reference
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO payments (user_id, paystack_reference, amount, status) VALUES ($1, $2, $3, $4)",
                        current_user["id"], data["data"]["reference"], 15.00, "pending"
                    )
                return {"authorization_url": data["data"]["authorization_url"], "reference": data["data"]["reference"]}
            else:
                raise HTTPException(status_code=400, detail="Payment initialization failed")
    except Exception as e:
        logger.error(f"Payment initiation error: {e}")
        raise HTTPException(status_code=500, detail="Payment service error")

@app.post("/subscription/verify")
async def verify_payment(reference: str = Form(...), current_user: dict = Depends(get_current_user)):
    """Verify Paystack payment and activate subscription"""
    if not PAYSTACK_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payment service not configured")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.paystack.co/transaction/verify/{reference}",
                headers={"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
            )

            data = response.json()
            if data.get("status") and data["data"]["status"] == "success":
                async with db_pool.acquire() as conn:
                    # Update payment status
                    await conn.execute(
                        "UPDATE payments SET status = $1, paystack_transaction_id = $2, paid_at = NOW() WHERE paystack_reference = $3",
                        "success", data["data"]["id"], reference
                    )

                    # Activate subscription
                    subscription_ends = datetime.utcnow() + timedelta(days=30)
                    await conn.execute(
                        "UPDATE users SET subscription_status = $1, subscription_ends_at = $2 WHERE id = $3",
                        "active", subscription_ends, current_user["id"]
                    )

                    # Send confirmation email
                    await send_email(current_user["id"], "subscription_activated", current_user["email"], 
                                   "Welcome to Pipways Pro!", f"<h1>Your Pro subscription is active!</h1><p>Valid until {subscription_ends.strftime('%Y-%m-%d')}</p>")

                    # Create notification
                    await create_notification(current_user["id"], "subscription", "Pro Activated", "Your Pro subscription is now active!")

                return {"status": "success", "message": "Subscription activated"}
            else:
                raise HTTPException(status_code=400, detail="Payment verification failed")
    except Exception as e:
        logger.error(f"Payment verification error: {e}")
        raise HTTPException(status_code=500, detail="Payment verification error")

# =============================================================================
# NOTIFICATIONS ENDPOINTS
# =============================================================================

@app.get("/notifications")
async def get_notifications(unread_only: bool = False, current_user: dict = Depends(get_current_user)):
    async with db_pool.acquire() as conn:
        if unread_only:
            rows = await conn.fetch(
                "SELECT * FROM notifications WHERE user_id = $1 AND read = FALSE ORDER BY created_at DESC",
                current_user["id"]
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM notifications WHERE user_id = $1 ORDER BY created_at DESC LIMIT 50",
                current_user["id"]
            )
        return [dict(r) for r in rows]

@app.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: int, current_user: dict = Depends(get_current_user)):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE notifications SET read = TRUE WHERE id = $1 AND user_id = $2",
            notification_id, current_user["id"]
        )
    return {"message": "Notification marked as read"}

@app.get("/notifications/unread-count")
async def get_unread_count(current_user: dict = Depends(get_current_user)):
    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM notifications WHERE user_id = $1 AND read = FALSE",
            current_user["id"]
        )
    return {"unread_count": count}

@app.post("/notifications/read-all")
async def mark_all_notifications_read(current_user: dict = Depends(get_current_user)):
    """Mark all notifications as read for current user"""
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE notifications SET read = TRUE WHERE user_id = $1 AND read = FALSE",
            current_user["id"]
        )
    return {"message": "All notifications marked as read"}

# =============================================================================
# USER ENDPOINTS
# =============================================================================

@app.get("/users/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    return {
        "id": current_user["id"],
        "name": current_user["name"],
        "email": current_user["email"],
        "is_admin": current_user.get("is_admin", False),
        "subscription_status": current_user.get("subscription_status", "trial"),
        "subscription_ends_at": current_user.get("subscription_ends_at"),
        "trial_ends_at": current_user.get("trial_ends_at"),
        "email_verified": current_user.get("email_verified", False)
    }

# =============================================================================
# BLOG ENDPOINTS
# =============================================================================

@app.get("/blog/posts")
async def get_blog_posts(category: Optional[str] = None):
    cache_key = f"blog:posts:{category or 'all'}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    async with db_pool.acquire() as conn:
        if category:
            posts = await conn.fetch("SELECT * FROM blog_posts WHERE published = TRUE AND category = $1 ORDER BY created_at DESC", category)
        else:
            posts = await conn.fetch("SELECT * FROM blog_posts WHERE published = TRUE ORDER BY created_at DESC")

        result = [dict(p) for p in posts]
        cache_set(cache_key, result, 3600)
        return result

@app.get("/blog/posts/{slug}")
async def get_blog_post(slug: str):
    async with db_pool.acquire() as conn:
        post = await conn.fetchrow("SELECT * FROM blog_posts WHERE slug = $1 AND published = TRUE", slug)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        await conn.execute("UPDATE blog_posts SET view_count = view_count + 1 WHERE id = $1", post["id"])
        return dict(post)

# =============================================================================
# ADMIN DASHBOARD ENDPOINTS
# =============================================================================

@app.get("/admin/stats")
async def get_admin_stats(admin_user: dict = Depends(get_admin_user)):
    """Get comprehensive platform statistics"""
    async with db_pool.acquire() as conn:
        stats = {
            "total_users": await conn.fetchval("SELECT COUNT(*) FROM users"),
            "new_users_7d": await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '7 days'"),
            "new_users_30d": await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '30 days'"),
            "active_subscriptions": await conn.fetchval("SELECT COUNT(*) FROM users WHERE subscription_status = 'active' AND subscription_ends_at > NOW()"),
            "trial_users": await conn.fetchval("SELECT COUNT(*) FROM users WHERE subscription_status = 'trial' AND trial_ends_at > NOW()"),
            "expired_trials": await conn.fetchval("SELECT COUNT(*) FROM users WHERE subscription_status = 'trial' AND trial_ends_at < NOW()"),
            "total_trades": await conn.fetchval("SELECT COUNT(*) FROM trades"),
            "trades_7d": await conn.fetchval("SELECT COUNT(*) FROM trades WHERE created_at > NOW() - INTERVAL '7 days'"),
            "trades_30d": await conn.fetchval("SELECT COUNT(*) FROM trades WHERE created_at > NOW() - INTERVAL '30 days'"),
            "total_courses": await conn.fetchval("SELECT COUNT(*) FROM courses"),
            "total_webinars": await conn.fetchval("SELECT COUNT(*) FROM webinars"),
            "total_blog_posts": await conn.fetchval("SELECT COUNT(*) FROM blog_posts"),
            "published_blog_posts": await conn.fetchval("SELECT COUNT(*) FROM blog_posts WHERE published = TRUE"),
            "total_revenue": await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'success'"),
            "revenue_30d": await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'success' AND created_at > NOW() - INTERVAL '30 days'"),
        }

        # Recent activity
        recent_users = await conn.fetch("SELECT id, name, email, subscription_status, created_at FROM users ORDER BY created_at DESC LIMIT 10")
        recent_trades = await conn.fetch("""
            SELECT t.*, u.name as user_name 
            FROM trades t 
            JOIN users u ON t.user_id = u.id 
            ORDER BY t.created_at DESC LIMIT 10
        """)

        stats["recent_users"] = [dict(u) for u in recent_users]
        stats["recent_trades"] = [dict(t) for t in recent_trades]

        return stats

@app.post("/admin/send-email")
async def admin_send_email(
    recipient: str = Form(...),
    subject: str = Form(...),
    content: str = Form(...),
    admin_user: dict = Depends(get_admin_user)
):
    """Send email to user(s) from admin panel"""
    async with db_pool.acquire() as conn:
        if recipient.lower() == "all":
            # Send to all users
            users = await conn.fetch("SELECT email FROM users WHERE email IS NOT NULL")
            emails_sent = 0
            for user in users:
                await create_notification(
                    user_id=0,  # System notification
                    notification_type="system",
                    title=subject,
                    message=content
                )
                emails_sent += 1
            return {"message": f"Notification sent to {emails_sent} users"}
        else:
            # Send to specific user
            user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", recipient)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            await create_notification(
                user_id=user["id"],
                notification_type="system",
                title=subject,
                message=content
            )
            return {"message": f"Notification sent to {recipient}"}

@app.get("/admin/users")
async def get_admin_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    admin_user: dict = Depends(get_admin_user)
):
    """Get all users for admin management"""
    async with db_pool.acquire() as conn:
        offset = (page - 1) * limit

        if search:
            rows = await conn.fetch(
                """SELECT id, name, email, subscription_status, is_admin, created_at, trial_ends_at, subscription_ends_at
                   FROM users WHERE name ILIKE $1 OR email ILIKE $1 
                   ORDER BY created_at DESC LIMIT $2 OFFSET $3""",
                f"%{search}%", limit, offset
            )
            total = await conn.fetchval("SELECT COUNT(*) FROM users WHERE name ILIKE $1 OR email ILIKE $1", f"%{search}%")
        else:
            rows = await conn.fetch(
                """SELECT id, name, email, subscription_status, is_admin, created_at, trial_ends_at, subscription_ends_at
                   FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2""",
                limit, offset
            )
            total = await conn.fetchval("SELECT COUNT(*) FROM users")

        return {"users": [dict(r) for r in rows], "total": total, "page": page, "pages": (total + limit - 1) // limit}

@app.put("/admin/users/{user_id}")
async def update_user(
    user_id: int,
    subscription_status: Optional[str] = Form(None),
    is_admin: Optional[bool] = Form(None),
    admin_user: dict = Depends(get_admin_user)
):
    """Update user (admin only)"""
    async with db_pool.acquire() as conn:
        updates = []
        values = []

        if subscription_status:
            updates.append("subscription_status = $" + str(len(values) + 1))
            values.append(subscription_status)
        if is_admin is not None:
            updates.append("is_admin = $" + str(len(values) + 1))
            values.append(is_admin)

        if updates:
            query = f"UPDATE users SET {', '.join(updates)} WHERE id = ${len(values) + 1}"
            values.append(user_id)
            await conn.execute(query, *values)

        return {"message": "User updated"}

@app.post("/admin/blog/posts")
async def create_blog_post(
    title: str = Form(...),
    slug: str = Form(...),
    content: str = Form(...),
    excerpt: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    published: bool = Form(False),
    admin_user: dict = Depends(get_admin_user)
):
    """Create a new blog post (admin only)"""
    async with db_pool.acquire() as conn:
        post_id = await conn.fetchval(
            "INSERT INTO blog_posts (title, slug, content, excerpt, category, published) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
            title, slug, content, excerpt, category, published
        )
        cache_delete_pattern("blog:")
        return {"id": post_id, "message": "Blog post created"}

@app.put("/admin/blog/posts/{post_id}")
async def update_blog_post(
    post_id: int,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    published: Optional[bool] = Form(None),
    admin_user: dict = Depends(get_admin_user)
):
    """Update a blog post (admin only)"""
    async with db_pool.acquire() as conn:
        updates = []
        values = []

        if title:
            updates.append("title = $" + str(len(values) + 1))
            values.append(title)
        if content:
            updates.append("content = $" + str(len(values) + 1))
            values.append(content)
        if excerpt is not None:
            updates.append("excerpt = $" + str(len(values) + 1))
            values.append(excerpt)
        if category is not None:
            updates.append("category = $" + str(len(values) + 1))
            values.append(category)
        if published is not None:
            updates.append("published = $" + str(len(values) + 1))
            values.append(published)

        if updates:
            updates.append("updated_at = NOW()")
            query = f"UPDATE blog_posts SET {', '.join(updates)} WHERE id = ${len(values) + 1}"
            values.append(post_id)
            await conn.execute(query, *values)

        cache_delete_pattern("blog:")
        return {"message": "Blog post updated"}

@app.delete("/admin/blog/posts/{post_id}")
async def delete_blog_post(post_id: int, admin_user: dict = Depends(get_admin_user)):
    """Delete a blog post (admin only)"""
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM blog_posts WHERE id = $1", post_id)
        cache_delete_pattern("blog:")
        return {"message": "Blog post deleted"}

@app.post("/admin/courses")
async def create_course(
    title: str = Form(...),
    description: str = Form(...),
    level: str = Form(...),
    category: Optional[str] = Form(None),
    admin_user: dict = Depends(get_admin_user)
):
    """Create a new course (admin only)"""
    async with db_pool.acquire() as conn:
        course_id = await conn.fetchval(
            "INSERT INTO courses (title, description, level, category) VALUES ($1, $2, $3, $4) RETURNING id",
            title, description, level, category
        )
        cache_delete("courses:all")
        return {"id": course_id, "message": "Course created"}

@app.post("/admin/make-admin")
async def make_user_admin(email: str = Form(...)):
    """Make a user an admin by email (no auth required for initial setup)"""
    async with db_pool.acquire() as conn:
        # Check if user exists
        user = await conn.fetchrow("SELECT id, email, is_admin FROM users WHERE email = $1", email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        logger.info(f"Making user {email} (ID: {user['id']}) an admin. Current is_admin: {user['is_admin']}")
        
        # Update to admin
        await conn.execute("UPDATE users SET is_admin = TRUE WHERE id = $1", user["id"])
        
        # Verify the update
        updated = await conn.fetchrow("SELECT is_admin FROM users WHERE id = $1", user["id"])
        logger.info(f"User {email} is_admin updated to: {updated['is_admin']}")
        
        return {
            "message": f"User {email} is now an admin. Please log out and log back in for changes to take effect.", 
            "user_id": user["id"],
            "is_admin": updated["is_admin"]
        }

@app.post("/setup/make-admin-default")
async def make_default_admin():
    """Make admin@pipways.com an admin (convenience endpoint for setup)"""
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id, email, is_admin FROM users WHERE email = 'admin@pipways.com'")
        if not user:
            raise HTTPException(status_code=404, detail="Default admin user not found. Please register first.")
        
        logger.info(f"Making admin@pipways.com (ID: {user['id']}) an admin. Current is_admin: {user['is_admin']}")
        
        await conn.execute("UPDATE users SET is_admin = TRUE WHERE id = $1", user["id"])
        
        # Verify the update
        updated = await conn.fetchrow("SELECT is_admin FROM users WHERE id = $1", user["id"])
        logger.info(f"admin@pipways.com is_admin updated to: {updated['is_admin']}")
        
        return {
            "message": "admin@pipways.com is now an admin. Please log out and log back in for changes to take effect.", 
            "user_id": user["id"],
            "is_admin": updated["is_admin"]
        }

@app.post("/admin/webinars")
async def create_webinar(
    title: str = Form(...),
    description: str = Form(...),
    scheduled_at: datetime = Form(...),
    zoom_join_url: Optional[str] = Form(None),
    admin_user: dict = Depends(get_admin_user)
):
    """Create a new webinar (admin only)"""
    async with db_pool.acquire() as conn:
        webinar_id = await conn.fetchval(
            "INSERT INTO webinars (title, description, scheduled_at, zoom_join_url) VALUES ($1, $2, $3, $4) RETURNING id",
            title, description, scheduled_at, zoom_join_url
        )
        cache_delete("webinars:all")
        return {"id": webinar_id, "message": "Webinar created"}

def cache_delete_pattern(pattern: str):
    """Delete cache keys matching pattern"""
    keys_to_delete = [k for k in cache_store.keys() if pattern in k]
    for key in keys_to_delete:
        cache_delete(key)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
