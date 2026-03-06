"""
Pipways Trading Platform - Complete Fixed Version
Uses PyJWT instead of python-jose to avoid import issues
"""
import os
import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

# Setup logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from fastapi import FastAPI, HTTPException, Depends, status, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
import jwt as pyjwt  # Import PyJWT with alias to avoid conflicts
import asyncpg

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/pipways")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# Database connection pool
db_pool: Optional[asyncpg.Pool] = None

# Pydantic Models
class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

class TradeEntry(BaseModel):
    id: Optional[int] = None
    symbol: str
    entry_price: float
    exit_price: Optional[float] = None
    position: str
    size: float
    pnl: Optional[float] = None
    notes: Optional[str] = None
    date: Optional[str] = None

class BlogPost(BaseModel):
    id: Optional[int] = None
    title: str
    content: str
    author: Optional[str] = None
    created_at: Optional[str] = None

# Database functions
async def init_db():
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
        logger.info("Database connected successfully")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

async def close_db():
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Database connection closed")

# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()

# Create FastAPI app
app = FastAPI(title="Pipways AI", lifespan=lifespan)

# CORS - Allow all for debugging
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = pyjwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = pyjwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return email
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Routes
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/health")
async def api_health_check():
    """API Health check"""
    return {"status": "healthy", "service": "pipways-api"}

@app.post("/api/auth/login", response_model=Token)
async def login(credentials: UserLogin):
    """Login endpoint"""
    logger.info(f"Login attempt for: {credentials.email}")

    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT * FROM users WHERE email = $1", credentials.email
        )

        if not user:
            logger.warning(f"User not found: {credentials.email}")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not verify_password(credentials.password, user["password_hash"]):
            logger.warning(f"Invalid password for: {credentials.email}")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["email"], "role": user["role"]},
            expires_delta=access_token_expires
        )

        logger.info(f"Login successful for: {credentials.email}")

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "role": user["role"]
            }
        }

@app.post("/api/auth/register")
async def register(user_data: UserRegister):
    """Register endpoint"""
    logger.info(f"Registration attempt for: {user_data.email}")

    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    async with db_pool.acquire() as conn:
        # Check if user exists
        existing = await conn.fetchrow(
            "SELECT id FROM users WHERE email = $1", user_data.email
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Hash password and create user
        hashed_password = get_password_hash(user_data.password)

        try:
            new_user = await conn.fetchrow(
                """
                INSERT INTO users (name, email, password_hash, role, created_at)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, name, email, role
                """,
                user_data.name,
                user_data.email,
                hashed_password,
                "user",
                datetime.utcnow()
            )

            logger.info(f"User registered successfully: {user_data.email}")

            return {
                "message": "Registration successful",
                "user": {
                    "id": new_user["id"],
                    "name": new_user["name"],
                    "email": new_user["email"],
                    "role": new_user["role"]
                }
            }
        except Exception as e:
            logger.error(f"Registration failed: {e}")
            raise HTTPException(status_code=500, detail="Registration failed")

@app.get("/api/trades")
async def get_trades(current_user: str = Depends(get_current_user)):
    """Get all trades for current user"""
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    async with db_pool.acquire() as conn:
        trades = await conn.fetch(
            """
            SELECT * FROM trades 
            WHERE user_email = $1 
            ORDER BY created_at DESC
            """,
            current_user
        )
        return [dict(trade) for trade in trades]

@app.post("/api/trades")
async def create_trade(trade: TradeEntry, current_user: str = Depends(get_current_user)):
    """Create a new trade"""
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    async with db_pool.acquire() as conn:
        new_trade = await conn.fetchrow(
            """
            INSERT INTO trades (user_email, symbol, entry_price, exit_price, position, size, pnl, notes, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            current_user,
            trade.symbol,
            trade.entry_price,
            trade.exit_price,
            trade.position,
            trade.size,
            trade.pnl,
            trade.notes,
            datetime.utcnow()
        )
        return dict(new_trade)

@app.get("/api/trades/stats")
async def get_trade_stats(current_user: str = Depends(get_current_user)):
    """Get trading statistics"""
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    async with db_pool.acquire() as conn:
        stats = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) as total_trades,
                COUNT(CASE WHEN pnl > 0 THEN 1 END) as winning_trades,
                COUNT(CASE WHEN pnl < 0 THEN 1 END) as losing_trades,
                COALESCE(SUM(pnl), 0) as total_pnl,
                COALESCE(AVG(pnl), 0) as avg_pnl
            FROM trades 
            WHERE user_email = $1
            """,
            current_user
        )
        return dict(stats)

@app.get("/api/blog")
async def get_blog_posts():
    """Get all blog posts"""
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    async with db_pool.acquire() as conn:
        posts = await conn.fetch(
            "SELECT * FROM blog_posts ORDER BY created_at DESC"
        )
        return [dict(post) for post in posts]

@app.post("/api/blog")
async def create_blog_post(post: BlogPost, current_user: str = Depends(get_current_user)):
    """Create a blog post (admin only)"""
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    async with db_pool.acquire() as conn:
        # Check if user is admin
        user = await conn.fetchrow(
            "SELECT role FROM users WHERE email = $1", current_user
        )
        if not user or user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

        new_post = await conn.fetchrow(
            """
            INSERT INTO blog_posts (title, content, author, created_at)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            post.title,
            post.content,
            current_user,
            datetime.utcnow()
        )
        return dict(new_post)

@app.post("/api/media/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user)
):
    """Upload a file"""
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)

    file_path = upload_dir / f"{datetime.utcnow().timestamp()}_{file.filename}"

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    return {"filename": file.filename, "path": str(file_path), "status": "uploaded"}

# Serve frontend - Check multiple locations
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the frontend HTML"""
    # Try root first, then frontend folder
    possible_paths = [
        Path("index.html"),
        Path("frontend/index.html"),
        Path("static/index.html"),
        project_root / "index.html",
        project_root / "frontend" / "index.html",
        project_root / "static" / "index.html",
    ]

    for path in possible_paths:
        if path.exists():
            logger.info(f"Serving frontend from: {path}")
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return HTMLResponse(content=content)

    # If no file found, return error
    logger.error("No index.html found in any location")
    return HTMLResponse(content="<h1>Error: Frontend not found</h1><p>Please ensure index.html exists</p>", status_code=404)

@app.get("/test")
async def test_page():
    """Simple test page"""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head><title>Pipways Test</title></head>
    <body>
        <h1>✓ Backend is Working!</h1>
        <p>If you see this, the API is running correctly.</p>
        <p>Try the <a href="/">main app</a></p>
        <p>API Health: <a href="/health">/health</a></p>
    </body>
    </html>
    """)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
