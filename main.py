from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from datetime import datetime, timedelta
import asyncpg
import os
import base64
import requests
import bcrypt
from typing import Optional
import json

app = FastAPI(title="Pipways API")

# CORS - Allow all origins for Render deployment flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()

# OpenRouter Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Database
DATABASE_URL = os.getenv("DATABASE_URL")

# Default admin credentials
DEFAULT_ADMIN_EMAIL = "admin@pipways.com"
DEFAULT_ADMIN_PASSWORD = "admin123"

async def get_db():
    conn = await asyncpg.connect(DATABASE_URL, ssl="require")
    try:
        yield conn
    finally:
        await conn.close()

# Password hashing using bcrypt directly
def get_password_hash(password: str) -> str:
    # bcrypt has a 72 byte limit
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return email
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# OpenRouter API Helper
def openrouter_chat(messages, model="anthropic/claude-3.5-sonnet"):
    """Call OpenRouter API for chat completions"""
    if not OPENROUTER_API_KEY:
        return None, "OpenRouter API key not configured"
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://pipways-web.onrender.com",
        "X-Title": "Pipways Trading Platform"
    }
    
    data = {
        "model": model,
        "messages": messages,
        "max_tokens": 500
    }
    
    try:
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, str(e)

def openrouter_vision(image_base64, prompt, model="anthropic/claude-3.5-sonnet"):
    """Call OpenRouter API for vision/image analysis"""
    if not OPENROUTER_API_KEY:
        return None, "OpenRouter API key not configured"
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://pipways-web.onrender.com",
        "X-Title": "Pipways Trading Platform"
    }
    
    data = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a professional forex trading analyst. Analyze trading charts and extract: pair name, direction (LONG/SHORT), entry price, exit price, stop loss, take profit, and grade the trade setup (A, B, or C). Be concise and return structured data."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 500
    }
    
    try:
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, str(e)

# Startup - create tables and default admin
@app.on_event("startup")
async def startup():
    conn = await asyncpg.connect(DATABASE_URL, ssl="require")
    
    # Users table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            name VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Trades table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            pair VARCHAR(10) NOT NULL,
            direction VARCHAR(10) NOT NULL,
            entry_price DECIMAL(10,5),
            exit_price DECIMAL(10,5),
            pips INTEGER,
            grade VARCHAR(5),
            screenshot_url TEXT,
            ai_analysis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create default admin user if it doesn't exist
    try:
        existing_admin = await conn.fetchrow("SELECT id FROM users WHERE email = $1", DEFAULT_ADMIN_EMAIL)
        if not existing_admin:
            hashed = get_password_hash(DEFAULT_ADMIN_PASSWORD)
            await conn.execute(
                "INSERT INTO users (email, password_hash, name) VALUES ($1, $2, $3)",
                DEFAULT_ADMIN_EMAIL, hashed, "Admin"
            )
            print(f"Default admin created: {DEFAULT_ADMIN_EMAIL} / {DEFAULT_ADMIN_PASSWORD}")
    except Exception as e:
        print(f"Error creating admin: {e}")
    
    await conn.close()

# Routes
@app.get("/health")
async def health():
    return {
        "status": "ok", 
        "version": "1.0.0",
        "openrouter_configured": bool(OPENROUTER_API_KEY)
    }

@app.post("/auth/register")
async def register(
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
    conn=Depends(get_db)
):
    try:
        # Check if exists
        existing = await conn.fetchrow("SELECT id FROM users WHERE email = $1", email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Validate password length (max 72 bytes for bcrypt)
        password_bytes = password.encode('utf-8')
        if len(password_bytes) > 72:
            raise HTTPException(status_code=400, detail="Password is too long (max 72 characters)")
        
        # Create user
        hashed = get_password_hash(password)
        user_id = await conn.fetchval(
            "INSERT INTO users (email, password_hash, name) VALUES ($1, $2, $3) RETURNING id",
            email, hashed, name
        )
        
        token = create_access_token({"sub": email})
        return {"access_token": token, "user_id": user_id, "email": email, "name": name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.post("/auth/login")
async def login(
    email: str = Form(...),
    password: str = Form(...),
    conn=Depends(get_db)
):
    try:
        user = await conn.fetchrow("SELECT id, password_hash, name FROM users WHERE email = $1", email)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        if not verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        token = create_access_token({"sub": email})
        return {"access_token": token, "user_id": user["id"], "name": user["name"], "email": email}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.get("/trades")
async def get_trades(current_user: str = Depends(get_current_user), conn=Depends(get_db)):
    try:
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        trades = await conn.fetch(
            "SELECT * FROM trades WHERE user_id = $1 ORDER BY created_at DESC",
            user["id"]
        )
        return [dict(t) for t in trades]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch trades: {str(e)}")

@app.post("/trades")
async def create_trade(
    pair: str = Form(...),
    direction: str = Form(...),
    pips: int = Form(...),
    grade: str = Form(...),
    entry_price: Optional[float] = Form(None),
    exit_price: Optional[float] = Form(None),
    current_user: str = Depends(get_current_user),
    conn=Depends(get_db)
):
    try:
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        trade_id = await conn.fetchval("""
            INSERT INTO trades (user_id, pair, direction, entry_price, exit_price, pips, grade)
            VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
        """, user["id"], pair, direction, entry_price, exit_price, pips, grade)
        
        return {"id": trade_id, "message": "Trade saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save trade: {str(e)}")

@app.post("/analyze-chart")
async def analyze_chart(
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user)
):
    """Upload trading chart screenshot for AI analysis via OpenRouter"""
    
    try:
        # Read image
        contents = await file.read()
        base64_image = base64.b64encode(contents).decode('utf-8')
        
        # Call OpenRouter Vision API
        analysis, error = openrouter_vision(
            base64_image,
            "Analyze this trading chart screenshot. Extract: pair name, direction (LONG/SHORT), entry price, exit price, stop loss, take profit. Grade the setup A/B/C and explain why."
        )
        
        if error:
            return {
                "analysis": "AI analysis temporarily unavailable. Please enter trade details manually.",
                "error": error,
                "fallback": True
            }
        
        return {
            "analysis": analysis,
            "filename": file.filename,
            "model": "claude-3.5-sonnet"
        }
    except Exception as e:
        return {
            "analysis": "Failed to analyze image. Please try again or enter details manually.",
            "error": str(e),
            "fallback": True
        }

@app.get("/mentor-chat")
async def mentor_chat(message: str, current_user: str = Depends(get_current_user)):
    """Get AI mentor response via OpenRouter"""
    
    try:
        messages = [
            {
                "role": "system",
                "content": "You are a disciplined forex trading mentor. Focus on risk management, trading psychology, and process adherence. Keep responses concise (2-3 sentences) and actionable. Be encouraging but firm about discipline."
            },
            {
                "role": "user",
                "content": message
            }
        ]
        
        response, error = openrouter_chat(messages)
        
        if error:
            # Fallback responses
            fallbacks = [
                "Focus on your process, not the outcome. Did you follow your trading plan?",
                "Risk management is key. Never risk more than 1-2% per trade.",
                "Emotional trading leads to losses. Take a break if you're feeling frustrated.",
                "Patience is a trader's greatest virtue. Wait for your setup.",
                "Review your losing trades objectively. What can you learn?"
            ]
            import random
            return {
                "response": random.choice(fallbacks),
                "fallback": True,
                "error": error
            }
        
        return {
            "response": response,
            "model": "claude-3.5-sonnet"
        }
    except Exception as e:
        return {
            "response": "I'm here to help with your trading psychology. What would you like to discuss?",
            "fallback": True,
            "error": str(e)
        }

@app.get("/models")
async def list_models(current_user: str = Depends(get_current_user)):
    """List available models on OpenRouter"""
    if not OPENROUTER_API_KEY:
        return {"error": "OpenRouter not configured"}
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://pipways-web.onrender.com",
        "X-Title": "Pipways Trading Platform"
    }
    
    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
