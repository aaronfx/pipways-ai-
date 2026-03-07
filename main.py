"""
Pipways Trading Platform - Integrated Setup Version
"""
import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
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
db_pool = None

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

# ========== SETUP API ENDPOINT ==========
@app.post("/api/setup-db")
async def setup_database():
    """Create database tables and default user"""
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

        return {"message": "Database initialized! You can now login with admin@pipways.com / admin123"}

@app.get("/api/check-db")
async def check_database():
    """Check if database is set up"""
    if not db_pool:
        return {"connected": False, "setup": False}

    try:
        async with db_pool.acquire() as conn:
            tables = await conn.fetch("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'users'
            """)
            has_users = len(tables) > 0

            if has_users:
                count = await conn.fetchval("SELECT COUNT(*) FROM users")
                return {"connected": True, "setup": True, "users": count}
            else:
                return {"connected": True, "setup": False, "users": 0}
    except Exception as e:
        return {"connected": True, "setup": False, "error": str(e)}

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

# ========== FRONTEND WITH INTEGRATED SETUP ==========
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    # Check if we can find index.html
    possible_paths = [Path("index.html"), project_root / "index.html"]
    index_content = None

    for path in possible_paths:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                index_content = f.read()
            break

    # If index.html exists, inject setup button into it
    if index_content:
        # Add setup script before closing body tag
        setup_script = """
    <div id="setup-banner" style="display:none; position:fixed; top:0; left:0; right:0; background:linear-gradient(90deg, #667eea, #764ba2); color:white; padding:15px; text-align:center; z-index:9999;">
        <span style="font-weight:bold;">🚀 Database Not Initialized!</span> 
        <button onclick="initDatabase()" style="margin-left:20px; padding:8px 20px; background:white; color:#667eea; border:none; border-radius:5px; cursor:pointer; font-weight:bold;">
            Initialize Now
        </button>
        <span id="setup-status" style="margin-left:20px;"></span>
    </div>
    <script>
        // Check database status on load
        fetch('/api/check-db')
            .then(r => r.json())
            .then(data => {
                if (data.connected && !data.setup) {
                    document.getElementById('setup-banner').style.display = 'block';
                }
            });

        function initDatabase() {
            const btn = document.querySelector('#setup-banner button');
            const status = document.getElementById('setup-status');
            btn.disabled = true;
            btn.textContent = 'Initializing...';
            status.textContent = 'Creating tables...';

            fetch('/api/setup-db', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    status.textContent = '✅ ' + data.message;
                    btn.textContent = 'Done!';
                    setTimeout(() => {
                        document.getElementById('setup-banner').style.display = 'none';
                        alert('Database initialized! Login with: admin@pipways.com / admin123');
                    }, 2000);
                })
                .catch(e => {
                    status.textContent = '❌ Error: ' + e.message;
                    btn.disabled = false;
                    btn.textContent = 'Try Again';
                });
        }
    </script>
</body>"""

        # Replace closing body tag with our script
        if "</body>" in index_content:
            index_content = index_content.replace("</body>", setup_script)
        else:
            index_content += setup_script

        return HTMLResponse(content=index_content)

    # Fallback HTML if no index.html found
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pipways AI - Trading Platform</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 min-h-screen">
    <!-- Setup Banner -->
    <div id="setup-banner" class="hidden bg-gradient-to-r from-purple-600 to-indigo-600 text-white p-4 text-center">
        <span class="font-bold text-lg">🚀 Database Not Initialized!</span>
        <button onclick="initDatabase()" class="ml-4 px-6 py-2 bg-white text-purple-600 rounded-lg font-bold hover:bg-gray-100">
            Initialize Database
        </button>
        <span id="setup-status" class="ml-4"></span>
    </div>

    <!-- Main App -->
    <div id="app">
        <nav class="bg-gradient-to-r from-purple-600 to-indigo-600 text-white p-4">
            <div class="max-w-7xl mx-auto flex justify-between items-center">
                <h1 class="text-2xl font-bold">Pipways AI</h1>
            </div>
        </nav>

        <div class="max-w-md mx-auto mt-10 p-8 bg-white rounded-xl shadow-lg">
            <h2 class="text-2xl font-bold text-center mb-6">Welcome Back</h2>
            <form id="login-form" onsubmit="handleLogin(event)">
                <div class="mb-4">
                    <label class="block text-gray-700 mb-2">Email</label>
                    <input type="email" id="email" value="admin@pipways.com" class="w-full px-4 py-2 border rounded-lg focus:outline-none focus:border-purple-500">
                </div>
                <div class="mb-6">
                    <label class="block text-gray-700 mb-2">Password</label>
                    <input type="password" id="password" value="admin123" class="w-full px-4 py-2 border rounded-lg focus:outline-none focus:border-purple-500">
                </div>
                <button type="submit" class="w-full bg-gradient-to-r from-purple-600 to-indigo-600 text-white font-bold py-3 rounded-lg hover:opacity-90">
                    Sign In
                </button>
            </form>
            <div id="error" class="mt-4 p-3 bg-red-100 text-red-700 rounded-lg hidden"></div>
        </div>
    </div>

    <script>
        // Check database status
        fetch('/api/check-db')
            .then(r => r.json())
            .then(data => {
                console.log('DB Status:', data);
                if (data.connected && !data.setup) {
                    document.getElementById('setup-banner').classList.remove('hidden');
                }
            });

        function initDatabase() {
            const btn = document.querySelector('#setup-banner button');
            const status = document.getElementById('setup-status');
            btn.disabled = true;
            btn.textContent = 'Initializing...';

            fetch('/api/setup-db', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    status.textContent = '✅ Success!';
                    btn.textContent = 'Done';
                    setTimeout(() => {
                        document.getElementById('setup-banner').classList.add('hidden');
                        alert('Database initialized! Login with: admin@pipways.com / admin123');
                    }, 1500);
                })
                .catch(e => {
                    status.textContent = '❌ Error: ' + e.message;
                    btn.disabled = false;
                    btn.textContent = 'Try Again';
                });
        }

        function handleLogin(e) {
            e.preventDefault();
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;

            fetch('/api/auth/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password})
            })
            .then(r => r.json())
            .then(data => {
                if (data.access_token) {
                    localStorage.setItem('token', data.access_token);
                    alert('Login successful!');
                    // Redirect to dashboard or show logged-in UI
                } else {
                    document.getElementById('error').textContent = data.detail || 'Login failed';
                    document.getElementById('error').classList.remove('hidden');
                }
            })
            .catch(e => {
                document.getElementById('error').textContent = 'Error: ' + e.message;
                document.getElementById('error').classList.remove('hidden');
            });
        }
    </script>
</body>
</html>
    """)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
