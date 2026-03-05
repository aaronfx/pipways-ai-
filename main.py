# main.py
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, Form, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.routing import APIRouter
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
from typing import Optional, List, Dict, Any
from pathlib import Path
import shutil

# Import dependencies FIRST (before blog_routes to avoid circular import)
from dependencies import get_db, get_current_user, get_current_admin, SECRET_KEY, ALGORITHM

# Import new routers and tools - ONLY for blog system
from blog_routes import blog_router
from media_routes import media_router
import ai_blog_tools  # AI tools for blog

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

Provide your analysis in this exact JSON format: {{
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

Provide response in this JSON format: {{
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

# Startup with auto-migration
@app.on_event("startup")
async def startup():
    conn = await asyncpg.connect(DATABASE_URL, ssl="require")
    
    # ========== AUTO-MIGRATION ==========
    migrations = [
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE", "is_admin column"),
        # New migrations ONLY for blog upgrades
        ("ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS content_json JSONB", "content_json column"),
        ("ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS seo_score INTEGER", "seo_score column"),
        ("ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS reading_time INTEGER", "reading_time column"),
        ("ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS ai_generated BOOLEAN DEFAULT FALSE", "ai_generated column"),
        ("ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS focus_keyword VARCHAR(255)", "focus_keyword column"),
        ("ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS canonical_url VARCHAR(255)", "canonical_url column"),
        ("ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS og_image TEXT", "og_image column"),
        ("ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMP", "scheduled_at column"),
    ]
    
    for sql, description in migrations:
        try:
            await conn.execute(sql)
            print(f"✅ Migration applied: {description}")
        except Exception as e:
            print(f"⚠️ Migration skipped ({description}): {e}")
    # ========== END MIGRATION ==========
    
    # Users table (create if not exists)
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
            content_json JSONB,
            excerpt TEXT,
            featured_image TEXT,
            meta_title VARCHAR(70),
            meta_description VARCHAR(160),
            meta_keywords TEXT,
            focus_keyword VARCHAR(255),
            canonical_url VARCHAR(255),
            og_image TEXT,
            author_id INTEGER REFERENCES users(id),
            category VARCHAR(100),
            tags TEXT[],
            status VARCHAR(20) DEFAULT 'draft',
            published_at TIMESTAMP,
            scheduled_at TIMESTAMP,
            view_count INTEGER DEFAULT 0,
            reading_time INTEGER,
            seo_score INTEGER,
            ai_generated BOOLEAN DEFAULT FALSE,
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
    
    # Create default admin user and ensure is_admin = TRUE
    try:
        existing_admin = await conn.fetchrow("SELECT id, is_admin FROM users WHERE email = $1", DEFAULT_ADMIN_EMAIL)
        if not existing_admin:
            hashed = get_password_hash(DEFAULT_ADMIN_PASSWORD)
            await conn.execute(
                "INSERT INTO users (email, password_hash, name, is_admin) VALUES ($1, $2, $3, $4)",
                DEFAULT_ADMIN_EMAIL, hashed, "Admin", True
            )
            print(f"✅ Default admin created: {DEFAULT_ADMIN_EMAIL} / {DEFAULT_ADMIN_PASSWORD}")
        else:
            # Ensure existing admin has is_admin = TRUE
            await conn.execute(
                "UPDATE users SET is_admin = TRUE WHERE email = $1",
                DEFAULT_ADMIN_EMAIL
            )
            print(f"✅ Admin privileges confirmed for: {DEFAULT_ADMIN_EMAIL}")
    except Exception as e:
        print(f"⚠️ Admin setup error: {e}")
    
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
            }
        
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                analysis = {"raw": analysis_text}
        except Exception as e:
            analysis = {"raw": analysis_text, "parse_error": str(e)}
        
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        
        analysis_id = await conn.fetchval("""
            INSERT INTO chart_analyses (user_id, image_data, analysis_result)
            VALUES ($1, $2, $3) RETURNING id
        """, user["id"], base64_image, json.dumps(analysis))
        
        return {
            "success": True,
            "analysis_id": analysis_id,
            "analysis": analysis,
            "message": "Chart analyzed and saved"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chart analysis failed: {str(e)}")

@app.get("/chart-analyses")
async def get_chart_analyses(
    current_user: str = Depends(get_current_user),
    conn=Depends(get_db)
):
    try:
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        analyses = await conn.fetch(
            "SELECT id, created_at, analysis_result FROM chart_analyses WHERE user_id = $1 ORDER BY created_at DESC",
            user["id"]
        )
        return [dict(a) for a in analyses]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch analyses: {str(e)}")

# ==================== TRADE ANALYSIS ====================

@app.post("/analyze-trades")
async def analyze_trades(
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
    conn=Depends(get_db)
):
    try:
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large")
        
        file_type = file.content_type
        ext = Path(file.filename).suffix.lower()
        if file_type not in ALLOWED_TRADE_FILE_TYPES and ext not in ALLOWED_TRADE_FILE_TYPES.values():
            raise HTTPException(status_code=400, detail="Unsupported file type")
        
        # Normalize file_type based on extension if needed
        type_map = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.csv': 'text/csv',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp'
        }
        file_type = type_map.get(ext, file_type)
        
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
async def get_personalized_mentorship_endpoint(
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
    return await get_personalized_mentorship_endpoint(message, "general", current_user, conn)

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
            "users": dict(user_stats) if user_stats else {},
            "trades": dict(trade_stats) if trade_stats else {},
            "blog": dict(blog_stats) if blog_stats else {},
            "analyses": dict(analysis_stats) if analysis_stats else {},
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
                "total": count['total'] if count else 0
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/admin/users/{user_id}")
async def admin_update_user(
    user_id: int,
    is_admin: Optional[bool] = Form(None),
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

# ==================== BLOG ADMIN INTERFACE ====================

@app.get("/admin/blog", response_class=HTMLResponse)
async def blog_admin_interface():
    """Serve the blog admin interface with Editor.js"""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Blog Admin - Pipways</title>
    <script src="https://cdn.tailwindcss.com"></script>
    
    <!-- Editor.js -->
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/editorjs@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/header@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/list@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/paragraph@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/image@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/quote@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/code@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/table@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/embed@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/delimiter@latest"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    
    <style>
        body { background: #0f172a; color: #e2e8f0; }
        .ce-block__content, .ce-toolbar__content { max-width: 100%; }
        .codex-editor { background: #1e293b; border-radius: 0.5rem; }
        .ce-toolbar__actions { right: 10px; }
        .ce-block--selected .ce-block__content { background: #334155; }
        .ce-inline-toolbar { background: #1e293b; border-color: #334155; }
        .ce-conversion-tool__icon, .ce-popover__item-icon { background: #334155; }
        .ce-popover, .ce-settings { background: #1e293b; border-color: #334155; }
        .cdx-search-field { border-color: #334155; }
        .ce-popover__item:hover, .ce-conversion-tool:hover { background: #334155; }
        .cdx-button { background: #334155; border-color: #475569; color: #e2e8f0; }
        .cdx-button:hover { background: #475569; }
        .ce-header { color: #f8fafc; }
        .codex-editor__redactor { padding-bottom: 100px !important; }
    </style>
</head>
<body class="min-h-screen">
    <div class="max-w-7xl mx-auto p-6">
        <!-- Header -->
        <div class="flex justify-between items-center mb-8 pb-6 border-b border-slate-800">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center">
                    <i data-lucide="file-text" class="w-5 h-5 text-white"></i>
                </div>
                <h1 class="text-2xl font-bold text-white">Blog Admin</h1>
            </div>
            <div class="flex gap-3">
                <button onclick="loadPosts()" class="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium transition-all flex items-center gap-2">
                    <i data-lucide="refresh-cw" class="w-4 h-4"></i> Refresh
                </button>
                <button onclick="openEditor()" class="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-all flex items-center gap-2">
                    <i data-lucide="plus" class="w-4 h-4"></i> New Post
                </button>
            </div>
        </div>

        <!-- Posts Grid -->
        <div id="posts-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <div class="col-span-full text-center text-slate-400 py-12">Loading posts...</div>
        </div>
    </div>

    <!-- Editor Modal -->
    <div id="editor-modal" class="fixed inset-0 bg-black/80 backdrop-blur-sm hidden z-50 overflow-y-auto">
        <div class="min-h-screen px-4 py-8">
            <div class="max-w-6xl mx-auto bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl overflow-hidden">
                <!-- Modal Header -->
                <div class="flex justify-between items-center p-6 border-b border-slate-800 bg-slate-800/50">
                    <h3 class="text-xl font-bold text-white flex items-center gap-2">
                        <i data-lucide="edit-3" class="w-5 h-5 text-blue-400"></i>
                        <span id="modal-title">Create New Post</span>
                    </h3>
                    <button onclick="closeEditor()" class="text-slate-400 hover:text-white transition-colors">
                        <i data-lucide="x" class="w-6 h-6"></i>
                    </button>
                </div>

                <!-- Modal Body -->
                <div class="p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <!-- Main Editor -->
                    <div class="lg:col-span-2 space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-slate-400 mb-2">Title</label>
                            <input type="text" id="post-title" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-white focus:border-blue-500 focus:outline-none text-lg" placeholder="Enter post title...">
                        </div>
                        
                        <div>
                            <label class="block text-sm font-medium text-slate-400 mb-2">Content</label>
                            <div id="editorjs" class="min-h-[500px] bg-slate-800 border border-slate-700 rounded-lg"></div>
                        </div>
                        
                        <div>
                            <label class="block text-sm font-medium text-slate-400 mb-2">Excerpt</label>
                            <textarea id="post-excerpt" rows="3" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-white focus:border-blue-500 focus:outline-none" placeholder="Brief summary for blog listing..."></textarea>
                        </div>
                    </div>

                    <!-- Sidebar -->
                    <div class="space-y-4">
                        <!-- Publish Settings -->
                        <div class="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                            <h4 class="font-medium text-white mb-4 flex items-center gap-2">
                                <i data-lucide="settings" class="w-4 h-4 text-slate-400"></i> Publish Settings
                            </h4>
                            <div class="space-y-3">
                                <div>
                                    <label class="block text-xs font-medium text-slate-400 mb-1">Status</label>
                                    <select id="post-status" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white">
                                        <option value="draft">Draft</option>
                                        <option value="published">Published</option>
                                        <option value="scheduled">Scheduled</option>
                                    </select>
                                </div>
                                <div>
                                    <label class="block text-xs font-medium text-slate-400 mb-1">Category</label>
                                    <select id="post-category" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white">
                                        <option value="">Select Category</option>
                                        <option value="Psychology">Trading Psychology</option>
                                        <option value="Strategy">Trading Strategy</option>
                                        <option value="Risk Management">Risk Management</option>
                                        <option value="Technical Analysis">Technical Analysis</option>
                                        <option value="Beginner Guides">Beginner Guides</option>
                                    </select>
                                </div>
                                <div>
                                    <label class="block text-xs font-medium text-slate-400 mb-1">Tags</label>
                                    <input type="text" id="post-tags" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="forex, trading, psychology">
                                </div>
                                <div>
                                    <label class="block text-xs font-medium text-slate-400 mb-1">Featured Image URL</label>
                                    <input type="text" id="post-image" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="https://...">
                                </div>
                            </div>
                        </div>

                        <!-- SEO -->
                        <div class="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                            <h4 class="font-medium text-white mb-4 flex items-center gap-2">
                                <i data-lucide="search" class="w-4 h-4 text-slate-400"></i> SEO
                            </h4>
                            <div class="space-y-3">
                                <div>
                                    <label class="block text-xs font-medium text-slate-400 mb-1">Meta Title <span class="text-slate-500">(<span id="title-count">0</span>/70)</span></label>
                                    <input type="text" id="post-meta-title" maxlength="70" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="SEO title...">
                                </div>
                                <div>
                                    <label class="block text-xs font-medium text-slate-400 mb-1">Meta Description <span class="text-slate-500">(<span id="desc-count">0</span>/160)</span></label>
                                    <textarea id="post-meta-desc" maxlength="160" rows="2" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="SEO description..."></textarea>
                                </div>
                                <div>
                                    <label class="block text-xs font-medium text-slate-400 mb-1">Focus Keyword</label>
                                    <input type="text" id="post-keyword" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="Primary keyword">
                                </div>
                            </div>
                            <button onclick="analyzeSEO()" class="w-full mt-3 bg-slate-700 hover:bg-slate-600 text-white py-2 rounded-lg text-sm font-medium transition-all">
                                Analyze SEO
                            </button>
                            <div id="seo-result" class="mt-3 hidden">
                                <div class="text-center">
                                    <div id="seo-score" class="text-3xl font-bold">--</div>
                                    <div class="text-xs text-slate-400">SEO Score</div>
                                </div>
                            </div>
                        </div>

                        <!-- AI Assistant -->
                        <div class="bg-gradient-to-br from-violet-900/30 to-blue-900/30 rounded-lg p-4 border border-violet-700/30">
                            <h4 class="font-medium text-white mb-4 flex items-center gap-2">
                                <i data-lucide="sparkles" class="w-4 h-4 text-violet-400"></i> AI Assistant
                            </h4>
                            <div class="space-y-3">
                                <input type="text" id="ai-topic" class="w-full bg-slate-800/50 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="Topic (e.g., Risk Management)">
                                <input type="text" id="ai-keywords" class="w-full bg-slate-800/50 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="Keywords">
                                <select id="ai-audience" class="w-full bg-slate-800/50 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white">
                                    <option value="beginner">Beginner</option>
                                    <option value="intermediate">Intermediate</option>
                                    <option value="advanced">Advanced</option>
                                </select>
                                <button onclick="generateAI()" class="w-full bg-violet-600 hover:bg-violet-500 text-white py-2 rounded-lg text-sm font-medium transition-all">
                                    Generate Content
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Modal Footer -->
                <div class="flex justify-end gap-3 p-6 border-t border-slate-800 bg-slate-800/30">
                    <button onclick="closeEditor()" class="px-6 py-2.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800 transition-all">
                        Cancel
                    </button>
                    <button onclick="savePost('draft')" class="px-6 py-2.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-white font-medium transition-all">
                        Save Draft
                    </button>
                    <button onclick="savePost('published')" class="px-6 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium transition-all shadow-lg shadow-blue-500/25">
                        Publish
                    </button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const API_BASE = window.location.origin;
        let editor = null;
        let currentPostId = null;

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            lucide.createIcons();
            loadPosts();
            
            // Character counters
            document.getElementById('post-meta-title')?.addEventListener('input', (e) => {
                document.getElementById('title-count').textContent = e.target.value.length;
            });
            document.getElementById('post-meta-desc')?.addEventListener('input', (e) => {
                document.getElementById('desc-count').textContent = e.target.value.length;
            });
        });

        function getToken() {
            return localStorage.getItem('token') || prompt('Enter auth token:');
        }

        async function loadPosts() {
            try {
                const response = await fetch(`${API_BASE}/posts?per_page=12`);
                const data = await response.json();
                
                const grid = document.getElementById('posts-grid');
                
                if (data.posts && data.posts.length > 0) {
                    grid.innerHTML = data.posts.map(post => `
                        <div class="bg-slate-800/50 border border-slate-700 rounded-xl overflow-hidden hover:border-blue-500/50 transition-all group cursor-pointer" onclick="editPost(${post.id})">
                            ${post.featured_image ? `<div class="h-48 overflow-hidden"><img src="${post.featured_image}" alt="${post.title}" class="w-full h-full object-cover group-hover:scale-105 transition-transform"></div>` : '<div class="h-48 bg-slate-800 flex items-center justify-center"><i data-lucide="image" class="w-12 h-12 text-slate-600"></i></div>'}
                            <div class="p-4">
                                <div class="flex items-center gap-2 mb-2">
                                    <span class="px-2 py-1 bg-blue-500/20 text-blue-400 text-xs rounded-full">${post.category || 'Uncategorized'}</span>
                                    <span class="text-xs text-slate-500 capitalize">${post.status}</span>
                                </div>
                                <h3 class="font-semibold text-white mb-2 line-clamp-2">${post.title}</h3>
                                <p class="text-sm text-slate-400 line-clamp-2 mb-3">${post.excerpt || ''}</p>
                                <div class="flex items-center justify-between text-xs text-slate-500">
                                    <span class="flex items-center gap-1"><i data-lucide="clock" class="w-3 h-3"></i> ${post.reading_time || 5} min</span>
                                    <span class="flex items-center gap-1"><i data-lucide="eye" class="w-3 h-3"></i> ${post.view_count || 0}</span>
                                </div>
                            </div>
                        </div>
                    `).join('');
                    lucide.createIcons();
                } else {
                    grid.innerHTML = '<div class="col-span-full text-center text-slate-400 py-12">No posts yet. Create your first post!</div>';
                }
            } catch (error) {
                console.error('Error loading posts:', error);
                document.getElementById('posts-grid').innerHTML = '<div class="col-span-full text-center text-red-400 py-12">Error loading posts</div>';
            }
        }

        function openEditor() {
            currentPostId = null;
            document.getElementById('modal-title').textContent = 'Create New Post';
            document.getElementById('editor-modal').classList.remove('hidden');
            document.body.style.overflow = 'hidden';
            
            if (!editor) {
                editor = new EditorJS({
                    holder: 'editorjs',
                    tools: {
                        header: {
                            class: Header,
                            config: { levels: [1, 2, 3, 4, 5, 6], defaultLevel: 2 }
                        },
                        list: { class: List, inlineToolbar: true },
                        paragraph: { class: Paragraph, inlineToolbar: true },
                        image: {
                            class: ImageTool,
                            config: {
                                endpoints: {
                                    byFile: `${API_BASE}/upload`,
                                    byUrl: `${API_BASE}/upload-url`
                                }
                            }
                        },
                        quote: { class: Quote, inlineToolbar: true },
                        code: { class: CodeTool },
                        table: { class: Table, inlineToolbar: true },
                        embed: {
                            class: Embed,
                            config: { services: { youtube: true, twitter: true } }
                        },
                        delimiter: Delimiter
                    },
                    placeholder: 'Start writing your post... Click + to add headings, lists, images, and more',
                    autofocus: true
                });
            }
        }

        async function editPost(postId) {
            try {
                const response = await fetch(`${API_BASE}/admin/posts/${postId}`, {
                    headers: { 'Authorization': `Bearer ${getToken()}` }
                });
                const post = await response.json();
                
                currentPostId = post.id;
                document.getElementById('modal-title').textContent = 'Edit Post';
                document.getElementById('post-title').value = post.title || '';
                document.getElementById('post-excerpt').value = post.excerpt || '';
                document.getElementById('post-meta-title').value = post.meta_title || '';
                document.getElementById('post-meta-desc').value = post.meta_description || '';
                document.getElementById('post-keyword').value = post.focus_keyword || '';
                document.getElementById('post-tags').value = post.tags ? post.tags.join(', ') : '';
                document.getElementById('post-image').value = post.featured_image || '';
                document.getElementById('post-category').value = post.category || '';
                document.getElementById('post-status').value = post.status || 'draft';
                
                // Update counters
                document.getElementById('title-count').textContent = (post.meta_title || '').length;
                document.getElementById('desc-count').textContent = (post.meta_description || '').length;
                
                openEditor();
                
                if (post.content_json) {
                    await editor.render(post.content_json);
                }
            } catch (error) {
                console.error('Error loading post:', error);
                alert('Error loading post');
            }
        }

        function closeEditor() {
            document.getElementById('editor-modal').classList.add('hidden');
            document.body.style.overflow = '';
            
            // Reset form
            document.getElementById('post-title').value = '';
            document.getElementById('post-excerpt').value = '';
            document.getElementById('post-meta-title').value = '';
            document.getElementById('post-meta-desc').value = '';
            document.getElementById('post-keyword').value = '';
            document.getElementById('post-tags').value = '';
            document.getElementById('post-image').value = '';
            document.getElementById('post-category').value = '';
            document.getElementById('post-status').value = 'draft';
            document.getElementById('title-count').textContent = '0';
            document.getElementById('desc-count').textContent = '0';
            document.getElementById('seo-result').classList.add('hidden');
            
            if (editor) editor.clear();
            currentPostId = null;
        }

        async function savePost(status) {
            try {
                const content = await editor.save();
                
                const formData = new FormData();
                formData.append('title', document.getElementById('post-title').value);
                formData.append('content_json', JSON.stringify(content));
                formData.append('excerpt', document.getElementById('post-excerpt').value);
                formData.append('meta_title', document.getElementById('post-meta-title').value);
                formData.append('meta_description', document.getElementById('post-meta-desc').value);
                formData.append('focus_keyword', document.getElementById('post-keyword').value);
                formData.append('tags', document.getElementById('post-tags').value);
                formData.append('featured_image', document.getElementById('post-image').value);
                formData.append('category', document.getElementById('post-category').value);
                formData.append('status', status);
                
                const url = currentPostId 
                    ? `${API_BASE}/admin/posts/${currentPostId}` 
                    : `${API_BASE}/admin/posts`;
                const method = currentPostId ? 'PUT' : 'POST';
                
                const response = await fetch(url, {
                    method: method,
                    body: formData,
                    headers: { 'Authorization': `Bearer ${getToken()}` }
                });
                
                const result = await response.json();
                
                if (result.success) {
                    alert(`Post ${currentPostId ? 'updated' : 'created'} successfully!`);
                    closeEditor();
                    loadPosts();
                } else {
                    alert('Error: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error saving post:', error);
                alert('Error saving post: ' + error.message);
            }
        }

        async function generateAI() {
            const btn = event.target;
            btn.textContent = 'Generating...';
            btn.disabled = true;
            
            try {
                const formData = new FormData();
                formData.append('topic', document.getElementById('ai-topic').value);
                formData.append('keywords', document.getElementById('ai-keywords').value);
                formData.append('audience', document.getElementById('ai-audience').value);
                formData.append('tone', 'professional');
                
                const response = await fetch(`${API_BASE}/admin/ai-generate`, {
                    method: 'POST',
                    body: formData,
                    headers: { 'Authorization': `Bearer ${getToken()}` }
                });
                
                const result = await response.json();
                
                if (result.success) {
                    const content = result.content;
                    document.getElementById('post-title').value = content.title || '';
                    document.getElementById('post-meta-title').value = content.meta_title || '';
                    document.getElementById('post-meta-desc').value = content.meta_description || '';
                    document.getElementById('post-keyword').value = content.focus_keyword || '';
                    document.getElementById('post-excerpt').value = content.excerpt || '';
                    
                    if (content.content_blocks) {
                        await editor.render({ blocks: content.content_blocks });
                    }
                    
                    // Update counters
                    document.getElementById('title-count').textContent = (content.meta_title || '').length;
                    document.getElementById('desc-count').textContent = (content.meta_description || '').length;
                    
                    alert('AI content generated! Review before publishing.');
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Error generating content');
            } finally {
                btn.textContent = 'Generate Content';
                btn.disabled = false;
            }
        }

        async function analyzeSEO() {
            try {
                const content = await editor.save();
                
                const formData = new FormData();
                formData.append('content_json', JSON.stringify(content));
                formData.append('title', document.getElementById('post-title').value);
                formData.append('meta_description', document.getElementById('post-meta-desc').value);
                formData.append('focus_keyword', document.getElementById('post-keyword').value);
                
                const response = await fetch(`${API_BASE}/admin/analyze-seo`, {
                    method: 'POST',
                    body: formData,
                    headers: { 'Authorization': `Bearer ${getToken()}` }
                });
                
                const result = await response.json();
                
                if (result.success) {
                    document.getElementById('seo-result').classList.remove('hidden');
                    const scoreEl = document.getElementById('seo-score');
                    scoreEl.textContent = result.seo_score;
                    scoreEl.className = 'text-3xl font-bold ' + 
                        (result.seo_score >= 80 ? 'text-green-400' : 
                         result.seo_score >= 60 ? 'text-yellow-400' : 'text-red-400');
                }
            } catch (error) {
                console.error('Error analyzing SEO:', error);
            }
        }
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

# ==================== ZOOM WEBINAR MODULE (Separate) ====================
# This keeps webinar functionality completely modular and separate

try:
    from routers.webinars_zoom import router as zoom_webinar_router
    app.include_router(zoom_webinar_router)
    
    # Mount webinar static files separately
    from fastapi.staticfiles import StaticFiles
    app.mount("/webinars", StaticFiles(directory="static/webinars", html=True), name="webinars")
    
    print("✅ Zoom Webinar module loaded successfully")
except Exception as e:
    print(f"⚠️ Zoom Webinar module not loaded: {e}")

# Redirect /webinars to the webinar app
@app.get("/webinars", response_class=HTMLResponse)
async def webinar_app_root():
    return FileResponse("static/webinars/index.html")

# Include upgraded blog and media routers - ONLY addition for blog system
app.include_router(blog_router)
app.include_router(media_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
