"""
Pipways Trading Platform - Production Version
"""
import os
import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext

try:
    import jwt as pyjwt
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyJWT==2.8.0"])
    import jwt as pyjwt

import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL", "")
SECRET_KEY = os.getenv("SECRET_KEY", "pipways-secret-key")
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
db_pool: Optional[asyncpg.Pool] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

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

# ========== SETUP ROUTE (UNIQUE PATH) ==========
@app.get("/init-db", response_class=HTMLResponse)
async def init_db_page():
    """Database initialization page"""
    return HTMLResponse(content="""
<!DOCTYPE html>
<html>
<head>
    <title>Initialize Database - Pipways</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gradient-to-br from-purple-600 to-blue-600 min-h-screen flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl shadow-2xl p-8 max-w-md w-full">
        <div class="text-center mb-6">
            <div class="text-5xl mb-4">🚀</div>
            <h1 class="text-3xl font-bold text-gray-800">Database Setup</h1>
            <p class="text-gray-600 mt-2">Initialize your trading platform</p>
        </div>

        <div id="statusBox" class="hidden mb-4 p-4 rounded-lg text-center font-semibold"></div>

        <button id="initBtn" onclick="initializeDB()" 
            class="w-full bg-gradient-to-r from-green-500 to-emerald-600 text-white font-bold py-4 px-6 rounded-xl hover:shadow-lg transform hover:scale-105 transition duration-200">
            🔧 Initialize Database
        </button>

        <div class="mt-6 text-center space-y-2">
            <a href="/" class="text-purple-600 hover:underline block">← Back to Login</a>
        </div>

        <div class="mt-6 p-4 bg-gray-100 rounded-lg text-sm">
            <p class="font-bold text-gray-700 mb-2">Default Login After Setup:</p>
            <p class="text-gray-600">Email: <span class="font-mono">admin@pipways.com</span></p>
            <p class="text-gray-600">Password: <span class="font-mono">admin123</span></p>
        </div>
    </div>

    <script>
        function showStatus(msg, isError) {
            const box = document.getElementById("statusBox");
            box.textContent = msg;
            box.className = "mb-4 p-4 rounded-lg text-center font-semibold " + 
                (isError ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700");
            box.classList.remove("hidden");
        }

        async function initializeDB() {
            const btn = document.getElementById("initBtn");
            btn.disabled = true;
            btn.textContent = "Initializing...";
            showStatus("Creating tables... Please wait", false);

            try {
                const res = await fetch("/api/init", { method: "POST" });
                const data = await res.json();

                if (res.ok) {
                    showStatus("✅ " + data.message, false);
                    btn.textContent = "Database Ready!";
                    btn.classList.remove("from-green-500", "to-emerald-600");
                    btn.classList.add("from-blue-500", "to-blue-600");
                } else {
                    showStatus("❌ Error: " + (data.detail || "Unknown"), true);
                    btn.disabled = false;
                    btn.textContent = "🔧 Try Again";
                }
            } catch (e) {
                showStatus("❌ Network Error: " + e.message, true);
                btn.disabled = false;
                btn.textContent = "🔧 Try Again";
            }
        }
    </script>
</body>
</html>
    """)

@app.post("/api/init")
async def api_init():
    """Initialize database tables"""
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    async with db_pool.acquire() as conn:
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

        hashed_pw = pwd_context.hash("admin123")
        await conn.execute("""
            INSERT INTO users (name, email, password_hash, role)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (email) DO NOTHING
        """, "Admin User", "admin@pipways.com", hashed_pw, "admin")

        return {"message": "Database initialized! You can now login."}

# ========== DEBUG ENDPOINT ==========
@app.get("/api/status")
async def api_status():
    info = {
        "database_connected": db_pool is not None,
        "timestamp": datetime.utcnow().isoformat()
    }
    if db_pool:
        async with db_pool.acquire() as conn:
            tables = await conn.fetch("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            info["tables"] = [t["table_name"] for t in tables]
    return info

# ========== AUTH ENDPOINTS ==========
@app.post("/api/auth/login")
async def login(credentials: UserLogin):
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE email = $1", credentials.email)

        if not user or not pwd_context.verify(credentials.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = pyjwt.encode(
            {"sub": user["email"], "role": user["role"], "exp": datetime.utcnow() + timedelta(hours=24)},
            SECRET_KEY,
            algorithm=ALGORITHM
        )

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

@app.post("/api/auth/register")
async def register(user_data: UserRegister):
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not connected")

    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM users WHERE email = $1", user_data.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        hashed_pw = pwd_context.hash(user_data.password)
        new_user = await conn.fetchrow(
            """INSERT INTO users (name, email, password_hash, role, created_at)
            VALUES ($1, $2, $3, $4, $5) RETURNING id, name, email, role""",
            user_data.name, user_data.email, hashed_pw, "user", datetime.utcnow()
        )

        return {"message": "Registration successful", "user": dict(new_user)}

# ========== API ENDPOINTS ==========
@app.get("/api/trades")
async def get_trades(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = pyjwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    email = payload.get("sub")

    async with db_pool.acquire() as conn:
        trades = await conn.fetch(
            "SELECT * FROM trades WHERE user_email = $1 ORDER BY created_at DESC", email
        )
        return [dict(t) for t in trades]

@app.post("/api/trades")
async def create_trade(trade: dict, credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = pyjwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    email = payload.get("sub")

    async with db_pool.acquire() as conn:
        new_trade = await conn.fetchrow(
            """INSERT INTO trades (user_email, symbol, entry_price, exit_price, position, size, pnl, notes, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *""",
            email, trade.get("symbol"), trade.get("entry_price"), trade.get("exit_price"),
            trade.get("position"), trade.get("size"), trade.get("pnl"), trade.get("notes"), datetime.utcnow()
        )
        return dict(new_trade)

@app.get("/api/blog")
async def get_blog_posts():
    async with db_pool.acquire() as conn:
        posts = await conn.fetch("SELECT * FROM blog_posts ORDER BY created_at DESC")
        return [dict(p) for p in posts]

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# ========== FRONTEND (MUST BE LAST) ==========
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    possible_paths = [Path("index.html"), project_root / "index.html"]

    for path in possible_paths:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())

    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head><title>Pipways AI</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-100 min-h-screen flex items-center justify-center">
        <div class="bg-white p-8 rounded-xl shadow-lg max-w-md w-full text-center">
            <h1 class="text-2xl font-bold mb-4 text-purple-600">Pipways AI</h1>
            <p class="mb-4 text-gray-600">Index file not found</p>
            <a href="/init-db" class="inline-block bg-purple-600 text-white px-6 py-3 rounded-lg hover:bg-purple-700">
                🚀 Initialize Database
            </a>
        </div>
    </body>
    </html>
    """)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
