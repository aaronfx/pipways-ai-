# main.py
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, Form, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
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
        ("ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS canonical_url VARCHAR(255)",
