"""
Pipways Trading Platform - Debug Version
"""
import os
import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from fastapi import FastAPI, HTTPException, Depends, status, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext

# Try PyJWT with fallback
try:
    import jwt as pyjwt
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyJWT==2.8.0"])
    import jwt as pyjwt

import asyncpg

# Config
DATABASE_URL = os.getenv("DATABASE_URL", "")
SECRET_KEY = os.getenv("SECRET_KEY", "pipways-secret-key")
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
db_pool: Optional[asyncpg.Pool] = None

# Models
class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

# DB Functions
async def init_db():
    global db_pool
    if not DATABASE_URL:
        logger.error("DATABASE_URL not set!")
        return
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
        logger.info("Database connected")
    except Exception as e:
        logger.error(f"DB connection failed: {e}")

async def close_db():
    global db_pool
    if db_pool:
        await db_pool.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()

app = FastAPI(title="Pipways AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Debug endpoints first
@app.get("/debug")
async def debug_info():
    """Debug endpoint to check system status"""
    info = {
        "status": "running",
        "database_url_set": bool(DATABASE_URL),
        "database_connected": db_pool is not None,
        "timestamp": datetime.utcnow().isoformat()
    }

    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                # Check if tables exist
                tables = await conn.fetch("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
                info["tables"] = [t["table_name"] for t in tables]

                # Check users count
                try:
                    user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
                    info["user_count"] = user_count
                except:
                    info["user_count"] = "users table not found"

        except Exception as e:
            info["database_error"] = str(e)

    return info

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Setup page - MUST be before the / route
@app.get("/setup", response_class=HTMLResponse)
async def setup_page():
    """Serve the setup page"""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Pipways Setup</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100 min-h-screen flex items-center justify-center p-4">
        <div class="bg-white rounded-xl shadow-2xl p-8 max-w-md w-full">
            <h1 class="text-3xl font-bold text-center mb-2 text-purple-600">Pipways Setup</h1>
            <p class="text-gray-600 text-center mb-6">Initialize your database</p>

            <div id="status" class="mb-4 p-4 rounded-lg hidden"></div>

            <button onclick="runSetup()" 
                class="w-full bg-gradient-to-r from-purple-500 to-indigo-600 text-white font-bold py-3 px-4 rounded-lg hover:opacity-90 transition">
                Initialize Database
            </button>

            <div class="mt-6 text-center">
                <a href="/" class="text-purple-600 hover:underline">Go to Login Page</a>
            </div>

            <div class="mt-4 text-sm text-gray-500 text-center">
                <p class="font-bold">Default Login:</p>
                <p>Email: admin@pipways.com</p>
                <p>Password: admin123</p>
            </div>
        </div>

        <script>
            function showStatus(message, isError) {
                const status = document.getElementById("status");
                status.textContent = message;
                status.className = "mb-4 p-4 rounded-lg " + (isError ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700");
                status.classList.remove("hidden");
            }

            async function runSetup() {
                try {
                    showStatus("Setting up database...", false);

                    const response = await fetch("/api/setup", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" }
                    });

                    const data = await response.json();

                    if (response.ok) {
                        showStatus("Success! " + data.message + " Default user: " + data.default_user, false);
                    } else {
                        showStatus("Error: " + (data.detail || "Unknown error"), true);
                    }
                } catch (error) {
                    showStatus("Error: " + error.message, true);
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Create tables endpoint (for easy setup)
@app.post("/api/setup")
async def setup_database():
    """Create database tables and default user"""
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    async with db_pool.acquire() as conn:
        # Create tables
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id SERIAL PRIMARY KEY,
                user_email VARCHAR(255) REFERENCES users(email),
                symbol VARCHAR(20) NOT NULL,
                entry_price DECIMAL(15, 5) NOT NULL,
                exit_price DECIMAL(15, 5),
                position VARCHAR(10) NOT NULL,
                size DECIMAL(15, 2) NOT NULL,
                pnl DECIMAL(15, 2),
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blog_posts (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                author VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create default admin
        hashed_pw = pwd_context.hash("admin123")
        await conn.execute("""
            INSERT INTO users (name, email, password_hash, role)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (email) DO NOTHING
        """, "Admin User", "admin@pipways.com", hashed_pw, "admin")

        return {"message": "Database setup complete", "default_user": "admin@pipways.com / admin123"}

# Auth endpoints with better error handling
@app.post("/api/auth/login")
async def login(credentials: UserLogin):
    logger.info(f"Login attempt: {credentials.email}")

    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE email = $1", credentials.email
            )

            if not user:
                logger.warning(f"User not found: {credentials.email}")
                raise HTTPException(status_code=401, detail="Invalid credentials")

            if not pwd_context.verify(credentials.password, user["password_hash"]):
                logger.warning(f"Wrong password for: {credentials.email}")
                raise HTTPException(status_code=401, detail="Invalid credentials")

            token = pyjwt.encode(
                {"sub": user["email"], "role": user["role"], "exp": datetime.utcnow() + timedelta(hours=24)},
                SECRET_KEY,
                algorithm=ALGORITHM
            )

            logger.info(f"Login successful: {credentials.email}")

            return {
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": user["id"],
                    "name": user["name"],
                    "email": user["email"],
                    "role": user["role"]
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@app.post("/api/auth/register")
async def register(user_data: UserRegister):
    logger.info(f"Registration attempt: {user_data.email}")

    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        async with db_pool.acquire() as conn:
            # Check existing
            existing = await conn.fetchrow(
                "SELECT id FROM users WHERE email = $1", user_data.email
            )
            if existing:
                raise HTTPException(status_code=400, detail="Email already registered")

            # Create user
            hashed_pw = pwd_context.hash(user_data.password)
            new_user = await conn.fetchrow(
                """
                INSERT INTO users (name, email, password_hash, role, created_at)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, name, email, role
                """,
                user_data.name,
                user_data.email,
                hashed_pw,
                "user",
                datetime.utcnow()
            )

            logger.info(f"Registration successful: {user_data.email}")

            return {
                "message": "Registration successful",
                "user": dict(new_user)
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# Other endpoints
@app.get("/api/trades")
async def get_trades(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = pyjwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

    async with db_pool.acquire() as conn:
        trades = await conn.fetch(
            "SELECT * FROM trades WHERE user_email = $1 ORDER BY created_at DESC",
            email
        )
        return [dict(t) for t in trades]

@app.post("/api/trades")
async def create_trade(
    trade: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = pyjwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

    async with db_pool.acquire() as conn:
        new_trade = await conn.fetchrow(
            """
            INSERT INTO trades (user_email, symbol, entry_price, exit_price, position, size, pnl, notes, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            email,
            trade.get("symbol"),
            trade.get("entry_price"),
            trade.get("exit_price"),
            trade.get("position"),
            trade.get("size"),
            trade.get("pnl"),
            trade.get("notes"),
            datetime.utcnow()
        )
        return dict(new_trade)

@app.get("/api/blog")
async def get_blog_posts():
    async with db_pool.acquire() as conn:
        posts = await conn.fetch("SELECT * FROM blog_posts ORDER BY created_at DESC")
        return [dict(p) for p in posts]

# Serve frontend - MUST be last
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    possible_paths = [
        Path("index.html"),
        Path("frontend/index.html"),
        project_root / "index.html",
        project_root / "frontend" / "index.html",
    ]

    for path in possible_paths:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())

    # Return inline HTML if file not found
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pipways AI</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100 min-h-screen flex items-center justify-center">
        <div class="bg-white p-8 rounded-xl shadow-lg max-w-md w-full">
            <h1 class="text-2xl font-bold mb-4">Pipways AI</h1>
            <p class="mb-4">Index file not found. Please upload index.html</p>
            <a href="/setup" class="text-purple-600 hover:underline">Go to Setup Page</a>
        </div>
    </body>
    </html>
    """)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
