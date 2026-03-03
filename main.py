"""
Pipways - Forex Trading Journal API v3.0
Complete implementation with Admin Dashboard, Blog, Courses, AI Integration, RBAC
Fixed database connection verification and uploads directory creation
Fixed CORS and login issues for Render deployment
"""

import os
import re
import json
import base64
import logging
import io
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from contextlib import asynccontextmanager

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
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
    account_id: int
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
# DATABASE CONNECTION
# =============================================================================

async def init_db_pool():
    """Initialize database connection pool with verification"""
    global db_pool
    try:
        logger.info(f"Initializing database pool...")
        
        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=20,
            command_timeout=60,
            server_settings={
                'jit': 'off'
            }
        )
        
        # Verify the pool actually works
        async with db_pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            if result == 1:
                logger.info("Database pool initialized and verified successfully")
            else:
                raise Exception("Database verification query returned unexpected result")
                
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        db_pool = None
        raise

async def close_db_pool():
    """Close database connection pool"""
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None
        logger.info("Database pool closed")

async def get_db():
    """Get database connection from pool"""
    if db_pool is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    async with db_pool.acquire() as conn:
        yield conn

# =============================================================================
# AUTHENTICATION HELPERS
# =============================================================================

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

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
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT id, email, full_name, role, avatar_url, is_active FROM users WHERE id = $1",
                int(user_id)
            )
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

async def save_upload_file(upload_file: UploadFile, folder: str) -> str:
    """Save uploaded file and return the file path"""
    upload_dir = f"uploads/{folder}"
    os.makedirs(upload_dir, exist_ok=True)
    
    file_ext = os.path.splitext(upload_file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(upload_dir, unique_filename)
    
    content = await upload_file.read()
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(content)
    
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
# FASTAPI APPLICATION - CORS FIXED
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create uploads directory on startup
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("uploads/blog", exist_ok=True)
    logger.info("Uploads directories created/verified")
    
    await init_db_pool()
    yield
    await close_db_pool()

app = FastAPI(
    title="Pipways API",
    description="Forex Trading Journal with AI Analysis, Courses, and Blog",
    version="3.0.0",
    lifespan=lifespan
)

# =============================================================================
# CORS MIDDLEWARE - CRITICAL FIX FOR RENDER
# =============================================================================

# IMPORTANT: CORS middleware must be added BEFORE any routes
# and must explicitly allow OPTIONS for preflight requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins temporarily for debugging
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],  # Explicitly include OPTIONS
    allow_headers=["*"],  # Allow all headers
    expose_headers=["*"],
    max_age=3600,  # Cache preflight for 1 hour
)

# Create uploads directory BEFORE mounting StaticFiles
os.makedirs("uploads", exist_ok=True)
os.makedirs("uploads/blog", exist_ok=True)

# Mount static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# =============================================================================
# HEALTH & INFO ENDPOINTS
# =============================================================================

@app.get("/health")
async def health_check():
    db_status = "not_connected"
    error_detail = None
    
    try:
        if db_pool is not None:
            async with db_pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                if result == 1:
                    db_status = "connected"
                else:
                    db_status = "error"
                    error_detail = "Unexpected query result"
        else:
            db_status = "pool_not_initialized"
    except Exception as e:
        db_status = "error"
        error_detail = str(e)[:100]
        logger.error(f"Health check database error: {e}")
    
    response = {
        "status": "healthy" if db_status == "connected" else "unhealthy",
        "version": "3.0.0",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if error_detail:
        response["error"] = error_detail
        
    return response

@app.get("/api/info")
async def api_info():
    return {
        "name": "Pipways API",
        "version": "3.0.0",
        "features": [
            "trading_journal", "analytics", "ai_analysis",
            "courses", "blog", "admin_dashboard", "rbac"
        ]
    }

# =============================================================================
# AUTHENTICATION ENDPOINTS - FIXED FOR CORS/REDIRECT ISSUES
# =============================================================================

@app.post("/api/auth/register", response_model=TokenResponse)
async def register(user_data: UserRegister):
    async with db_pool.acquire() as conn:
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", user_data.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        password_hash = hash_password(user_data.password)
        
        user_id = await conn.fetchval("""
            INSERT INTO users (email, password_hash, full_name, phone, country)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """, user_data.email, password_hash, user_data.full_name, user_data.phone, user_data.country)
        
        await conn.execute("""
            INSERT INTO user_settings (user_id) VALUES ($1)
        """, user_id)
        
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

# FIXED LOGIN - Explicit POST handler with OPTIONS support
@app.post("/api/auth/login", response_model=TokenResponse)
async def login(login_data: UserLogin):
    """
    Login endpoint - requires POST with JSON body:
    {"email": "user@example.com", "password": "password"}
    """
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT * FROM users WHERE email = $1",
            login_data.email
        )
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        if user["locked_until"] and user["locked_until"] > datetime.utcnow():
            remaining = (user["locked_until"] - datetime.utcnow()).seconds // 60
            raise HTTPException(status_code=401, detail=f"Account locked. Try again in {remaining} minutes")
        
        if not verify_password(login_data.password, user["password_hash"]):
            new_attempts = (user["login_attempts"] or 0) + 1
            locked_until = None
            if new_attempts >= 5:
                locked_until = datetime.utcnow() + timedelta(minutes=30)
            
            await conn.execute("""
                UPDATE users SET login_attempts = $1, locked_until = $2 WHERE id = $3
            """, new_attempts, locked_until, user["id"])
            
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        await conn.execute("""
            UPDATE users 
            SET login_attempts = 0, locked_until = NULL, last_login_at = $1
            WHERE id = $2
        """, datetime.utcnow(), user["id"])
        
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

# Debug endpoint to check what method is being received
@app.api_route("/api/auth/login-test", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"])
async def login_test(request: Request):
    """Debug endpoint to see what method is being received"""
    return {
        "method_received": request.method,
        "url": str(request.url),
        "headers": dict(request.headers),
        "message": f"Received {request.method} request"
    }

@app.post("/api/admin/login", response_model=TokenResponse)
async def admin_login(login_data: AdminLogin):
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT * FROM users WHERE email = $1 AND role = 'admin'",
            login_data.email
        )
        
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
async def logout(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    token = credentials.credentials
    token_blacklist.add(token)
    return {"message": "Logged out successfully"}

@app.get("/api/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {"user": current_user}

# =============================================================================
# TRADING ENDPOINTS
# =============================================================================

@app.post("/api/trades")
async def create_trade(trade: TradeCreate, current_user: dict = Depends(get_current_user)):
    async with db_pool.acquire() as conn:
        account = await conn.fetchrow(
            "SELECT id FROM accounts WHERE id = $1 AND user_id = $2",
            trade.account_id, current_user["id"]
        )
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        trade_id = await conn.fetchval("""
            INSERT INTO trades (
                user_id, account_id, symbol, trade_type, entry_price, exit_price,
                stop_loss, take_profit, position_size, lot_size, strategy,
                timeframe, setup_type, entry_date, exit_date, emotions, notes,
                lessons_learned, tags, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
            RETURNING id
        """,
            current_user["id"], trade.account_id, trade.symbol, trade.trade_type,
            trade.entry_price, trade.exit_price, trade.stop_loss, trade.take_profit,
            trade.position_size, trade.lot_size, trade.strategy, trade.timeframe,
            trade.setup_type, trade.entry_date, trade.exit_date, trade.emotions,
            trade.notes, trade.lessons_learned, json.dumps(trade.tags),
            "closed" if trade.exit_price else "open"
        )
        
        return {"id": trade_id, "message": "Trade created successfully"}

@app.get("/api/trades")
async def list_trades(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    current_user: dict = Depends(get_current_user)
):
    async with db_pool.acquire() as conn:
        where_clauses = ["user_id = $1"]
        params = [current_user["id"]]
        param_idx = 2
        
        if status:
            where_clauses.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1
        if symbol:
            where_clauses.append(f"symbol ILIKE ${param_idx}")
            params.append(f"%{symbol}%")
            param_idx += 1
        if strategy:
            where_clauses.append(f"strategy = ${param_idx}")
            params.append(strategy)
            param_idx += 1
        
        where_sql = " AND ".join(where_clauses)
        
        trades = await conn.fetch(f"""
            SELECT * FROM trades WHERE {where_sql}
            ORDER BY entry_date DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """, *params, per_page, (page - 1) * per_page)
        
        total = await conn.fetchval(f"""
            SELECT COUNT(*) FROM trades WHERE {where_sql}
        """, *params[:-2])
        
        return {
            "trades": [dict(t) for t in trades],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        }

@app.get("/api/trades/{trade_id}")
async def get_trade(trade_id: int, current_user: dict = Depends(get_current_user)):
    async with db_pool.acquire() as conn:
        trade = await conn.fetchrow(
            "SELECT * FROM trades WHERE id = $1 AND user_id = $2",
            trade_id, current_user["id"]
        )
        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")
        return dict(trade)

@app.put("/api/trades/{trade_id}")
async def update_trade(
    trade_id: int,
    trade_update: TradeUpdate,
    current_user: dict = Depends(get_current_user)
):
    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM trades WHERE id = $1 AND user_id = $2",
            trade_id, current_user["id"]
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Trade not found")
        
        update_fields = []
        params = []
        param_idx = 1
        
        if trade_update.exit_price is not None:
            update_fields.append(f"exit_price = ${param_idx}")
            params.append(trade_update.exit_price)
            param_idx += 1
        if trade_update.exit_date is not None:
            update_fields.append(f"exit_date = ${param_idx}")
            params.append(trade_update.exit_date)
            param_idx += 1
        if trade_update.status is not None:
            update_fields.append(f"status = ${param_idx}")
            params.append(trade_update.status)
            param_idx += 1
        if trade_update.emotions is not None:
            update_fields.append(f"emotions = ${param_idx}")
            params.append(trade_update.emotions)
            param_idx += 1
        if trade_update.notes is not None:
            update_fields.append(f"notes = ${param_idx}")
            params.append(trade_update.notes)
            param_idx += 1
        if trade_update.lessons_learned is not None:
            update_fields.append(f"lessons_learned = ${param_idx}")
            params.append(trade_update.lessons_learned)
            param_idx += 1
        if trade_update.tags is not None:
            update_fields.append(f"tags = ${param_idx}")
            params.append(json.dumps(trade_update.tags))
            param_idx += 1
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        update_fields.append(f"updated_at = ${param_idx}")
        params.append(datetime.utcnow())
        param_idx += 1
        
        params.extend([trade_id, current_user["id"]])
        
        await conn.execute(f"""
            UPDATE trades SET {', '.join(update_fields)}
            WHERE id = ${param_idx} AND user_id = ${param_idx + 1}
        """, *params)
        
        return {"message": "Trade updated successfully"}

@app.delete("/api/trades/{trade_id}")
async def delete_trade(trade_id: int, current_user: dict = Depends(get_current_user)):
    async with db_pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM trades WHERE id = $1 AND user_id = $2",
            trade_id, current_user["id"]
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Trade not found")
        return {"message": "Trade deleted successfully"}

# =============================================================================
# ANALYTICS ENDPOINTS
# =============================================================================

@app.get("/api/analytics/dashboard")
async def get_dashboard_analytics(current_user: dict = Depends(get_current_user)):
    async with db_pool.acquire() as conn:
        overall = await conn.fetchrow("""
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
            WHERE user_id = $1 AND status = 'closed'
        """, current_user["id"])
        
        total_trades = overall["total_trades"] or 0
        winning_trades = overall["winning_trades"] or 0
        losing_trades = overall["losing_trades"] or 0
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        avg_win = overall["avg_win"] or 0
        avg_loss = abs(overall["avg_loss"] or 0)
        profit_factor = (avg_win * winning_trades) / (avg_loss * losing_trades) if (avg_loss * losing_trades) > 0 else 0
        
        expectancy = ((win_rate / 100) * avg_win) - ((1 - win_rate / 100) * avg_loss) if total_trades > 0 else 0
        
        monthly_data = await conn.fetch("""
            SELECT 
                DATE_TRUNC('month', entry_date) as month,
                COUNT(*) as trades,
                SUM(profit_loss) as pnl,
                SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as wins
            FROM trades
            WHERE user_id = $1 AND status = 'closed'
            GROUP BY DATE_TRUNC('month', entry_date)
            ORDER BY month DESC
            LIMIT 12
        """, current_user["id"])
        
        strategy_performance = await conn.fetch("""
            SELECT 
                strategy,
                COUNT(*) as trades,
                SUM(profit_loss) as total_pnl,
                AVG(profit_loss) as avg_pnl,
                SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate
            FROM trades
            WHERE user_id = $1 AND status = 'closed' AND strategy IS NOT NULL
            GROUP BY strategy
            ORDER BY total_pnl DESC
        """, current_user["id"])
        
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
async def analyze_trade_with_ai(
    request: AIAnalysisRequest,
    current_user: dict = Depends(get_current_user)
):
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=503, detail="AI service not configured")
    
    async with db_pool.acquire() as conn:
        trade = await conn.fetchrow("""
            SELECT * FROM trades WHERE id = $1 AND user_id = $2
        """, request.trade_id, current_user["id"])
        
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
                
                await conn.execute("""
                    UPDATE trades SET ai_analysis = $1 WHERE id = $2
                """, json.dumps(analysis_data), request.trade_id)
                
                return analysis_data
                
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="AI service timeout")
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            raise HTTPException(status_code=500, detail="Failed to analyze trade")

@app.post("/api/ai/analyze-chart")
async def analyze_chart_with_ai(
    request: ChartAnalysisRequest,
    current_user: dict = Depends(get_current_user)
):
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
async def list_courses(
    category: Optional[str] = None,
    level: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 12
):
    async with db_pool.acquire() as conn:
        where_clauses = ["is_published = TRUE"]
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
        if search:
            where_clauses.append(f"(title ILIKE ${param_idx} OR description ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1
        
        where_sql = " AND ".join(where_clauses)
        
        courses = await conn.fetch(f"""
            SELECT c.*, u.full_name as instructor_name,
                   (SELECT COUNT(*) FROM course_modules WHERE course_id = c.id) as module_count,
                   (SELECT COUNT(*) FROM course_lessons l 
                    JOIN course_modules m ON l.module_id = m.id WHERE m.course_id = c.id) as lesson_count
            FROM courses c
            LEFT JOIN users u ON c.instructor_id = u.id
            WHERE {where_sql}
            ORDER BY c.is_featured DESC, c.created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """, *params, per_page, (page - 1) * per_page)
        
        total = await conn.fetchval(f"""
            SELECT COUNT(*) FROM courses WHERE {where_sql}
        """, *params[:-2])
        
        return {
            "courses": [dict(c) for c in courses],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        }

@app.get("/api/courses/{course_id}")
async def get_course(course_id: int, current_user: dict = Depends(get_current_user)):
    async with db_pool.acquire() as conn:
        course = await conn.fetchrow("""
            SELECT c.*, u.full_name as instructor_name
            FROM courses c
            LEFT JOIN users u ON c.instructor_id = u.id
            WHERE c.id = $1
        """, course_id)
        
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
        
        modules = await conn.fetch("""
            SELECT * FROM course_modules
            WHERE course_id = $1 AND is_published = TRUE
            ORDER BY sort_order
        """, course_id)
        
        modules_with_lessons = []
        for module in modules:
            lessons = await conn.fetch("""
                SELECT id, title, description, video_duration, is_preview, sort_order
                FROM course_lessons
                WHERE module_id = $1
                ORDER BY sort_order
            """, module["id"])
            
            module_dict = dict(module)
            module_dict["lessons"] = [dict(l) for l in lessons]
            modules_with_lessons.append(module_dict)
        
        enrollment = await conn.fetchrow("""
            SELECT * FROM user_enrollments
            WHERE user_id = $1 AND course_id = $2
        """, current_user["id"], course_id)
        
        return {
            "course": dict(course),
            "modules": modules_with_lessons,
            "enrolled": enrollment is not None,
            "enrollment": dict(enrollment) if enrollment else None
        }

@app.post("/api/courses/{course_id}/enroll")
async def enroll_in_course(course_id: int, current_user: dict = Depends(get_current_user)):
    async with db_pool.acquire() as conn:
        course = await conn.fetchrow(
            "SELECT id, price FROM courses WHERE id = $1 AND is_published = TRUE",
            course_id
        )
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
        
        existing = await conn.fetchrow(
            "SELECT id FROM user_enrollments WHERE user_id = $1 AND course_id = $2",
            current_user["id"], course_id
        )
        if existing:
            raise HTTPException(status_code=400, detail="Already enrolled")
        
        await conn.execute("""
            INSERT INTO user_enrollments (user_id, course_id, payment_status)
            VALUES ($1, $2, $3)
        """, current_user["id"], course_id, "completed" if course["price"] == 0 else "pending")
        
        return {"message": "Enrolled successfully"}

@app.get("/api/courses/{course_id}/lessons/{lesson_id}")
async def get_lesson(
    course_id: int,
    lesson_id: int,
    current_user: dict = Depends(get_current_user)
):
    async with db_pool.acquire() as conn:
        enrollment = await conn.fetchrow("""
            SELECT * FROM user_enrollments
            WHERE user_id = $1 AND course_id = $2
        """, current_user["id"], course_id)
        
        lesson = await conn.fetchrow("""
            SELECT l.*, m.course_id
            FROM course_lessons l
            JOIN course_modules m ON l.module_id = m.id
            WHERE l.id = $1 AND m.course_id = $2
        """, lesson_id, course_id)
        
        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found")
        
        if not lesson["is_preview"] and not enrollment:
            raise HTTPException(status_code=403, detail="Enroll to access this lesson")
        
        progress = await conn.fetchrow("""
            SELECT * FROM lesson_progress
            WHERE user_id = $1 AND lesson_id = $2
        """, current_user["id"], lesson_id)
        
        return {
            "lesson": dict(lesson),
            "progress": dict(progress) if progress else None
        }

@app.post("/api/courses/{course_id}/lessons/{lesson_id}/progress")
async def update_lesson_progress(
    course_id: int,
    lesson_id: int,
    is_completed: bool = Form(False),
    watch_time: int = Form(0),
    current_user: dict = Depends(get_current_user)
):
    async with db_pool.acquire() as conn:
        enrollment = await conn.fetchrow("""
            SELECT * FROM user_enrollments
            WHERE user_id = $1 AND course_id = $2
        """, current_user["id"], course_id)
        
        if not enrollment:
            raise HTTPException(status_code=403, detail="Not enrolled in this course")
        
        await conn.execute("""
            INSERT INTO lesson_progress (user_id, lesson_id, is_completed, watch_time_seconds, completed_at, last_watched_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id, lesson_id) DO UPDATE SET
                is_completed = EXCLUDED.is_completed,
                watch_time_seconds = lesson_progress.watch_time_seconds + EXCLUDED.watch_time_seconds,
                completed_at = COALESCE(lesson_progress.completed_at, EXCLUDED.completed_at),
                last_watched_at = EXCLUDED.last_watched_at
        """, current_user["id"], lesson_id, is_completed, watch_time,
            datetime.utcnow() if is_completed else None, datetime.utcnow())
        
        total_lessons = await conn.fetchval("""
            SELECT COUNT(*) FROM course_lessons l
            JOIN course_modules m ON l.module_id = m.id
            WHERE m.course_id = $1
        """, course_id)
        
        completed_lessons = await conn.fetchval("""
            SELECT COUNT(*) FROM lesson_progress lp
            JOIN course_lessons l ON lp.lesson_id = l.id
            JOIN course_modules m ON l.module_id = m.id
            WHERE m.course_id = $1 AND lp.user_id = $2 AND lp.is_completed = TRUE
        """, course_id, current_user["id"])
        
        progress_percent = int((completed_lessons / total_lessons) * 100) if total_lessons > 0 else 0
        
        await conn.execute("""
            UPDATE user_enrollments
            SET progress_percent = $1
            WHERE user_id = $2 AND course_id = $3
        """, progress_percent, current_user["id"], course_id)
        
        return {"progress_percent": progress_percent, "completed_lessons": completed_lessons}

# =============================================================================
# BLOG ENDPOINTS
# =============================================================================

@app.get("/api/blog/posts")
async def list_blog_posts(
    category: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 10
):
    async with db_pool.acquire() as conn:
        where_clauses = ["status = 'published'"]
        params = []
        param_idx = 1
        
        if category:
            where_clauses.append(f"category = ${param_idx}")
            params.append(category)
            param_idx += 1
        if tag:
            where_clauses.append(f"tags @> ${param_idx}::jsonb")
            params.append(json.dumps([tag]))
            param_idx += 1
        if search:
            where_clauses.append(f"(title ILIKE ${param_idx} OR content ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1
        
        where_sql = " AND ".join(where_clauses)
        
        posts = await conn.fetch(f"""
            SELECT p.*, u.full_name as author_name
            FROM blog_posts p
            LEFT JOIN users u ON p.author_id = u.id
            WHERE {where_sql}
            ORDER BY p.published_at DESC NULLS LAST, p.created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """, *params, per_page, (page - 1) * per_page)
        
        total = await conn.fetchval(f"""
            SELECT COUNT(*) FROM blog_posts WHERE {where_sql}
        """, *params[:-2])
        
        return {
            "posts": [dict(p) for p in posts],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        }

@app.get("/api/blog/posts/{slug}")
async def get_blog_post(slug: str):
    async with db_pool.acquire() as conn:
        post = await conn.fetchrow("""
            SELECT p.*, u.full_name as author_name
            FROM blog_posts p
            LEFT JOIN users u ON p.author_id = u.id
            WHERE p.slug = $1 AND p.status = 'published'
        """, slug)
        
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        await conn.execute("""
            UPDATE blog_posts SET view_count = view_count + 1 WHERE id = $1
        """, post["id"])
        
        related = await conn.fetch("""
            SELECT slug, title, excerpt, featured_image FROM blog_posts
            WHERE status = 'published' AND category = $1 AND id != $2
            ORDER BY published_at DESC LIMIT 3
        """, post["category"], post["id"])
        
        return {
            "post": dict(post),
            "related_posts": [dict(r) for r in related]
        }

# =============================================================================
# ADMIN ENDPOINTS - BLOG MANAGEMENT
# =============================================================================

@app.post("/api/admin/blog/posts")
async def admin_create_post(
    post: BlogPostCreate,
    current_user: dict = Depends(get_admin_user)
):
    async with db_pool.acquire() as conn:
        slug = post.slug or generate_slug(post.title)
        
        existing = await conn.fetchval("SELECT id FROM blog_posts WHERE slug = $1", slug)
        if existing:
            slug = f"{slug}-{uuid.uuid4().hex[:8]}"
        
        post_id = await conn.fetchval("""
            INSERT INTO blog_posts (
                author_id, title, slug, excerpt, content, featured_image,
                category, tags, seo_title, seo_description, seo_keywords, status, published_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING id
        """,
            current_user["id"], post.title, slug, post.excerpt, post.content,
            post.featured_image, post.category, json.dumps(post.tags),
            post.seo_title, post.seo_description, post.seo_keywords,
            post.status, datetime.utcnow() if post.status == "published" else None
        )
        
        return {"id": post_id, "slug": slug, "message": "Post created"}

@app.put("/api/admin/blog/posts/{post_id}")
async def admin_update_post(
    post_id: int,
    post: BlogPostUpdate,
    current_user: dict = Depends(get_admin_user)
):
    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT * FROM blog_posts WHERE id = $1", post_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Post not found")
        
        update_fields = []
        params = []
        param_idx = 1
        
        if post.title is not None:
            update_fields.append(f"title = ${param_idx}")
            params.append(post.title)
            param_idx += 1
        if post.excerpt is not None:
            update_fields.append(f"excerpt = ${param_idx}")
            params.append(post.excerpt)
            param_idx += 1
        if post.content is not None:
            update_fields.append(f"content = ${param_idx}")
            params.append(post.content)
            param_idx += 1
        if post.featured_image is not None:
            update_fields.append(f"featured_image = ${param_idx}")
            params.append(post.featured_image)
            param_idx += 1
        if post.category is not None:
            update_fields.append(f"category = ${param_idx}")
            params.append(post.category)
            param_idx += 1
        if post.tags is not None:
            update_fields.append(f"tags = ${param_idx}")
            params.append(json.dumps(post.tags))
            param_idx += 1
        if post.seo_title is not None:
            update_fields.append(f"seo_title = ${param_idx}")
            params.append(post.seo_title)
            param_idx += 1
        if post.seo_description is not None:
            update_fields.append(f"seo_description = ${param_idx}")
            params.append(post.seo_description)
            param_idx += 1
        if post.seo_keywords is not None:
            update_fields.append(f"seo_keywords = ${param_idx}")
            params.append(post.seo_keywords)
            param_idx += 1
        if post.status is not None:
            update_fields.append(f"status = ${param_idx}")
            params.append(post.status)
            param_idx += 1
            if post.status == "published" and existing["status"] != "published":
                update_fields.append(f"published_at = ${param_idx}")
                params.append(datetime.utcnow())
                param_idx += 1
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        update_fields.append(f"updated_at = ${param_idx}")
        params.append(datetime.utcnow())
        param_idx += 1
        params.append(post_id)
        
        await conn.execute(f"""
            UPDATE blog_posts SET {', '.join(update_fields)} WHERE id = ${param_idx}
        """, *params)
        
        return {"message": "Post updated"}

@app.delete("/api/admin/blog/posts/{post_id}")
async def admin_delete_post(post_id: int, current_user: dict = Depends(get_admin_user)):
    async with db_pool.acquire() as conn:
        result = await conn.execute("DELETE FROM blog_posts WHERE id = $1", post_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Post not found")
        return {"message": "Post deleted"}

@app.get("/api/admin/blog/posts")
async def admin_list_posts(
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    current_user: dict = Depends(get_admin_user)
):
    async with db_pool.acquire() as conn:
        where_clauses = []
        params = []
        param_idx = 1
        
        if status:
            where_clauses.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        posts = await conn.fetch(f"""
            SELECT p.*, u.full_name as author_name
            FROM blog_posts p
            LEFT JOIN users u ON p.author_id = u.id
            WHERE {where_sql}
            ORDER BY p.created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """, *params, per_page, (page - 1) * per_page)
        
        total = await conn.fetchval(f"SELECT COUNT(*) FROM blog_posts WHERE {where_sql}", *params[:-2])
        
        return {
            "posts": [dict(p) for p in posts],
            "total": total,
            "page": page,
            "per_page": per_page
        }

@app.post("/api/admin/blog/media")
async def admin_upload_media(
    file: UploadFile = File(...),
    alt_text: Optional[str] = Form(None),
    current_user: dict = Depends(get_admin_user)
):
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    file_path = await save_upload_file(file, "blog")
    file_size = os.path.getsize(file_path)
    
    async with db_pool.acquire() as conn:
        media_id = await conn.fetchval("""
            INSERT INTO blog_media (uploaded_by, filename, original_name, file_path, file_size, mime_type, alt_text)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
        """, current_user["id"], os.path.basename(file_path), file.filename, file_path, file_size, file.content_type, alt_text)
        
        return {
            "id": media_id,
            "url": f"/uploads/{os.path.basename(file_path)}",
            "filename": os.path.basename(file_path)
        }

# =============================================================================
# ADMIN ENDPOINTS - COURSE MANAGEMENT
# =============================================================================

@app.post("/api/admin/courses")
async def admin_create_course(
    course: CourseCreate,
    current_user: dict = Depends(get_admin_user)
):
    async with db_pool.acquire() as conn:
        slug = course.slug or generate_slug(course.title)
        
        existing = await conn.fetchval("SELECT id FROM courses WHERE slug = $1", slug)
        if existing:
            slug = f"{slug}-{uuid.uuid4().hex[:8]}"
        
        course_id = await conn.fetchval("""
            INSERT INTO courses (
                instructor_id, title, slug, description, short_description,
                thumbnail_url, preview_video_url, category, level, price,
                duration_hours, seo_title, seo_description
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING id
        """,
            current_user["id"], course.title, slug, course.description,
            course.short_description, course.thumbnail_url, course.preview_video_url,
            course.category, course.level, course.price, course.duration_hours,
            course.seo_title, course.seo_description
        )
        
        return {"id": course_id, "slug": slug, "message": "Course created"}

@app.put("/api/admin/courses/{course_id}")
async def admin_update_course(
    course_id: int,
    course: CourseUpdate,
    current_user: dict = Depends(get_admin_user)
):
    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT * FROM courses WHERE id = $1", course_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Course not found")
        
        update_fields = []
        params = []
        param_idx = 1
        
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
                update_fields.append(f"{field} = ${param_idx}")
                params.append(value)
                param_idx += 1
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        update_fields.append(f"updated_at = ${param_idx}")
        params.append(datetime.utcnow())
        param_idx += 1
        params.append(course_id)
        
        await conn.execute(f"""
            UPDATE courses SET {', '.join(update_fields)} WHERE id = ${param_idx}
        """, *params)
        
        return {"message": "Course updated"}

@app.delete("/api/admin/courses/{course_id}")
async def admin_delete_course(course_id: int, current_user: dict = Depends(get_admin_user)):
    async with db_pool.acquire() as conn:
        result = await conn.execute("DELETE FROM courses WHERE id = $1", course_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Course not found")
        return {"message": "Course deleted"}

@app.post("/api/admin/courses/{course_id}/modules")
async def admin_create_module(
    course_id: int,
    module: ModuleCreate,
    current_user: dict = Depends(get_admin_user)
):
    async with db_pool.acquire() as conn:
        course = await conn.fetchval("SELECT id FROM courses WHERE id = $1", course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
        
        module_id = await conn.fetchval("""
            INSERT INTO course_modules (course_id, title, description, sort_order)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """, course_id, module.title, module.description, module.sort_order)
        
        return {"id": module_id, "message": "Module created"}

@app.post("/api/admin/modules/{module_id}/lessons")
async def admin_create_lesson(
    module_id: int,
    lesson: LessonCreate,
    current_user: dict = Depends(get_admin_user)
):
    async with db_pool.acquire() as conn:
        module = await conn.fetchval("SELECT id FROM course_modules WHERE id = $1", module_id)
        if not module:
            raise HTTPException(status_code=404, detail="Module not found")
        
        lesson_id = await conn.fetchval("""
            INSERT INTO course_lessons (module_id, title, description, content, video_url, video_duration, is_preview, sort_order)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
        """, module_id, lesson.title, lesson.description, lesson.content,
            lesson.video_url, lesson.video_duration, lesson.is_preview, lesson.sort_order)
        
        return {"id": lesson_id, "message": "Lesson created"}

# =============================================================================
# ADMIN ENDPOINTS - USER MANAGEMENT
# =============================================================================

@app.get("/api/admin/users")
async def admin_list_users(
    role: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    current_user: dict = Depends(get_admin_user)
):
    async with db_pool.acquire() as conn:
        where_clauses = []
        params = []
        param_idx = 1
        
        if role:
            where_clauses.append(f"role = ${param_idx}")
            params.append(role)
            param_idx += 1
        if search:
            where_clauses.append(f"(email ILIKE ${param_idx} OR full_name ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        users = await conn.fetch(f"""
            SELECT id, email, full_name, role, is_active, created_at, last_login_at
            FROM users
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """, *params, per_page, (page - 1) * per_page)
        
        total = await conn.fetchval(f"SELECT COUNT(*) FROM users WHERE {where_sql}", *params[:-2])
        
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
    async with db_pool.acquire() as conn:
        if user_id == current_user["id"] and role and role != "admin":
            raise HTTPException(status_code=400, detail="Cannot remove your own admin role")
        
        update_fields = []
        params = []
        param_idx = 1
        
        if role is not None:
            update_fields.append(f"role = ${param_idx}")
            params.append(role)
            param_idx += 1
        if is_active is not None:
            update_fields.append(f"is_active = ${param_idx}")
            params.append(is_active)
            param_idx += 1
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        params.append(user_id)
        
        await conn.execute(f"""
            UPDATE users SET {', '.join(update_fields)} WHERE id = ${param_idx}
        """, *params)
        
        return {"message": "User updated"}

# =============================================================================
# ADMIN DASHBOARD ENDPOINTS
# =============================================================================

@app.get("/api/admin/dashboard/stats")
async def admin_dashboard_stats(current_user: dict = Depends(get_admin_user)):
    async with db_pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        total_trades = await conn.fetchval("SELECT COUNT(*) FROM trades")
        total_courses = await conn.fetchval("SELECT COUNT(*) FROM courses")
        total_posts = await conn.fetchval("SELECT COUNT(*) FROM blog_posts")
        
        new_users_today = await conn.fetchval("""
            SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE
        """)
        
        new_trades_today = await conn.fetchval("""
            SELECT COUNT(*) FROM trades WHERE created_at >= CURRENT_DATE
        """)
        
        enrollments = await conn.fetchval("SELECT COUNT(*) FROM user_enrollments")
        
        recent_users = await conn.fetch("""
            SELECT id, email, full_name, role, created_at
            FROM users
            ORDER BY created_at DESC LIMIT 5
        """)
        
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
# STATIC FILES & SPA
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_spa():
    try:
        with open("index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Pipways API v3.0</h1><p>Frontend not built yet.</p>")

@app.get("/{path:path}", response_class=HTMLResponse)
async def serve_spa_routes(path: str):
    try:
        with open("index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Page not found")

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
