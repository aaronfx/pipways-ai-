from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
import asyncpg
import os
import openai
import base64
from typing import Optional

app = FastAPI(title="Pipways API")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://pipways-web.onrender.com", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Database
DATABASE_URL = os.getenv("DATABASE_URL")

async def get_db():
    conn = await asyncpg.connect(DATABASE_URL, ssl="require")
    try:
        yield conn
    finally:
        await conn.close()

# Startup - create tables
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
    
    await conn.close()

# Auth helpers
def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_password_hash(password):
    return pwd_context.hash(password)

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

# Routes
@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}

@app.post("/auth/register")
async def register(email: str, password: str, name: str, conn=Depends(get_db)):
    # Check if exists
    existing = await conn.fetchrow("SELECT id FROM users WHERE email = $1", email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    hashed = get_password_hash(password)
    user_id = await conn.fetchval(
        "INSERT INTO users (email, password_hash, name) VALUES ($1, $2, $3) RETURNING id",
        email, hashed, name
    )
    
    token = create_access_token({"sub": email})
    return {"access_token": token, "user_id": user_id, "email": email}

@app.post("/auth/login")
async def login(email: str, password: str, conn=Depends(get_db)):
    user = await conn.fetchrow("SELECT id, password_hash, name FROM users WHERE email = $1", email)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"sub": email})
    return {"access_token": token, "user_id": user["id"], "name": user["name"]}

@app.get("/trades")
async def get_trades(current_user: str = Depends(get_current_user), conn=Depends(get_db)):
    user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
    trades = await conn.fetch(
        "SELECT * FROM trades WHERE user_id = $1 ORDER BY created_at DESC",
        user["id"]
    )
    return [dict(t) for t in trades]

@app.post("/trades")
async def create_trade(
    pair: str,
    direction: str,
    pips: int,
    grade: str,
    entry_price: Optional[float] = None,
    exit_price: Optional[float] = None,
    current_user: str = Depends(get_current_user),
    conn=Depends(get_db)
):
    user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
    trade_id = await conn.fetchval("""
        INSERT INTO trades (user_id, pair, direction, entry_price, exit_price, pips, grade)
        VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
    """, user["id"], pair, direction, entry_price, exit_price, pips, grade)
    
    return {"id": trade_id, "message": "Trade saved"}

@app.post("/analyze-chart")
async def analyze_chart(
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user)
):
    """Upload trading chart screenshot for AI analysis"""
    
    # Read image
    contents = await file.read()
    
    # Convert to base64 for OpenAI
    base64_image = base64.b64encode(contents).decode('utf-8')
    
    # Call OpenAI Vision API
    try:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional forex trading analyst. Analyze trading charts and extract: pair name, direction (LONG/SHORT), entry price, exit price, stop loss, take profit, and grade the trade setup (A, B, or C). Respond in JSON format."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this trading chart screenshot. Extract trade details and provide a grade."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                    ]
                }
            ],
            max_tokens=500
        )
        
        analysis = response.choices[0].message.content
        
        return {
            "analysis": analysis,
            "filename": file.filename
        }
        
    except Exception as e:
        # Fallback if OpenAI not configured
        return {
            "analysis": "AI analysis temporarily unavailable. Please enter trade details manually.",
            "error": str(e),
            "fallback": True
        }

@app.get("/mentor-chat")
async def mentor_chat(message: str, current_user: str = Depends(get_current_user)):
    """Get AI mentor response based on user's trading history"""
    
    try:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a disciplined forex trading mentor. Focus on risk management, trading psychology, and process adherence. Keep responses concise and actionable."
                },
                {
                    "role": "user",
                    "content": message
                }
            ],
            max_tokens=300
        )
        
        return {"response": response.choices[0].message.content}
        
    except Exception as e:
        # Fallback responses
        fallbacks = [
            "Focus on your process, not the outcome. Did you follow your trading plan?",
            "Risk management is key. Never risk more than 1-2% per trade.",
            "Emotional trading leads to losses. Take a break if you're feeling frustrated.",
            "Patience is a trader's greatest virtue. Wait for your setup.",
            "Review your losing trades objectively. What can you learn?"
        ]
        import random
        return {"response": random.choice(fallbacks), "fallback": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
