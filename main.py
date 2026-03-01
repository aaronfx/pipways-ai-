from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from datetime import datetime, timedelta, date
import asyncpg
import os
import base64
import requests
import bcrypt
import json
import re
from typing import Optional, List
from pydantic import BaseModel

app = FastAPI(title="Pipways API")

# CORS - Update with your custom domain when ready
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pipways-web-nhem.onrender.com",
        "https://www.pipways.com",  # Your custom domain
        "https://pipways.com",
        "http://localhost:8000",
    ],
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

async def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    email = await get_current_user(credentials)
    if email != DEFAULT_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required")
    return email

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
        "max_tokens": 2000
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
    
    # Trades table - with checklist columns
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            pair VARCHAR(10) NOT NULL,
            direction VARCHAR(10) NOT NULL,
            entry_price DECIMAL(10,5),
            exit_price DECIMAL(10,5),
            pips DECIMAL(10,2),
            grade VARCHAR(5),
            screenshot_url TEXT,
            ai_analysis TEXT,
            checklist_completed BOOLEAN DEFAULT FALSE,
            checklist_data JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Check if checklist columns exist, add if not
    try:
        await conn.execute("""
            ALTER TABLE trades 
            ADD COLUMN IF NOT EXISTS checklist_completed BOOLEAN DEFAULT FALSE
        """)
        await conn.execute("""
            ALTER TABLE trades 
            ADD COLUMN IF NOT EXISTS checklist_data JSONB
        """)
    except Exception as e:
        print(f"Note: checklist columns may already exist: {e}")
    
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
    
    # Performance analyses table - NEW
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS performance_analyses (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            file_name VARCHAR(255),
            file_data TEXT,
            analysis_result JSONB,
            trader_type VARCHAR(50),
            performance_score INTEGER,
            risk_appetite VARCHAR(20),
            recommendations TEXT[],
            courses_recommended JSONB,
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
            category VARCHAR(50),
            tags TEXT[],
            featured_image TEXT,
            published BOOLEAN DEFAULT FALSE,
            author_email VARCHAR(255),
            view_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Checklist templates table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS checklist_templates (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            items JSONB NOT NULL,
            is_default BOOLEAN DEFAULT FALSE,
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
    
    # Create default checklist template if not exists
    try:
        existing_checklist = await conn.fetchrow("SELECT id FROM checklist_templates WHERE is_default = TRUE")
        if not existing_checklist:
            default_items = [
                {"id": 1, "text": "I have a clear entry strategy based on my trading plan", "required": True},
                {"id": 2, "text": "I have identified and set a definitive stop loss level", "required": True},
                {"id": 3, "text": "I have a realistic take profit target (minimum 1:1.5 R:R)", "required": True},
                {"id": 4, "text": "I have calculated position size (risking only 1-2% of account)", "required": True},
                {"id": 5, "text": "I am not trading out of FOMO, revenge, or emotion", "required": True},
                {"id": 6, "text": "I have checked the economic calendar for high-impact news", "required": False},
                {"id": 7, "text": "This setup meets my minimum A or B grade criteria", "required": True},
                {"id": 8, "text": "I have analyzed the higher timeframe trend direction", "required": False}
            ]
            await conn.execute(
                "INSERT INTO checklist_templates (name, items, is_default) VALUES ($1, $2, $3)",
                "Standard Pre-Trade Checklist", json.dumps(default_items), True
            )
            print("Default checklist template created")
    except Exception as e:
        print(f"Error creating checklist template: {e}")
    
    await conn.close()

# Routes
@app.get("/health")
async def health():
    return {
        "status": "ok", 
        "version": "1.1.0",
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
        return {"access_token": token, "user_id": user["id"], "name": user["name"], "email": email, "is_admin": email == DEFAULT_ADMIN_EMAIL}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

# Checklist Routes
@app.get("/checklist/template")
async def get_checklist_template(conn=Depends(get_db)):
    """Get the default pre-trade checklist template"""
    try:
        template = await conn.fetchrow(
            "SELECT * FROM checklist_templates WHERE is_default = TRUE LIMIT 1"
        )
        if not template:
            # Return hardcoded default if none in DB
            return {
                "id": 0,
                "name": "Standard Pre-Trade Checklist",
                "items": [
                    {"id": 1, "text": "I have a clear entry strategy based on my trading plan", "required": True},
                    {"id": 2, "text": "I have identified and set a definitive stop loss level", "required": True},
                    {"id": 3, "text": "I have a realistic take profit target (minimum 1:1.5 R:R)", "required": True},
                    {"id": 4, "text": "I have calculated position size (risking only 1-2% of account)", "required": True},
                    {"id": 5, "text": "I am not trading out of FOMO, revenge, or emotion", "required": True},
                    {"id": 6, "text": "I have checked the economic calendar for high-impact news", "required": False},
                    {"id": 7, "text": "This setup meets my minimum A or B grade criteria", "required": True},
                    {"id": 8, "text": "I have analyzed the higher timeframe trend direction", "required": False}
                ]
            }
        
        # Parse items if stored as JSON string
        items = template["items"]
        if isinstance(items, str):
            items = json.loads(items)
        
        return {
            "id": template["id"],
            "name": template["name"],
            "items": items,
            "is_default": template["is_default"]
        }
    except Exception as e:
        # Return hardcoded fallback on error
        return {
            "id": 0,
            "name": "Standard Pre-Trade Checklist",
            "items": [
                {"id": 1, "text": "I have a clear entry strategy based on my trading plan", "required": True},
                {"id": 2, "text": "I have identified and set a definitive stop loss level", "required": True},
                {"id": 3, "text": "I have a realistic take profit target (minimum 1:1.5 R:R)", "required": True},
                {"id": 4, "text": "I have calculated position size (risking only 1-2% of account)", "required": True},
                {"id": 5, "text": "I am not trading out of FOMO, revenge, or emotion", "required": True},
                {"id": 6, "text": "I have checked the economic calendar for high-impact news", "required": False},
                {"id": 7, "text": "This setup meets my minimum A or B grade criteria", "required": True},
                {"id": 8, "text": "I have analyzed the higher timeframe trend direction", "required": False}
            ]
        }

# Analytics Routes
@app.get("/analytics/dashboard")
async def get_analytics(current_user: str = Depends(get_current_user), conn=Depends(get_db)):
    """Get comprehensive trading analytics"""
    try:
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        user_id = user["id"]
        
        # Get all trades
        trades = await conn.fetch(
            "SELECT * FROM trades WHERE user_id = $1 ORDER BY created_at ASC",
            user_id
        )
        
        if not trades:
            return {
                "total_trades": 0,
                "win_rate": 0,
                "total_pips": 0,
                "avg_pips_per_trade": 0,
                "profit_factor": 0,
                "winning_streak": 0,
                "losing_streak": 0,
                "current_streak": 0,
                "best_trade": None,
                "worst_trade": None,
                "avg_risk_reward": 0,
                "grade_distribution": {"A": 0, "B": 0, "C": 0},
                "pair_performance": [],
                "monthly_performance": [],
                "equity_curve": [],
                "checklist_adherence": 0
            }
        
        # Basic metrics
        total_trades = len(trades)
        winning_trades = [t for t in trades if t["pips"] and t["pips"] > 0]
        losing_trades = [t for t in trades if t["pips"] and t["pips"] < 0]
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
        total_pips = sum(t["pips"] or 0 for t in trades)
        avg_pips = total_pips / total_trades if total_trades > 0 else 0
        
        # Profit factor
        total_wins = sum(t["pips"] for t in winning_trades if t["pips"])
        total_losses = abs(sum(t["pips"] for t in losing_trades if t["pips"]))
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Streak calculation
        current_streak = 0
        streak_type = None
        winning_streak = 0
        losing_streak = 0
        temp_win_streak = 0
        temp_loss_streak = 0
        
        for trade in trades:
            if trade["pips"] and trade["pips"] > 0:
                if streak_type == "loss":
                    temp_loss_streak = 0
                streak_type = "win"
                temp_win_streak += 1
                winning_streak = max(winning_streak, temp_win_streak)
                temp_loss_streak = 0
            elif trade["pips"] and trade["pips"] < 0:
                if streak_type == "win":
                    temp_win_streak = 0
                streak_type = "loss"
                temp_loss_streak += 1
                losing_streak = max(losing_streak, temp_loss_streak)
                temp_win_streak = 0
        
        current_streak = temp_win_streak if streak_type == "win" else -temp_loss_streak
        
        # Best/worst trades
        sorted_by_pips = sorted(trades, key=lambda x: x["pips"] or 0, reverse=True)
        best_trade = dict(sorted_by_pips[0]) if sorted_by_pips else None
        worst_trade = dict(sorted_by_pips[-1]) if sorted_by_pips else None
        
        # Grade distribution
        grade_dist = {"A": 0, "B": 0, "C": 0}
        for t in trades:
            if t["grade"] in grade_dist:
                grade_dist[t["grade"]] += 1
        
        # Pair performance
        pair_stats = {}
        for t in trades:
            pair = t["pair"]
            if pair not in pair_stats:
                pair_stats[pair] = {"trades": 0, "wins": 0, "pips": 0}
            pair_stats[pair]["trades"] += 1
            if t["pips"] and t["pips"] > 0:
                pair_stats[pair]["wins"] += 1
            pair_stats[pair]["pips"] += t["pips"] or 0
        
        pair_performance = [
            {
                "pair": pair,
                "trades": stats["trades"],
                "win_rate": round(stats["wins"] / stats["trades"] * 100, 1),
                "total_pips": round(stats["pips"], 2)
            }
            for pair, stats in pair_stats.items()
        ]
        pair_performance.sort(key=lambda x: x["total_pips"], reverse=True)
        
        # Monthly performance
        monthly_stats = {}
        for t in trades:
            month_key = t["created_at"].strftime("%Y-%m")
            if month_key not in monthly_stats:
                monthly_stats[month_key] = {"trades": 0, "wins": 0, "pips": 0}
            monthly_stats[month_key]["trades"] += 1
            if t["pips"] and t["pips"] > 0:
                monthly_stats[month_key]["wins"] += 1
            monthly_stats[month_key]["pips"] += t["pips"] or 0
        
        monthly_performance = [
            {
                "month": month,
                "trades": stats["trades"],
                "win_rate": round(stats["wins"] / stats["trades"] * 100, 1) if stats["trades"] > 0 else 0,
                "pips": round(stats["pips"], 2)
            }
            for month, stats in sorted(monthly_stats.items())
        ]
        
        # Equity curve (cumulative pips)
        equity_curve = []
        running_total = 0
        for t in trades:
            running_total += t["pips"] or 0
            equity_curve.append({
                "date": t["created_at"].isoformat(),
                "cumulative_pips": round(running_total, 2),
                "trade_pips": round(t["pips"] or 0, 2)
            })
        
        # Checklist adherence - handle case where column might not exist
        try:
            checklist_completed = sum(1 for t in trades if t.get("checklist_completed"))
            checklist_adherence = (checklist_completed / total_trades * 100) if total_trades > 0 else 0
        except:
            checklist_adherence = 0
        
        return {
            "total_trades": total_trades,
            "win_rate": round(win_rate, 1),
            "total_pips": round(total_pips, 2),
            "avg_pips_per_trade": round(avg_pips, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else "∞",
            "winning_streak": winning_streak,
            "losing_streak": losing_streak,
            "current_streak": current_streak,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "avg_risk_reward": 0,
            "grade_distribution": grade_dist,
            "pair_performance": pair_performance,
            "monthly_performance": monthly_performance,
            "equity_curve": equity_curve,
            "checklist_adherence": round(checklist_adherence, 1)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics error: {str(e)}")

# NEW: Performance Analysis Routes
@app.post("/performance/analyze")
async def analyze_performance(
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
    conn=Depends(get_db)
):
    """Upload trading history for AI performance analysis"""
    try:
        contents = await file.read()
        
        # Handle both images and text files
        file_ext = file.filename.split('.')[-1].lower()
        is_image = file_ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']
        
        if is_image:
            base64_data = base64.b64encode(contents).decode('utf-8')
            file_content = f"[IMAGE_DATA:{base64_data}]"
        else:
            # Text/CSV file
            try:
                file_content = contents.decode('utf-8')
            except:
                file_content = base64.b64encode(contents).decode('utf-8')
        
        # Get user's trade history for context
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        user_id = user["id"]
        
        trades = await conn.fetch(
            "SELECT * FROM trades WHERE user_id = $1 ORDER BY created_at DESC LIMIT 50",
            user_id
        )
        
        trade_summary = {
            "total_trades": len(trades),
            "win_rate": 0,
            "avg_pips": 0,
            "favorite_pairs": []
        }
        
        if trades:
            wins = [t for t in trades if t["pips"] and t["pips"] > 0]
            trade_summary["win_rate"] = round(len(wins) / len(trades) * 100, 1)
            trade_summary["avg_pips"] = round(sum(t["pips"] or 0 for t in trades) / len(trades), 2)
            
            pairs = {}
            for t in trades:
                pairs[t["pair"]] = pairs.get(t["pair"], 0) + 1
            trade_summary["favorite_pairs"] = sorted(pairs.items(), key=lambda x: x[1], reverse=True)[:3]
        
        # AI Analysis Prompt
        messages = [
            {
                "role": "system",
                "content": """You are an expert trading performance analyst. Analyze the trader's history and provide a comprehensive assessment. Respond in this exact JSON format:
{
    "trader_type": "Scalper/Day Trader/Swing Trader/Position Trader/Mixed",
    "performance_score": 75,
    "score_breakdown": {
        "profitability": 80,
        "risk_management": 70,
        "consistency": 75,
        "psychology": 65
    },
    "risk_appetite": "Conservative/Moderate/Aggressive/Very Aggressive",
    "strengths": ["Good risk management", "Consistent entries"],
    "weaknesses": ["Overtrading", "Poor exit timing"],
    "key_insights": "You tend to perform better in trending markets...",
    "improvement_plan": [
        "Set maximum daily loss limits",
        "Wait for confirmation before entering"
    ],
    "recommended_courses": [
        {"title": "Advanced Risk Management", "level": "Intermediate", "priority": "High"},
        {"title": "Trading Psychology Mastery", "level": "Beginner", "priority": "Medium"}
    ],
    "monthly_goal": "Improve win rate by 5% while maintaining current R:R ratio"
}"""
            },
            {
                "role": "user",
                "content": f"""Analyze this trader's performance:

Trading History Summary:
- Total Trades: {trade_summary['total_trades']}
- Win Rate: {trade_summary['win_rate']}%
- Average Pips per Trade: {trade_summary['avg_pips']}
- Most Traded Pairs: {', '.join([p[0] for p in trade_summary['favorite_pairs']])}

Uploaded File Content ({file.filename}):
{file_content[:5000] if not is_image else '[Trading history screenshot provided]'}"""
            }
        ]
        
        analysis_text, error = openrouter_chat(messages)
        
        if error:
            return {
                "success": False,
                "error": error,
                "fallback_analysis": generate_fallback_analysis(trade_summary)
            }
        
        # Parse AI response
        try:
            json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            if json_match:
                analysis_result = json.loads(json_match.group())
            else:
                analysis_result = generate_fallback_analysis(trade_summary)
        except:
            analysis_result = generate_fallback_analysis(trade_summary)
        
        # Store in database
        await conn.execute("""
            INSERT INTO performance_analyses 
            (user_id, file_name, file_data, analysis_result, trader_type, performance_score, risk_appetite, recommendations, courses_recommended)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """, 
            user_id,
            file.filename,
            file_content[:1000] if not is_image else None,
            json.dumps(analysis_result),
            analysis_result.get("trader_type", "Unknown"),
            analysis_result.get("performance_score", 0),
            analysis_result.get("risk_appetite", "Unknown"),
            analysis_result.get("improvement_plan", []),
            json.dumps(analysis_result.get("recommended_courses", []))
        )
        
        return {
            "success": True,
            "analysis": analysis_result,
            "trade_summary": trade_summary
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "fallback_analysis": generate_fallback_analysis({"total_trades": 0})
        }

def generate_fallback_analysis(trade_summary):
    """Generate fallback analysis when AI fails"""
    return {
        "trader_type": "Analyzing...",
        "performance_score": 50,
        "score_breakdown": {
            "profitability": 50,
            "risk_management": 50,
            "consistency": 50,
            "psychology": 50
        },
        "risk_appetite": "Moderate",
        "strengths": ["Keep logging trades to get personalized insights"],
        "weaknesses": ["Not enough data for full analysis"],
        "key_insights": f"You have {trade_summary['total_trades']} trades logged. Continue journaling for detailed AI analysis.",
        "improvement_plan": [
            "Log all trades consistently",
            "Complete pre-trade checklist",
            "Review weekly performance"
        ],
        "recommended_courses": [
            {"title": "Trading Fundamentals", "level": "Beginner", "priority": "High"},
            {"title": "Risk Management Basics", "level": "Beginner", "priority": "High"}
        ],
        "monthly_goal": "Log 20+ trades with complete checklist"
    }

@app.get("/performance/history")
async def get_performance_history(current_user: str = Depends(get_current_user), conn=Depends(get_db)):
    """Get user's performance analysis history"""
    try:
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        analyses = await conn.fetch(
            """SELECT id, file_name, analysis_result, trader_type, performance_score, 
                      risk_appetite, created_at 
               FROM performance_analyses 
               WHERE user_id = $1 
               ORDER BY created_at DESC""",
            user["id"]
        )
        return [dict(a) for a in analyses]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    checklist_completed: bool = Form(False),
    checklist_data: Optional[str] = Form(None),
    current_user: str = Depends(get_current_user),
    conn=Depends(get_db)
):
    try:
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        
        checklist_json = None
        if checklist_data:
            try:
                checklist_json = json.loads(checklist_data)
            except:
                pass
        
        trade_id = await conn.fetchval("""
            INSERT INTO trades (user_id, pair, direction, entry_price, exit_price, pips, grade, checklist_completed, checklist_data)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id
        """, user["id"], pair.upper(), direction, entry_price, exit_price, pips, grade, checklist_completed, checklist_json)
        
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

# Blog Routes (Public)
@app.get("/blog/posts")
async def get_blog_posts(category: Optional[str] = None, limit: int = 10, offset: int = 0, conn=Depends(get_db)):
    """Get published blog posts"""
    try:
        if category:
            posts = await conn.fetch(
                """SELECT id, title, slug, excerpt, category, tags, featured_image, author_email, view_count, created_at 
                   FROM blog_posts WHERE published = TRUE AND category = $1 
                   ORDER BY created_at DESC LIMIT $2 OFFSET $3""",
                category, limit, offset
            )
        else:
            posts = await conn.fetch(
                """SELECT id, title, slug, excerpt, category, tags, featured_image, author_email, view_count, created_at 
                   FROM blog_posts WHERE published = TRUE 
                   ORDER BY created_at DESC LIMIT $1 OFFSET $2""",
                limit, offset
            )
        return [dict(p) for p in posts]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/blog/posts/{slug}")
async def get_blog_post(slug: str, conn=Depends(get_db)):
    """Get single blog post by slug"""
    try:
        post = await conn.fetchrow(
            "SELECT * FROM blog_posts WHERE slug = $1 AND published = TRUE",
            slug
        )
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Increment view count
        await conn.execute(
            "UPDATE blog_posts SET view_count = view_count + 1 WHERE id = $1",
            post["id"]
        )
        
        return dict(post)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/blog/categories")
async def get_blog_categories(conn=Depends(get_db)):
    """Get all blog categories"""
    try:
        categories = await conn.fetch(
            "SELECT DISTINCT category FROM blog_posts WHERE published = TRUE"
        )
        return [c["category"] for c in categories if c["category"]]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Admin Blog Routes (Protected)
@app.get("/admin/blog/posts")
async def get_admin_blog_posts(current_user: str = Depends(get_current_admin), conn=Depends(get_db)):
    """Get all blog posts for admin (including unpublished)"""
    try:
        posts = await conn.fetch(
            "SELECT * FROM blog_posts ORDER BY created_at DESC"
        )
        return [dict(p) for p in posts]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/blog/posts")
async def create_blog_post(
    title: str = Form(...),
    slug: str = Form(...),
    content: str = Form(...),
    excerpt: Optional[str] = Form(None),
    category: Optional[str] = Form("General"),
    tags: Optional[str] = Form(None),
    featured_image: Optional[str] = Form(None),
    published: bool = Form(False),
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Create new blog post (admin only)"""
    try:
        # Generate excerpt if not provided
        if not excerpt:
            excerpt = content[:200] + "..." if len(content) > 200 else content
        
        # Parse tags
        tag_list = [t.strip() for t in tags.split(",")] if tags else []
        
        post_id = await conn.fetchval("""
            INSERT INTO blog_posts (title, slug, content, excerpt, category, tags, featured_image, published, author_email)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id
        """, title, slug, content, excerpt, category, tag_list, featured_image, published, current_user)
        
        return {"id": post_id, "message": "Blog post created", "slug": slug}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/admin/blog/posts/{post_id}")
async def update_blog_post(
    post_id: int,
    title: Optional[str] = Form(None),
    slug: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    featured_image: Optional[str] = Form(None),
    published: Optional[bool] = Form(None),
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Update blog post (admin only)"""
    try:
        # Build dynamic update query
        updates = []
        values = []
        param_count = 0
        
        if title is not None:
            param_count += 1
            updates.append(f"title = ${param_count}")
            values.append(title)
        if slug is not None:
            param_count += 1
            updates.append(f"slug = ${param_count}")
            values.append(slug)
        if content is not None:
            param_count += 1
            updates.append(f"content = ${param_count}")
            values.append(content)
            # Auto-update excerpt if content changes
            if excerpt is None:
                new_excerpt = content[:200] + "..." if len(content) > 200 else content
                param_count += 1
                updates.append(f"excerpt = ${param_count}")
                values.append(new_excerpt)
        if excerpt is not None:
            param_count += 1
            updates.append(f"excerpt = ${param_count}")
            values.append(excerpt)
        if category is not None:
            param_count += 1
            updates.append(f"category = ${param_count}")
            values.append(category)
        if tags is not None:
            param_count += 1
            updates.append(f"tags = ${param_count}")
            values.append([t.strip() for t in tags.split(",")])
        if featured_image is not None:
            param_count += 1
            updates.append(f"featured_image = ${param_count}")
            values.append(featured_image)
        if published is not None:
            param_count += 1
            updates.append(f"published = ${param_count}")
            values.append(published)
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        param_count += 1
        updates.append(f"updated_at = ${param_count}")
        values.append(datetime.utcnow())
        
        values.append(post_id)
        
        query = f"UPDATE blog_posts SET {', '.join(updates)} WHERE id = ${len(values)}"
        await conn.execute(query, *values)
        
        return {"message": "Blog post updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/admin/blog/posts/{post_id}")
async def delete_blog_post(post_id: int, current_user: str = Depends(get_current_admin), conn=Depends(get_db)):
    """Delete blog post (admin only)"""
    try:
        result = await conn.execute("DELETE FROM blog_posts WHERE id = $1", post_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Post not found")
        return {"message": "Blog post deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/stats")
async def get_admin_stats(current_user: str = Depends(get_current_admin), conn=Depends(get_db)):
    """Get admin dashboard statistics"""
    try:
        # User stats
        user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        trade_count = await conn.fetchval("SELECT COUNT(*) FROM trades")
        analysis_count = await conn.fetchval("SELECT COUNT(*) FROM chart_analyses")
        
        # Blog stats
        blog_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_posts,
                COUNT(*) FILTER (WHERE published = TRUE) as published_posts,
                SUM(view_count) as total_views
            FROM blog_posts
        """)
        
        # Recent activity
        recent_trades = await conn.fetch("""
            SELECT t.*, u.name, u.email 
            FROM trades t 
            JOIN users u ON t.user_id = u.id 
            ORDER BY t.created_at DESC LIMIT 5
        """)
        
        return {
            "users": user_count,
            "trades": trade_count,
            "chart_analyses": analysis_count,
            "blog_posts": {
                "total": blog_stats["total_posts"],
                "published": blog_stats["published_posts"],
                "drafts": blog_stats["total_posts"] - blog_stats["published_posts"],
                "total_views": blog_stats["total_views"] or 0
            },
            "recent_trades": [dict(t) for t in recent_trades]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
