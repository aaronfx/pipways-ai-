"""
Pipways Trading Platform - Monolithic Version (No package imports)
All core functionality included in single file for Render deployment
"""
import os
import sys
import logging
import asyncpg
import base64
import requests
import imghdr
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Union
from contextlib import asynccontextmanager
from functools import lru_cache
from decimal import Decimal

from fastapi import FastAPI, HTTPException, status, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, EmailStr
from pydantic_settings import BaseSettings
from jose import JWTError, jwt
from passlib.context import CryptContext

# ==========================================
# CONFIGURATION
# ==========================================

class Settings(BaseSettings):
    """Application settings"""
    DATABASE_URL: str = "postgresql://user:pass@localhost/pipways"
    SECRET_KEY: str = "change-this-in-production-min-32-characters"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8000"
    MAX_UPLOAD_SIZE: int = 5 * 1024 * 1024
    ALLOWED_EXTENSIONS: set = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    OPENROUTER_API_KEY: str = ""
    ZOOM_ACCOUNT_ID: str = ""
    ZOOM_CLIENT_ID: str = ""
    ZOOM_CLIENT_SECRET: str = ""
    ENV: str = "development"
    DEBUG: bool = False
    PORT: int = 8000

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()

# ==========================================
# DATABASE
# ==========================================

class Database:
    """Database connection manager"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                settings.DATABASE_URL,
                min_size=2,
                max_size=10,
                command_timeout=60
            )

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def fetch(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def execute(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

db = Database()

async def init_db():
    await db.connect()

async def close_db():
    await db.disconnect()

# ==========================================
# SECURITY
# ==========================================

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security_bearer = HTTPBearer()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)):
    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    return {"user_id": user_id, "email": payload.get("email"), "role": payload.get("role")}

async def get_current_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user

# ==========================================
# FASTAPI APP
# ==========================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    await init_db()
    logger.info("Database connected")
    yield
    await close_db()
    logger.info("Database disconnected")

app = FastAPI(
    title="Pipways Trading Platform",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# ROUTERS
# ==========================================

# Auth Router
@app.post("/api/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await db.fetchrow(
        "SELECT id, email, password_hash, full_name, role, is_active FROM users WHERE email = $1",
        form_data.username
    )

    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="User account is disabled")

    access_token = create_access_token(
        data={"sub": str(user["id"]), "email": user["email"], "role": user["role"]}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": user["id"], "email": user["email"], "full_name": user["full_name"], "role": user["role"]}
    }

@app.post("/api/auth/register")
async def register(user_data: dict):
    email = user_data.get("email")
    password = user_data.get("password")
    full_name = user_data.get("full_name")

    existing = await db.fetchrow("SELECT id FROM users WHERE email = $1", email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(password)

    user = await db.fetchrow(
        "INSERT INTO users (email, password_hash, full_name, role, is_active) VALUES ($1, $2, $3, $4, $5) RETURNING id, email, full_name, role, is_active",
        email, hashed_password, full_name, "user", True
    )
    return dict(user)

# Trades Router
@app.get("/api/trades/")
async def list_trades(current_user: dict = Depends(get_current_user)):
    rows = await db.fetch("SELECT * FROM trades WHERE user_id = $1 ORDER BY entry_date DESC", int(current_user["user_id"]))
    return [dict(row) for row in rows]

@app.post("/api/trades/")
async def create_trade(trade: dict, current_user: dict = Depends(get_current_user)):
    result = await db.fetchrow(
        """INSERT INTO trades (user_id, symbol, direction, entry_price, quantity, entry_date, strategy, setup_notes, status) 
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *""",
        int(current_user["user_id"]), trade["symbol"].upper(), trade["direction"], 
        trade["entry_price"], trade["quantity"], trade["entry_date"],
        trade.get("strategy"), trade.get("setup_notes"), "open"
    )
    return dict(result)

@app.get("/api/trades/stats")
async def get_trade_stats(current_user: dict = Depends(get_current_user)):
    stats = await db.fetchrow(
        """SELECT 
            COUNT(*) as total_trades,
            COUNT(CASE WHEN pnl > 0 THEN 1 END) as winning_trades,
            COALESCE(SUM(pnl), 0) as total_pnl
        FROM trades WHERE user_id = $1 AND status = 'closed'""",
        int(current_user["user_id"])
    )
    return dict(stats)

# Blog Router
@app.get("/api/blog/posts")
async def list_posts():
    rows = await db.fetch("SELECT * FROM blog_posts WHERE status = 'published' ORDER BY created_at DESC")
    return [dict(row) for row in rows]

@app.get("/api/blog/posts/{slug}")
async def get_post(slug: str):
    post = await db.fetchrow("SELECT * FROM blog_posts WHERE slug = $1", slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return dict(post)

# Media Router
os.makedirs("uploads", exist_ok=True)

@app.post("/api/media/upload")
async def upload_image(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file type")

    contents = await file.read(settings.MAX_UPLOAD_SIZE + 1)
    if len(contents) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large")

    unique_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join("uploads", unique_name)

    with open(file_path, "wb") as f:
        f.write(contents)

    return {"filename": unique_name, "url": f"/uploads/{unique_name}"}

# Static files
if os.path.exists("frontend"):
    app.mount("/static", StaticFiles(directory="frontend"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/")
async def root():
    if os.path.exists("frontend/index.html"):
        return FileResponse("frontend/index.html")
    return {"message": "Pipways Trading Platform API", "version": "2.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", settings.PORT))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
