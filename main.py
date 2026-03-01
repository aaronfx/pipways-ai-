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
import json
import re
from typing import Optional

app = FastAPI(title="Pipways API")

# CORS
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

# Password hashing
def get_password_hash(password: str) -> str:
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
        "max_tokens": 1000
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
                "content": """You are a professional forex trading analyst. Analyze the provided chart and respond in this exact JSON format:
{
    "pair": "EURUSD",
    "direction": "LONG/SHORT",
    "setup_quality": "A/B/C",
    "entry_price": "1.0850",
    "stop_loss": "1.0820",
    "take_profit": "1.0900",
    "risk_reward": "1:1.67",
    "analysis": "Clear trendline break with volume confirmation...",
    "key_levels": ["1.0850", "1.0820", "1.0900"],
    "recommendations": "Wait for pullback to 1.0840 before entering..."
}"""
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
        "max_tokens": 1000
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

def parse_analysis_response(analysis_text):
    """Parse AI response into structured format"""
    try:
        # Try to extract JSON from response
        json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except:
        pass
    
    # Fallback: return structured fallback
    return {
        "pair": "Unknown",
        "direction": "Unknown",
        "setup_quality": "N/A",
        "entry_price": "N/A",
        "stop_loss": "N/A",
        "take_profit": "N/A",
        "risk_reward": "N/A",
        "analysis": analysis_text,
        "key_levels": [],
        "recommendations": "Please review manually"
    }

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
    
    # Chart analyses table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS chart_analyses (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            image_data TEXT,
            analysis_result JSONB,
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
        existing = await conn.fetchrow("SELECT id FROM users WHERE email = $1", email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        password_bytes = password.encode('utf-8')
        if len(password_bytes) > 72:
            raise HTTPException(status_code=400, detail="Password is too long (max 72 characters)")
        
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
    current_user: str = Depends(get_current_user),
    conn=Depends(get_db)
):
    """Upload trading chart screenshot for AI analysis"""
    
    try:
        # Read and encode image
        contents = await file.read()
        base64_image = base64.b64encode(contents).decode('utf-8')
        
        # Call OpenRouter Vision API
        analysis_text, error = openrouter_vision(
            base64_image,
            "Analyze this trading chart. Identify the currency pair, trend direction, key support/resistance levels, and provide a trade setup grade (A/B/C)."
        )
        
        if error:
            return {
                "success": False,
                "analysis": None,
                "raw_response": None,
                "error": error,
                "image_data": base64_image
            }
        
        # Parse structured response
        parsed_analysis = parse_analysis_response(analysis_text)
        
        # Save to database
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        await conn.execute(
            "INSERT INTO chart_analyses (user_id, image_data, analysis_result) VALUES ($1, $2, $3)",
            user["id"], base64_image, json.dumps(parsed_analysis)
        )
        
        return {
            "success": True,
            "analysis": parsed_analysis,
            "raw_response": analysis_text,
            "image_data": base64_image,
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "analysis": None,
            "raw_response": None,
            "error": str(e),
            "image_data": None
        }

@app.get("/chart-analyses")
async def get_chart_analyses(current_user: str = Depends(get_current_user), conn=Depends(get_db)):
    """Get user's chart analysis history"""
    try:
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        analyses = await conn.fetch(
            "SELECT id, analysis_result, created_at FROM chart_analyses WHERE user_id = $1 ORDER BY created_at DESC",
            user["id"]
        )
        return [dict(a) for a in analyses]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch analyses: {str(e)}")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
