"""
Pipways Trading Platform - Root Path Version
"""
import os
import sys
import logging
import asyncpg
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI, HTTPException, status, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, EmailStr
from pydantic_settings import BaseSettings
from jose import JWTError, jwt
from passlib.context import CryptContext

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Settings
class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://user:pass@localhost/pipways"
    SECRET_KEY: str = "change-this-in-production-min-32-characters-long"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALLOWED_ORIGINS: str = "*"
    ENV: str = "development"
    PORT: int = 8000

    @property
    def cors_origins(self) -> List[str]:
        if self.ALLOWED_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()

# Database
class Database:
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

# Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security_bearer = HTTPBearer(auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[dict]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if not payload.get("sub"):
            return None
        return payload
    except JWTError:
        return None

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "role": payload.get("role")
    }

# FastAPI App
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    await init_db()
    logger.info("Ready")
    yield
    await close_db()
    logger.info("Shutdown")

app = FastAPI(title="Pipways", version="2.0.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# KEY CHANGE: Serve index.html from ROOT
# ==========================================

@app.get("/")
async def root():
    """Serve index.html from root directory"""
    logger.info("Root URL accessed")

    # Try root directory first
    if os.path.exists("index.html"):
        logger.info("Serving index.html from root")
        return FileResponse("index.html")

    # Fallback to frontend directory
    if os.path.exists("frontend/index.html"):
        logger.info("Serving index.html from frontend/")
        return FileResponse("frontend/index.html")

    logger.warning("index.html not found")
    return {"message": "Pipways API", "error": "index.html not found in root or frontend/"}

# Mount static files if they exist
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if os.path.exists("uploads"):
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# Auth Routes
@app.post("/api/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    logger.info(f"Login attempt: {form_data.username}")

    user = await db.fetchrow(
        "SELECT id, email, password_hash, full_name, role, is_active FROM users WHERE email = $1",
        form_data.username
    )

    if not user or not verify_password(form_data.password, user["password_hash"]):
        logger.warning(f"Login failed for: {form_data.username}")
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account disabled")

    access_token = create_access_token(
        data={"sub": str(user["id"]), "email": user["email"], "role": user["role"]}
    )

    logger.info(f"Login success: {form_data.username}")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": user["id"], "email": user["email"], "full_name": user["full_name"], "role": user["role"]}
    }

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=2)

@app.post("/api/auth/register")
async def register(user_data: UserRegister):
    logger.info(f"Register attempt: {user_data.email}")

    existing = await db.fetchrow("SELECT id FROM users WHERE email = $1", user_data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user_data.password)

    user = await db.fetchrow(
        "INSERT INTO users (email, password_hash, full_name, role, is_active) VALUES ($1, $2, $3, $4, $5) RETURNING id, email, full_name, role, is_active",
        user_data.email, hashed_password, user_data.full_name, "user", True
    )

    logger.info(f"Register success: {user_data.email}")
    return {"message": "User created", "user": dict(user)}

# Trade Routes
@app.get("/api/trades/")
async def list_trades(current_user: dict = Depends(get_current_user)):
    rows = await db.fetch("SELECT * FROM trades WHERE user_id = $1 ORDER BY entry_date DESC", int(current_user["user_id"]))
    return [dict(row) for row in rows]

@app.post("/api/trades/")
async def create_trade(trade: dict, current_user: dict = Depends(get_current_user)):
    result = await db.fetchrow(
        "INSERT INTO trades (user_id, symbol, direction, entry_price, quantity, entry_date, strategy, setup_notes, status) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *",
        int(current_user["user_id"]), trade.get("symbol", "").upper(), trade.get("direction"), 
        trade.get("entry_price"), trade.get("quantity"), trade.get("entry_date", datetime.utcnow().isoformat()),
        trade.get("strategy"), trade.get("setup_notes"), "open"
    )
    return dict(result)

@app.get("/api/trades/stats")
async def get_trade_stats(current_user: dict = Depends(get_current_user)):
    stats = await db.fetchrow(
        "SELECT COUNT(*) as total_trades, COUNT(CASE WHEN pnl > 0 THEN 1 END) as winning_trades, COALESCE(SUM(pnl), 0) as total_pnl FROM trades WHERE user_id = $1 AND status = 'closed'",
        int(current_user["user_id"])
    )
    return dict(stats)

# Blog Routes
@app.get("/api/blog/posts")
async def list_posts():
    rows = await db.fetch("SELECT * FROM blog_posts WHERE status = 'published' ORDER BY created_at DESC")
    return [dict(row) for row in rows]

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", settings.PORT))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
