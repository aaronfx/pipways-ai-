from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, Form, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from datetime import datetime, timedelta
import asyncpg
import os
import base64
import requests
import bcrypt
import json
import re
import uuid
import io
import csv
import pandas as pd
from typing import Optional, List, Dict, Any
from pathlib import Path
import shutil
from slugify import slugify
import magic

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

# File upload settings
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
MEDIA_DIR = UPLOAD_DIR / "media"
MEDIA_DIR.mkdir(exist_ok=True)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

ALLOWED_TRADE_FILE_TYPES = {
    'application/pdf': '.pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    'application/msword': '.doc',
    'text/csv': '.csv',
    'application/vnd.ms-excel': '.xls',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/webp': '.webp'
}

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

async def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security), conn=Depends(get_db)):
    email = await get_current_user(credentials)
    user = await conn.fetchrow("SELECT is_admin FROM users WHERE email = $1", email)
    if not user or not user['is_admin']:
        raise HTTPException(status_code=403, detail="Admin access required")
    return email

# OpenRouter API Helpers
def openrouter_chat(messages, model="anthropic/claude-3.5-sonnet", max_tokens=1000):
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
        "max_tokens": max_tokens
    }
    
    try:
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, str(e)

def openrouter_vision(image_base64, prompt, model="anthropic/claude-3.5-sonnet"):
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
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"}
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
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, str(e)

# File processing helpers
def extract_text_from_pdf(file_data: bytes) -> str:
    try:
        import PyPDF2
        pdf_file = io.BytesIO(file_data)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        return f"Error extracting PDF: {str(e)}"

def extract_text_from_docx(file_data: bytes) -> str:
    try:
        import docx
        doc_file = io.BytesIO(file_data)
        doc = docx.Document(doc_file)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text
    except Exception as e:
        return f"Error extracting DOCX: {str(e)}"

def parse_csv_trades(file_data: bytes) -> List[Dict]:
    try:
        csv_file = io.StringIO(file_data.decode('utf-8'))
        reader = csv.DictReader(csv_file)
        trades = list(reader)
        return trades
    except Exception as e:
        return [{"error": str(e)}]

def parse_mt4_statement(file_data: bytes) -> Dict:
    """Parse MT4/MT5 HTML or CSV statement"""
    content = file_data.decode('utf-8', errors='ignore')
    
    # Try to extract trades from HTML statement
    trades = []
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(content, 'html.parser')
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 10:  # Likely a trade row
                    trade = {
                        'ticket': cols[0].text.strip(),
                        'open_time': cols[1].text.strip(),
                        'type': cols[2].text.strip(),
                        'size': cols[3].text.strip(),
                        'item': cols[4].text.strip(),
                        'price': cols[5].text.strip(),
                        'sl': cols[6].text.strip(),
                        'tp': cols[7].text.strip(),
                        'close_time': cols[8].text.strip(),
                        'price_close': cols[9].text.strip(),
                        'commission': cols[10].text.strip() if len(cols) > 10 else '',
                        'taxes': cols[11].text.strip() if len(cols) > 11 else '',
                        'swap': cols[12].text.strip() if len(cols) > 12 else '',
                        'profit': cols[13].text.strip() if len(cols) > 13 else ''
                    }
                    trades.append(trade)
    except:
        pass
    
    return {"trades": trades, "raw_content": content[:5000]}

# AI Analysis functions
async def analyze_trader_performance(trade_data: Dict, user_id: int) -> Dict:
    """Comprehensive AI analysis of trading performance"""
    
    prompt = f"""Analyze this trading data and provide a comprehensive assessment:

Trading Data: {json.dumps(trade_data, indent=2)}

Provide your analysis in this exact JSON format:
{{
    "trader_type": "scalper/day_trader/swing_trader/position_trader",
    "trader_type_confidence": 85,
    "trader_score": 78,
    "score_breakdown": {{
        "risk_management": 80,
        "consistency": 75,
        "profitability": 82,
        "psychology": 70,
        "strategy": 85
    }},
    "mistakes_detected": [
        {{
            "mistake": "Holding losers too long",
            "frequency": "high",
            "impact": "Significant drawdowns",
            "evidence": "Average loss 3x larger than average win"
        }}
    ],
    "patterns_detected": [
        {{
            "pattern": "Revenge trading after losses",
            "occurrence": "After 3+ consecutive losses",
            "consequence": "Increased position sizes, deviation from strategy"
        }}
    ],
    "strengths": [
        "Good win rate on EURUSD pairs",
        "Consistent risk per trade"
    ],
    "weaknesses": [
        "Overtrading during volatile sessions",
        "Poor exit timing"
    ],
    "recommendations": [
        "Implement hard stop-loss at 2% account risk",
        "Take 15-minute break after 2 consecutive losses",
        "Focus on A-grade setups only"
    ],
    "learning_resources": [
        "Book: Trading in the Zone by Mark Douglas",
        "Course: Advanced Risk Management",
        "Exercise: 20-trade challenge with strict rules"
    ],
    "projected_improvement": "With recommended changes, expect 15-20% improvement in risk-adjusted returns within 3 months"
}}"""

    messages = [
        {
            "role": "system",
            "content": "You are an expert trading psychologist and performance analyst with 20+ years experience. Be thorough, specific, and actionable."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]
    
    response, error = openrouter_chat(messages, max_tokens=2000)
    
    if error:
        return {
            "success": False,
            "error": error,
            "fallback_analysis": {
                "trader_type": "Unknown",
                "trader_score": 50,
                "recommendations": ["Please upload clearer trade data for analysis"]
            }
        }
    
    try:
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            analysis = json.loads(json_match.group())
            analysis['success'] = True
            return analysis
    except Exception as e:
        pass
    
    return {
        "success": False,
        "raw_response": response,
        "error": "Failed to parse analysis"
    }

async def get_personalized_mentorship(user_id: int, context: Dict, conn) -> Dict:
    """Generate personalized mentorship based on user's trading history"""
    
    # Get user's recent analyses and trades
    recent_analyses = await conn.fetch(
        "SELECT analysis_result FROM trade_analysis_uploads WHERE user_id = $1 ORDER BY created_at DESC LIMIT 3",
        user_id
    )
    
    recent_trades = await conn.fetch(
        "SELECT * FROM trades WHERE user_id = $1 ORDER BY created_at DESC LIMIT 10",
        user_id
    )
    
    user_history = {
        "recent_analyses": [dict(a) for a in recent_analyses],
        "recent_trades": [dict(t) for t in recent_trades],
        "current_context": context
    }
    
    prompt = f"""Based on this trader's history and current question, provide personalized mentorship:

User History: {json.dumps(user_history, indent=2, default=str)}

Current Question/Context: {context.get('message', 'General guidance')}

Provide response in this JSON format:
{{
    "personalized_response": "Specific advice addressing their patterns...",
    "identified_pattern": "Reference to their specific recurring issue",
    "actionable_steps": ["Step 1", "Step 2", "Step 3"],
    "relevant_resources": ["Specific resource based on their needs"],
    "accountability_check": "Question to make them reflect on their commitment",
    "encouragement": "Personalized motivational message"
}}"""

    messages = [
        {
            "role": "system",
            "content": "You are a compassionate but firm trading mentor who remembers the trader's history and provides personalized, accountable guidance."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]
    
    response, error = openrouter_chat(messages, max_tokens=1500)
    
    if error:
        return {
            "success": False,
            "error": error,
            "fallback_response": "I'm here to support your trading journey. Let's focus on one improvement at a time."
        }
    
    try:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except:
        pass
    
    return {
        "personalized_response": response,
        "success": True
    }

# Startup
@app.on_event("startup")
async def startup():
    conn = await asyncpg.connect(DATABASE_URL, ssl="require")
    
    # Users table with admin flag
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            name VARCHAR(100),
            is_admin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Add is_admin column if not exists
    try:
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE")
    except:
        pass
    
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
    
    # Blog posts table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS blog_posts (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            slug VARCHAR(255) UNIQUE NOT NULL,
            content TEXT NOT NULL,
            excerpt TEXT,
            featured_image TEXT,
            meta_title VARCHAR(70),
            meta_description VARCHAR(160),
            meta_keywords TEXT,
            author_id INTEGER REFERENCES users(id),
            category VARCHAR(100),
            tags TEXT[],
            status VARCHAR(20) DEFAULT 'draft',
            published_at TIMESTAMP,
            view_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Blog categories table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS blog_categories (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            slug VARCHAR(100) UNIQUE NOT NULL,
            description TEXT,
            meta_title VARCHAR(70),
            meta_description VARCHAR(160),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Media uploads table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS media_files (
            id SERIAL PRIMARY KEY,
            filename VARCHAR(255) NOT NULL,
            original_name VARCHAR(255) NOT NULL,
            file_path TEXT NOT NULL,
            file_type VARCHAR(50) NOT NULL,
            file_size INTEGER NOT NULL,
            mime_type VARCHAR(100),
            alt_text VARCHAR(255),
            uploaded_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Trade analysis uploads table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS trade_analysis_uploads (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            filename VARCHAR(255) NOT NULL,
            file_type VARCHAR(50) NOT NULL,
            file_data TEXT,
            extracted_data JSONB,
            analysis_result JSONB,
            trader_type VARCHAR(50),
            trader_score INTEGER,
            mistakes_detected JSONB,
            patterns_detected JSONB,
            recommendations TEXT[],
            learning_resources TEXT[],
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Mentorship sessions table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS mentorship_sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            session_type VARCHAR(50),
            context JSONB,
            ai_response TEXT,
            resources_suggested JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create default admin user
    try:
        existing_admin = await conn.fetchrow("SELECT id FROM users WHERE email = $1", DEFAULT_ADMIN_EMAIL)
        if not existing_admin:
            hashed = get_password_hash(DEFAULT_ADMIN_PASSWORD)
            await conn.execute(
                "INSERT INTO users (email, password_hash, name, is_admin) VALUES ($1, $2, $3, $4)",
                DEFAULT_ADMIN_EMAIL, hashed, "Admin", True
            )
            print(f"Default admin created: {DEFAULT_ADMIN_EMAIL} / {DEFAULT_ADMIN_PASSWORD}")
    except Exception as e:
        print(f"Error creating admin: {e}")
    
    await conn.close()

# Health check
@app.get("/health")
async def health():
    return {
        "status": "ok", 
        "version": "2.0.0",
        "openrouter_configured": bool(OPENROUTER_API_KEY),
        "features": ["blog", "trade_analysis", "mentorship", "admin"]
    }

# ==================== AUTHENTICATION ====================

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
        return {"access_token": token, "user_id": user_id, "email": email, "name": name, "is_admin": False}
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
        user = await conn.fetchrow("SELECT id, password_hash, name, is_admin FROM users WHERE email = $1", email)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        if not verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        token = create_access_token({"sub": email})
        return {
            "access_token": token, 
            "user_id": user["id"], 
            "name": user["name"], 
            "email": email,
            "is_admin": user["is_admin"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

# ==================== TRADING JOURNAL ====================

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
    pips: float = Form(...),
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
        """, user["id"], pair.upper(), direction, entry_price, exit_price, pips, grade)
        
        return {"id": trade_id, "message": "Trade saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save trade: {str(e)}")

# ==================== PRE-TRADE AI ANALYSIS ====================

@app.post("/analyze-trade-setup")
async def analyze_trade_setup(
    pair: str = Form(...),
    direction: str = Form(...),
    entry_price: float = Form(...),
    stop_loss: Optional[float] = Form(None),
    take_profit: Optional[float] = Form(None),
    risk_percent: Optional[float] = Form(None),
    setup_description: Optional[str] = Form(None),
    current_user: str = Depends(get_current_user),
    conn=Depends(get_db)
):
    """AI analyzes trade setup BEFORE user executes it"""
    
    prompt = f"""Analyze this trade setup critically:

Pair: {pair}
Direction: {direction}
Entry: {entry_price}
Stop Loss: {stop_loss or 'Not set'}
Take Profit: {take_profit or 'Not set'}
Risk: {risk_percent or 'Unknown'}%
Setup Description: {setup_description or 'None provided'}

Provide analysis in this JSON format:
{{
    "setup_grade": "A/B/C/D",
    "grade_reason": "Explanation of grade",
    "risk_reward_ratio": "1:2.5",
    "probability_of_success": 65,
    "key_concerns": ["Concern 1", "Concern 2"],
    "suggestions": ["Improvement 1", "Improvement 2"],
    "approval": "approved/conditional/rejected",
    "conditional_requirements": ["Only if these are met..."],
    "better_alternative": "Consider this instead...",
    "psychology_check": "Are you trading emotionally right now?"
}}"""

    messages = [
        {
            "role": "system",
            "content": "You are a ruthless, disciplined trading coach who prevents bad trades. Be harsh but constructive. Protect the trader from themselves."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]
    
    response, error = openrouter_chat(messages, max_tokens=1500)
    
    if error:
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {error}")
    
    try:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            analysis = json.loads(json_match.group())
            return {"success": True, "analysis": analysis}
    except:
        pass
    
    return {"success": False, "raw_response": response}

# ==================== CHART ANALYSIS ====================

@app.post("/analyze-chart")
async def analyze_chart(
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
    conn=Depends(get_db)
):
    try:
        contents = await file.read()
        base64_image = base64.b64encode(contents).decode('utf-8')
        
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
        
        parsed_analysis = parse_analysis_response(analysis_text)
        
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

def parse_analysis_response(analysis_text):
    try:
        json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except:
        pass
    
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

@app.get("/chart-analyses")
async def get_chart_analyses(current_user: str = Depends(get_current_user), conn=Depends(get_db)):
    try:
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        analyses = await conn.fetch(
            "SELECT id, analysis_result, created_at FROM chart_analyses WHERE user_id = $1 ORDER BY created_at DESC",
            user["id"]
        )
        return [dict(a) for a in analyses]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch analyses: {str(e)}")

# ==================== ADVANCED TRADE ANALYSIS UPLOAD ====================

@app.post("/analyze-trade-file")
async def analyze_trade_file(
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
    conn=Depends(get_db)
):
    """
    Upload and analyze trading results from PDF, DOC, CSV, screenshots, etc.
    """
    try:
        contents = await file.read()
        file_size = len(contents)
        
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large (max 50MB)")
        
        # Detect file type
        mime = magic.Magic(mime=True)
        file_type = mime.from_buffer(contents)
        
        if file_type not in ALLOWED_TRADE_FILE_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type}")
        
        # Extract data based on file type
        extracted_data = {}
        
        if file_type == 'application/pdf':
            extracted_data['text'] = extract_text_from_pdf(contents)
            extracted_data['type'] = 'pdf_statement'
        elif file_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword']:
            extracted_data['text'] = extract_text_from_docx(contents)
            extracted_data['type'] = 'doc_report'
        elif file_type == 'text/csv':
            extracted_data['trades'] = parse_csv_trades(contents)
            extracted_data['type'] = 'csv_trades'
        elif file_type in ['image/png', 'image/jpeg', 'image/webp']:
            # For screenshots, use vision API
            base64_image = base64.b64encode(contents).decode('utf-8')
            extracted_data['image_data'] = base64_image
            extracted_data['type'] = 'screenshot'
        elif 'mt4' in file.filename.lower() or 'mt5' in file.filename.lower():
            extracted_data = parse_mt4_statement(contents)
            extracted_data['type'] = 'mt_statement'
        
        # Save file
        file_ext = ALLOWED_TRADE_FILE_TYPES.get(file_type, '.bin')
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = MEDIA_DIR / unique_filename
        
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Perform AI analysis
        analysis = await analyze_trader_performance(extracted_data, 0)
        
        if not analysis.get('success'):
            return {
                "success": False,
                "error": analysis.get('error', 'Analysis failed'),
                "extracted_preview": str(extracted_data)[:500]
            }
        
        # Save to database
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        
        upload_id = await conn.fetchval("""
            INSERT INTO trade_analysis_uploads 
            (user_id, filename, file_type, file_data, extracted_data, analysis_result,
             trader_type, trader_score, mistakes_detected, patterns_detected, 
             recommendations, learning_resources)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING id
        """,
            user["id"],
            file.filename,
            file_type,
            str(file_path),
            json.dumps(extracted_data),
            json.dumps(analysis),
            analysis.get('trader_type'),
            analysis.get('trader_score'),
            json.dumps(analysis.get('mistakes_detected', [])),
            json.dumps(analysis.get('patterns_detected', [])),
            analysis.get('recommendations', []),
            analysis.get('learning_resources', [])
        )
        
        return {
            "success": True,
            "upload_id": upload_id,
            "analysis": analysis,
            "file_saved": str(file_path)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File analysis failed: {str(e)}")

@app.get("/trade-analyses")
async def get_trade_analyses(
    current_user: str = Depends(get_current_user),
    conn=Depends(get_db)
):
    """Get user's trade analysis history"""
    try:
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        analyses = await conn.fetch("""
            SELECT id, filename, file_type, trader_type, trader_score, 
                   recommendations, created_at
            FROM trade_analysis_uploads 
            WHERE user_id = $1 
            ORDER BY created_at DESC
        """, user["id"])
        return [dict(a) for a in analyses]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trade-analysis/{analysis_id}")
async def get_trade_analysis_detail(
    analysis_id: int,
    current_user: str = Depends(get_current_user),
    conn=Depends(get_db)
):
    """Get detailed trade analysis"""
    try:
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        analysis = await conn.fetchrow("""
            SELECT * FROM trade_analysis_uploads 
            WHERE id = $1 AND user_id = $2
        """, analysis_id, user["id"])
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        return dict(analysis)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== PERSONALIZED MENTORSHIP ====================

@app.post("/mentorship/personalized")
async def get_personalized_mentorship(
    message: str = Form(...),
    context_type: Optional[str] = Form("general"),
    current_user: str = Depends(get_current_user),
    conn=Depends(get_db)
):
    """Get AI mentorship personalized to user's trading history"""
    
    user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
    
    context = {
        "message": message,
        "type": context_type,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    mentorship = await get_personalized_mentorship(user["id"], context, conn)
    
    # Save session
    await conn.execute("""
        INSERT INTO mentorship_sessions (user_id, session_type, context, ai_response, resources_suggested)
        VALUES ($1, $2, $3, $4, $5)
    """,
        user["id"],
        context_type,
        json.dumps(context),
        mentorship.get('personalized_response', mentorship.get('response', '')),
        json.dumps(mentorship.get('relevant_resources', []))
    )
    
    return mentorship

@app.get("/mentor-chat")
async def mentor_chat(
    message: str, 
    current_user: str = Depends(get_current_user),
    conn=Depends(get_db)
):
    """Legacy mentor chat - redirects to personalized version"""
    return await get_personalized_mentorship(message, "general", current_user, conn)

# ==================== BLOG SYSTEM (SEO-OPTIMIZED) ====================

@app.get("/blog/posts", response_class=JSONResponse)
async def get_blog_posts(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    category: Optional[str] = None,
    tag: Optional[str] = None,
    status: Optional[str] = "published",
    search: Optional[str] = None,
    conn=Depends(get_db)
):
    """Get blog posts with filtering and pagination"""
    try:
        offset = (page - 1) * per_page
        params = []
        where_clauses = []
        
        if status:
            where_clauses.append(f"status = ${len(params)+1}")
            params.append(status)
        
        if category:
            where_clauses.append(f"category = ${len(params)+1}")
            params.append(category)
        
        if tag:
            where_clauses.append(f"${len(params)+1} = ANY(tags)")
            params.append(tag)
        
        if search:
            where_clauses.append(f"(title ILIKE ${len(params)+1} OR content ILIKE ${len(params)+1} OR excerpt ILIKE ${len(params)+1})")
            params.append(f"%{search}%")
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Get posts
        posts = await conn.fetch(f"""
            SELECT id, title, slug, excerpt, featured_image, category, tags,
                   meta_title, meta_description, published_at, view_count, created_at
            FROM blog_posts
            WHERE {where_sql}
            ORDER BY published_at DESC NULLS LAST
            LIMIT ${len(params)+1} OFFSET ${len(params)+2}
        """, *params, per_page, offset)
        
        # Get total count
        count_result = await conn.fetchrow(f"""
            SELECT COUNT(*) as total FROM blog_posts WHERE {where_sql}
        """, *params[:-2] if params else [])
        
        return {
            "posts": [dict(p) for p in posts],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": count_result['total'] if count_result else 0,
                "total_pages": (count_result['total'] + per_page - 1) // per_page if count_result else 0
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/blog/post/{slug}", response_class=JSONResponse)
async def get_blog_post(
    slug: str,
    conn=Depends(get_db)
):
    """Get single blog post by slug"""
    try:
        post = await conn.fetchrow("""
            SELECT * FROM blog_posts WHERE slug = $1 AND status = 'published'
        """, slug)
        
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Increment view count
        await conn.execute("""
            UPDATE blog_posts SET view_count = view_count + 1 WHERE id = $1
        """, post['id'])
        
        return dict(post)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/blog/posts")
async def create_blog_post(
    title: str = Form(...),
    content: str = Form(...),
    excerpt: Optional[str] = Form(None),
    featured_image: Optional[str] = Form(None),
    meta_title: Optional[str] = Form(None),
    meta_description: Optional[str] = Form(None),
    meta_keywords: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),  # Comma-separated
    status: str = Form("draft"),
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Create new blog post (admin only)"""
    try:
        slug = slugify(title)
        
        # Ensure unique slug
        existing = await conn.fetchrow("SELECT id FROM blog_posts WHERE slug = $1", slug)
        if existing:
            slug = f"{slug}-{uuid.uuid4().hex[:8]}"
        
        # Process tags
        tag_list = [t.strip() for t in tags.split(',')] if tags else []
        
        # Auto-generate excerpt if not provided
        if not excerpt:
            excerpt = content[:200] + "..." if len(content) > 200 else content
        
        # Auto-generate meta if not provided
        if not meta_title:
            meta_title = title[:70]
        if not meta_description:
            meta_description = excerpt[:160]
        
        published_at = datetime.utcnow() if status == 'published' else None
        
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        
        post_id = await conn.fetchval("""
            INSERT INTO blog_posts 
            (title, slug, content, excerpt, featured_image, meta_title, meta_description,
             meta_keywords, author_id, category, tags, status, published_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING id
        """,
            title, slug, content, excerpt, featured_image, meta_title, meta_description,
            meta_keywords, user["id"], category, tag_list, status, published_at
        )
        
        return {
            "success": True,
            "post_id": post_id,
            "slug": slug,
            "message": "Post created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/admin/blog/posts/{post_id}")
async def update_blog_post(
    post_id: int,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    featured_image: Optional[str] = Form(None),
    meta_title: Optional[str] = Form(None),
    meta_description: Optional[str] = Form(None),
    meta_keywords: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Update blog post (admin only)"""
    try:
        # Build update dynamically
        updates = []
        params = []
        
        if title:
            updates.append("title = $" + str(len(params)+1))
            params.append(title)
            updates.append("slug = $" + str(len(params)+1))
            params.append(slugify(title))
        if content:
            updates.append("content = $" + str(len(params)+1))
            params.append(content)
        if excerpt:
            updates.append("excerpt = $" + str(len(params)+1))
            params.append(excerpt)
        if featured_image:
            updates.append("featured_image = $" + str(len(params)+1))
            params.append(featured_image)
        if meta_title:
            updates.append("meta_title = $" + str(len(params)+1))
            params.append(meta_title)
        if meta_description:
            updates.append("meta_description = $" + str(len(params)+1))
            params.append(meta_description)
        if meta_keywords:
            updates.append("meta_keywords = $" + str(len(params)+1))
            params.append(meta_keywords)
        if category:
            updates.append("category = $" + str(len(params)+1))
            params.append(category)
        if tags:
            updates.append("tags = $" + str(len(params)+1))
            params.append([t.strip() for t in tags.split(',')])
        if status:
            updates.append("status = $" + str(len(params)+1))
            params.append(status)
            if status == 'published':
                updates.append("published_at = $" + str(len(params)+1))
                params.append(datetime.utcnow())
        
        updates.append("updated_at = $" + str(len(params)+1))
        params.append(datetime.utcnow())
        params.append(post_id)
        
        await conn.execute(f"""
            UPDATE blog_posts SET {', '.join(updates)} WHERE id = ${len(params)}
        """, *params)
        
        return {"success": True, "message": "Post updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/admin/blog/posts/{post_id}")
async def delete_blog_post(
    post_id: int,
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Delete blog post (admin only)"""
    try:
        await conn.execute("DELETE FROM blog_posts WHERE id = $1", post_id)
        return {"success": True, "message": "Post deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== MEDIA MANAGEMENT ====================

@app.post("/admin/media/upload")
async def upload_media(
    file: UploadFile = File(...),
    alt_text: Optional[str] = Form(None),
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Upload media file (admin only)"""
    try:
        contents = await file.read()
        file_size = len(contents)
        
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large")
        
        # Detect mime type
        mime = magic.Magic(mime=True)
        mime_type = mime.from_buffer(contents)
        
        # Generate unique filename
        file_ext = Path(file.filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = MEDIA_DIR / unique_filename
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Save to database
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        
        media_id = await conn.fetchval("""
            INSERT INTO media_files 
            (filename, original_name, file_path, file_type, file_size, mime_type, alt_text, uploaded_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
        """,
            unique_filename,
            file.filename,
            str(file_path),
            file_ext.replace('.', ''),
            file_size,
            mime_type,
            alt_text,
            user["id"]
        )
        
        return {
            "success": True,
            "media_id": media_id,
            "filename": unique_filename,
            "url": f"/media/{unique_filename}",
            "size": file_size
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/media")
async def list_media(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """List all media files (admin only)"""
    try:
        offset = (page - 1) * per_page
        media = await conn.fetch("""
            SELECT m.*, u.name as uploaded_by_name
            FROM media_files m
            JOIN users u ON m.uploaded_by = u.id
            ORDER BY m.created_at DESC
            LIMIT $1 OFFSET $2
        """, per_page, offset)
        
        count = await conn.fetchrow("SELECT COUNT(*) as total FROM media_files")
        
        return {
            "media": [dict(m) for m in media],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": count['total']
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/media/{filename}")
async def serve_media(filename: str):
    """Serve media file"""
    file_path = MEDIA_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(file_path)

# ==================== ADMIN DASHBOARD ====================

@app.get("/admin/dashboard")
async def admin_dashboard(
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Admin dashboard analytics"""
    try:
        # User statistics
        user_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_users,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') as new_users_7d,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days') as new_users_30d
            FROM users
        """)
        
        # Trade statistics
        trade_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_trades,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') as trades_7d,
                SUM(pips) as total_pips
            FROM trades
        """)
        
        # Blog statistics
        blog_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_posts,
                COUNT(*) FILTER (WHERE status = 'published') as published_posts,
                SUM(view_count) as total_views
            FROM blog_posts
        """)
        
        # Analysis statistics
        analysis_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_analyses,
                AVG(trader_score) as avg_trader_score
            FROM trade_analysis_uploads
        """)
        
        # Recent activity
        recent_users = await conn.fetch("""
            SELECT id, name, email, created_at FROM users
            ORDER BY created_at DESC LIMIT 5
        """)
        
        recent_trades = await conn.fetch("""
            SELECT t.*, u.name as user_name 
            FROM trades t
            JOIN users u ON t.user_id = u.id
            ORDER BY t.created_at DESC LIMIT 5
        """)
        
        return {
            "users": dict(user_stats),
            "trades": dict(trade_stats),
            "blog": dict(blog_stats),
            "analyses": dict(analysis_stats),
            "recent_activity": {
                "users": [dict(u) for u in recent_users],
                "trades": [dict(t) for t in recent_trades]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/users")
async def admin_list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """List all users (admin only)"""
    try:
        offset = (page - 1) * per_page
        
        where_clause = ""
        params = []
        if search:
            where_clause = "WHERE name ILIKE $1 OR email ILIKE $1"
            params.append(f"%{search}%")
        
        users = await conn.fetch(f"""
            SELECT id, name, email, is_admin, created_at,
                   (SELECT COUNT(*) FROM trades WHERE user_id = users.id) as trade_count,
                   (SELECT COUNT(*) FROM trade_analysis_uploads WHERE user_id = users.id) as analysis_count
            FROM users
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${len(params)+1} OFFSET ${len(params)+2}
        """, *params, per_page, offset)
        
        count = await conn.fetchrow(f"SELECT COUNT(*) as total FROM users {where_clause}", *params)
        
        return {
            "users": [dict(u) for u in users],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": count['total']
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/admin/users/{user_id}")
async def admin_update_user(
    user_id: int,
    is_admin: Optional[bool] = Form(None),
    is_active: Optional[bool] = Form(None),  # Would need to add is_active column
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Update user (admin only)"""
    try:
        updates = []
        params = []
        
        if is_admin is not None:
            updates.append("is_admin = $" + str(len(params)+1))
            params.append(is_admin)
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        params.append(user_id)
        
        await conn.execute(f"""
            UPDATE users SET {', '.join(updates)} WHERE id = ${len(params)}
        """, *params)
        
        return {"success": True, "message": "User updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== SEO ENDPOINTS ====================

@app.get("/blog/categories")
async def get_blog_categories(conn=Depends(get_db)):
    """Get all blog categories"""
    try:
        categories = await conn.fetch("SELECT * FROM blog_categories ORDER BY name")
        return [dict(c) for c in categories]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/blog/tags")
async def get_blog_tags(conn=Depends(get_db)):
    """Get all unique tags"""
    try:
        result = await conn.fetch("SELECT DISTINCT unnest(tags) as tag FROM blog_posts WHERE status = 'published'")
        return [r['tag'] for r in result if r['tag']]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sitemap.xml", response_class=HTMLResponse)
async def generate_sitemap(conn=Depends(get_db)):
    """Generate XML sitemap for SEO"""
    try:
        base_url = "https://pipways.com"  # Update with your domain
        
        # Get all published posts
        posts = await conn.fetch("""
            SELECT slug, updated_at FROM blog_posts WHERE status = 'published'
        """)
        
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        
        # Static pages
        static_pages = ['', 'blog', 'login', 'register']
        for page in static_pages:
            xml += f'  <url>\n'
            xml += f'    <loc>{base_url}/{page}</loc>\n'
            xml += f'    <changefreq>weekly</changefreq>\n'
            xml += f'    <priority>0.8</priority>\n'
            xml += f'  </url>\n'
        
        # Blog posts
        for post in posts:
            xml += f'  <url>\n'
            xml += f'    <loc>{base_url}/blog/{post["slug"]}</loc>\n'
            xml += f'    <lastmod>{post["updated_at"].strftime("%Y-%m-%d")}</lastmod>\n'
            xml += f'    <changefreq>monthly</changefreq>\n'
            xml += f'    <priority>0.6</priority>\n'
            xml += f'  </url>\n'
        
        xml += '</urlset>'
        
        return HTMLResponse(content=xml, media_type="application/xml")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/robots.txt", response_class=HTMLResponse)
async def robots_txt():
    """Serve robots.txt"""
    content = """User-agent: *
Allow: /
Allow: /blog/
Disallow: /admin/
Disallow: /api/

Sitemap: https://pipways.com/sitemap.xml
"""
    return HTMLResponse(content=content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
