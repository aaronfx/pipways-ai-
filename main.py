from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, Form, BackgroundTasks, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from jose import JWTError, jwt
from datetime import datetime, timedelta, date
import asyncpg
import os
import base64
import requests
import bcrypt
import json
import re
import io
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

app = FastAPI(title="Pipways API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pipways-web.onrender.com",
        "https://www.pipways.com",
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

# API Keys
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "sk_test_your_key_here")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "pk_test_your_key_here")
ZOOM_API_KEY = os.getenv("ZOOM_API_KEY", "your_zoom_key")
ZOOM_API_SECRET = os.getenv("ZOOM_API_SECRET", "your_zoom_secret")

# Database
DATABASE_URL = os.getenv("DATABASE_URL")

# Default admin
DEFAULT_ADMIN_EMAIL = "admin@pipways.com"
DEFAULT_ADMIN_PASSWORD = "admin123"

# Subscription settings
SUBSCRIPTION_PRICE = 15.00  # USD
FREE_TRIAL_DAYS = 3

async def get_db():
    conn = await asyncpg.connect(DATABASE_URL, ssl="require")
    try:
        yield conn
    finally:
        await conn.close()

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
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return int(user_id)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(user_id: int = Depends(verify_token), db=Depends(get_db)):
    row = await db.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(row)

def is_subscription_active(user: dict) -> bool:
    if user.get("is_admin"):
        return True
    if user.get("subscription_status") == "active":
        return True
    trial_end = user.get("trial_ends_at")
    if trial_end and trial_end > datetime.utcnow():
        return True
    return False

def is_trial_active(user: dict) -> bool:
    trial_end = user.get("trial_ends_at")
    if trial_end and trial_end > datetime.utcnow():
        return True
    return False

@app.on_event("startup")
async def startup():
    conn = await asyncpg.connect(DATABASE_URL, ssl="require")
    try:
        # Users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                name VARCHAR(255),
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                subscription_status VARCHAR(20) DEFAULT 'trial',
                subscription_ends_at TIMESTAMP,
                trial_ends_at TIMESTAMP,
                paystack_customer_code VARCHAR(255),
                paystack_subscription_code VARCHAR(255)
            )
        """)
        
        # Trades table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                pair VARCHAR(10) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                pips NUMERIC,
                grade VARCHAR(2),
                entry_price NUMERIC,
                exit_price NUMERIC,
                checklist_completed BOOLEAN DEFAULT FALSE,
                checklist_data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Blog posts table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blog_posts (
                id SERIAL PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                slug VARCHAR(500) UNIQUE NOT NULL,
                content TEXT,
                excerpt TEXT,
                category VARCHAR(100),
                tags TEXT[],
                featured_image TEXT,
                published BOOLEAN DEFAULT FALSE,
                view_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Performance analyses table
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
        
        # Courses table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                id SERIAL PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                description TEXT,
                level VARCHAR(20) NOT NULL, -- beginner, intermediate, advanced
                thumbnail_url TEXT,
                lessons JSONB DEFAULT '[]',
                quiz_questions JSONB DEFAULT '[]',
                passing_score INTEGER DEFAULT 70,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # User courses progress table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_courses (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                course_id INTEGER REFERENCES courses(id),
                progress_percentage INTEGER DEFAULT 0,
                completed_lessons INTEGER[] DEFAULT '{}',
                quiz_score INTEGER,
                quiz_attempts INTEGER DEFAULT 0,
                certificate_issued BOOLEAN DEFAULT FALSE,
                certificate_url TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, course_id)
            )
        """)
        
        # Webinars table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS webinars (
                id SERIAL PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                description TEXT,
                level VARCHAR(20) NOT NULL, -- beginner, intermediate, advanced
                scheduled_at TIMESTAMP NOT NULL,
                zoom_meeting_id VARCHAR(100),
                zoom_join_url TEXT,
                zoom_start_url TEXT,
                recording_url TEXT,
                is_recorded BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Webinar registrations table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS webinar_registrations (
                id SERIAL PRIMARY KEY,
                webinar_id INTEGER REFERENCES webinars(id),
                user_id INTEGER REFERENCES users(id),
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                attended BOOLEAN DEFAULT FALSE,
                UNIQUE(webinar_id, user_id)
            )
        """)
        
        # Payments table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                paystack_reference VARCHAR(255),
                amount NUMERIC,
                status VARCHAR(50),
                paid_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create default admin
        admin_exists = await conn.fetchval(
            "SELECT 1 FROM users WHERE email = $1", DEFAULT_ADMIN_EMAIL
        )
        if not admin_exists:
            hashed_pw = get_password_hash(DEFAULT_ADMIN_PASSWORD)
            await conn.execute("""
                INSERT INTO users (email, password_hash, name, is_admin, subscription_status)
                VALUES ($1, $2, 'Admin', TRUE, 'active')
            """, DEFAULT_ADMIN_EMAIL, hashed_pw)
            
        # Insert sample courses if none exist
        courses_exist = await conn.fetchval("SELECT COUNT(*) FROM courses")
        if courses_exist == 0:
            await conn.execute("""
                INSERT INTO courses (title, description, level, thumbnail_url, lessons, quiz_questions)
                VALUES 
                ('Forex Fundamentals', 'Learn the basics of forex trading', 'beginner', 'https://img.youtube.com/vi/sample1/0.jpg', 
                 '[{"id": 1, "title": "What is Forex?", "type": "video", "content": "https://youtube.com/embed/sample1", "duration_minutes": 15}]',
                 '[{"id": 1, "question": "What does forex stand for?", "options": ["Foreign exchange", "Fortune exchange", "For export"], "correct": 0}]'),
                ('Technical Analysis Mastery', 'Advanced chart patterns and indicators', 'intermediate', 'https://img.youtube.com/vi/sample2/0.jpg',
                 '[{"id": 1, "title": "Support and Resistance", "type": "video", "content": "https://youtube.com/embed/sample2", "duration_minutes": 20}]',
                 '[{"id": 1, "question": "What indicates a strong support level?", "options": ["Multiple touches", "Single touch", "No touches"], "correct": 0}]'),
                ('Institutional Trading', 'How banks and institutions trade', 'advanced', 'https://img.youtube.com/vi/sample3/0.jpg',
                 '[{"id": 1, "title": "Smart Money Concepts", "type": "video", "content": "https://youtube.com/embed/sample3", "duration_minutes": 25}]',
                 '[{"id": 1, "question": "What is order block?", "options": ["Last opposing candle before move", "Any candle", "First candle"], "correct": 0}]')
            """)
            
    finally:
        await conn.close()

# Auth endpoints
@app.post("/auth/register")
async def register(
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
    db=Depends(get_db)
):
    if len(password) > 72:
        raise HTTPException(status_code=400, detail="Password too long (max 72 characters)")
    
    existing = await db.fetchval("SELECT id FROM users WHERE email = $1", email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_pw = get_password_hash(password)
    trial_ends = datetime.utcnow() + timedelta(days=FREE_TRIAL_DAYS)
    
    user_id = await db.fetchval("""
        INSERT INTO users (email, password_hash, name, trial_ends_at, subscription_status)
        VALUES ($1, $2, $3, $4, 'trial')
        RETURNING id
    """, email, hashed_pw, name, trial_ends)
    
    access_token = create_access_token({"sub": str(user_id)})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "id": user_id,
        "email": email,
        "name": name,
        "is_admin": False,
        "subscription_status": "trial",
        "trial_ends_at": trial_ends.isoformat()
    }

@app.post("/auth/login")
async def login(email: str = Form(...), password: str = Form(...), db=Depends(get_db)):
    row = await db.fetchrow("SELECT * FROM users WHERE email = $1", email)
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token({"sub": str(row["id"])})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "is_admin": row["is_admin"],
        "subscription_status": row["subscription_status"],
        "trial_ends_at": row["trial_ends_at"].isoformat() if row["trial_ends_at"] else None,
        "subscription_ends_at": row["subscription_ends_at"].isoformat() if row["subscription_ends_at"] else None
    }

# Trades endpoints
@app.get("/trades")
async def get_trades(user=Depends(get_current_user), db=Depends(get_db)):
    rows = await db.fetch("""
        SELECT * FROM trades 
        WHERE user_id = $1 
        ORDER BY created_at DESC
    """, user["id"])
    return [dict(row) for row in rows]

@app.post("/trades")
async def create_trade(
    pair: str = Form(...),
    direction: str = Form(...),
    pips: str = Form(...),
    grade: str = Form(...),
    checklist_completed: str = Form("false"),
    checklist_data: str = Form("{}"),
    entry_price: Optional[str] = Form(None),
    exit_price: Optional[str] = Form(None),
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    # Check subscription limits
    if not is_subscription_active(user):
        raise HTTPException(status_code=403, detail="Subscription required")
    
    # Trial users limited to 5 trades
    if is_trial_active(user) and not user.get("subscription_status") == "active":
        trade_count = await db.fetchval(
            "SELECT COUNT(*) FROM trades WHERE user_id = $1", user["id"]
        )
        if trade_count >= 5:
            raise HTTPException(status_code=403, detail="Trial limit reached. Subscribe to continue.")
    
    try:
        pips_val = float(pips)
        entry_val = float(entry_price) if entry_price else None
        exit_val = float(exit_price) if exit_price else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid numeric value")
    
    trade_id = await db.fetchval("""
        INSERT INTO trades (user_id, pair, direction, pips, grade, entry_price, exit_price, checklist_completed, checklist_data)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
    """, user["id"], pair.upper(), direction, pips_val, grade, entry_val, exit_val, 
        checklist_completed.lower() == "true", json.loads(checklist_data))
    
    return {"id": trade_id, "message": "Trade created successfully"}

# Analytics endpoints
@app.get("/analytics/dashboard")
async def get_analytics(user=Depends(get_current_user), db=Depends(get_db)):
    trades = await db.fetch("SELECT * FROM trades WHERE user_id = $1", user["id"])
    trades_list = [dict(row) for row in trades]
    
    total_trades = len(trades_list)
    if total_trades == 0:
        return {
            "total_trades": 0,
            "win_rate": 0,
            "total_pips": 0,
            "profit_factor": 0,
            "grade_distribution": {},
            "pair_performance": [],
            "equity_curve": [],
            "monthly_performance": [],
            "checklist_adherence": 0
        }
    
    wins = sum(1 for t in trades_list if t["pips"] > 0)
    win_rate = round((wins / total_trades) * 100, 1)
    total_pips = sum(t["pips"] for t in trades_list)
    
    # Profit factor
    profit_pips = sum(t["pips"] for t in trades_list if t["pips"] > 0)
    loss_pips = abs(sum(t["pips"] for t in trades_list if t["pips"] < 0))
    profit_factor = round(profit_pips / loss_pips, 2) if loss_pips > 0 else profit_pips
    
    # Grade distribution
    grade_dist = {}
    for t in trades_list:
        g = t["grade"]
        grade_dist[g] = grade_dist.get(g, 0) + 1
    
    # Pair performance
    pair_stats = {}
    for t in trades_list:
        p = t["pair"]
        if p not in pair_stats:
            pair_stats[p] = {"trades": 0, "wins": 0, "pips": 0}
        pair_stats[p]["trades"] += 1
        if t["pips"] > 0:
            pair_stats[p]["wins"] += 1
        pair_stats[p]["pips"] += t["pips"]
    
    pair_performance = [
        {
            "pair": p,
            "trades": s["trades"],
            "win_rate": round((s["wins"] / s["trades"]) * 100, 1),
            "total_pips": round(s["pips"], 2)
        }
        for p, s in pair_stats.items()
    ]
    pair_performance.sort(key=lambda x: x["trades"], reverse=True)
    
    # Equity curve
    equity_curve = []
    cumulative = 0
    for t in sorted(trades_list, key=lambda x: x["created_at"]):
        cumulative += t["pips"]
        equity_curve.append({
            "date": t["created_at"].isoformat(),
            "cumulative_pips": round(cumulative, 2)
        })
    
    # Monthly performance
    monthly = {}
    for t in trades_list:
        month_key = t["created_at"].strftime("%Y-%m")
        if month_key not in monthly:
            monthly[month_key] = 0
        monthly[month_key] += t["pips"]
    
    monthly_performance = [
        {"month": m, "pips": round(p, 2)}
        for m, p in sorted(monthly.items())
    ]
    
    # Checklist adherence
    checklist_completed = sum(1 for t in trades_list if t.get("checklist_completed"))
    checklist_adherence = round((checklist_completed / total_trades) * 100, 1)
    
    return {
        "total_trades": total_trades,
        "win_rate": win_rate,
        "total_pips": round(total_pips, 2),
        "profit_factor": profit_factor,
        "grade_distribution": grade_dist,
        "pair_performance": pair_performance,
        "equity_curve": equity_curve,
        "monthly_performance": monthly_performance,
        "checklist_adherence": checklist_adherence
    }

# Checklist endpoints
@app.get("/checklist/template")
async def get_checklist_template(user=Depends(get_current_user)):
    return [
        {"id": 1, "text": "I have a clear entry strategy based on my trading plan", "required": True},
        {"id": 2, "text": "I have identified and set a definitive stop loss level", "required": True},
        {"id": 3, "text": "I have a realistic take profit target (minimum 1:1.5 R:R)", "required": True},
        {"id": 4, "text": "I have calculated position size (risking only 1-2% of account)", "required": True},
        {"id": 5, "text": "I am not trading out of FOMO, revenge, or emotion", "required": True},
        {"id": 6, "text": "I have checked the economic calendar for high-impact news", "required": False},
        {"id": 7, "text": "This setup meets my minimum A or B grade criteria", "required": True},
        {"id": 8, "text": "I have analyzed the higher timeframe trend direction", "required": False}
    ]

# Chart analysis endpoint
@app.post("/analyze-chart")
async def analyze_chart(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    if not is_subscription_active(user):
        raise HTTPException(status_code=403, detail="Subscription required")
    
    # Trial users limited to 1 analysis
    if is_trial_active(user) and not user.get("subscription_status") == "active":
        analysis_count = await db.fetchval(
            "SELECT COUNT(*) FROM performance_analyses WHERE user_id = $1", user["id"]
        )
        if analysis_count >= 1:
            raise HTTPException(status_code=403, detail="Trial analysis limit reached. Subscribe for unlimited access.")
    
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")
    
    image_b64 = base64.b64encode(contents).decode()
    
    # Call OpenRouter for analysis
    if OPENROUTER_API_KEY:
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://pipways.com"
                },
                json={
                    "model": "anthropic/claude-3.5-sonnet",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": """Analyze this trading chart image and provide a detailed trading setup analysis. 
                                    Return ONLY a JSON object with this exact structure:
                                    {
                                        "setup_quality": "A|B|C",
                                        "pair": "EURUSD",
                                        "direction": "LONG|SHORT",
                                        "entry_price": "1.08500",
                                        "stop_loss": "1.08200",
                                        "take_profit": "1.09000",
                                        "risk_reward": "1:1.67",
                                        "analysis": "Detailed technical analysis...",
                                        "recommendations": "Specific recommendations...",
                                        "key_levels": ["1.08500", "1.08200", "1.09000"]
                                    }"""
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{image_b64}"}
                                }
                            ]
                        }
                    ],
                    "max_tokens": 1000
                },
                timeout=60
            )
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                return {
                    "success": True,
                    "analysis": analysis,
                    "image_data": image_b64[:100] + "..."  # Truncated for response
                }
        except Exception as e:
            print(f"AI analysis error: {e}")
    
    # Fallback response
    return {
        "success": True,
        "analysis": {
            "setup_quality": "B",
            "pair": "EURUSD",
            "direction": "LONG",
            "entry_price": "1.08500",
            "stop_loss": "1.08200",
            "take_profit": "1.09000",
            "risk_reward": "1:1.67",
            "analysis": "Chart shows potential bullish momentum. Price is testing key support level with bullish candlestick pattern forming. RSI indicates oversold conditions.",
            "recommendations": "Wait for confirmation candle close above support. Consider partial entry now and add on breakout confirmation.",
            "key_levels": ["1.08500", "1.08200", "1.09000", "1.09500"]
        },
        "image_data": image_b64[:100] + "...",
        "fallback": True
    }

# Performance analysis endpoint
@app.post("/performance/analyze")
async def analyze_performance(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    if not is_subscription_active(user):
        raise HTTPException(status_code=403, detail="Subscription required")
    
    # Trial users limited to 1 analysis
    if is_trial_active(user) and not user.get("subscription_status") == "active":
        analysis_count = await db.fetchval(
            "SELECT COUNT(*) FROM performance_analyses WHERE user_id = $1", user["id"]
        )
        if analysis_count >= 1:
            raise HTTPException(status_code=403, detail="Trial analysis limit reached. Subscribe for unlimited access.")
    
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")
    
    # Get user's trade summary
    trades = await db.fetch("SELECT * FROM trades WHERE user_id = $1", user["id"])
    trades_summary = {
        "total_trades": len(trades),
        "win_rate": 0,
        "avg_pips": 0,
        "favorite_pairs": []
    }
    
    if trades:
        wins = sum(1 for t in trades if t["pips"] > 0)
        trades_summary["win_rate"] = round((wins / len(trades)) * 100, 1)
        trades_summary["avg_pips"] = round(sum(t["pips"] for t in trades) / len(trades), 2)
        
        pair_counts = {}
        for t in trades:
            pair_counts[t["pair"]] = pair_counts.get(t["pair"], 0) + 1
        trades_summary["favorite_pairs"] = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    
    file_b64 = base64.b64encode(contents).decode()
    file_ext = file.filename.split('.')[-1].lower()
    
    analysis_result = None
    
    if OPENROUTER_API_KEY and file_ext in ['png', 'jpg', 'jpeg', 'pdf']:
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://pipways.com"
                },
                json={
                    "model": "anthropic/claude-3.5-sonnet",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"""Analyze this trading history file and the user's stats. 
                                    User stats: {json.dumps(trades_summary)}
                                    
                                    Return ONLY a JSON object with this exact structure:
                                    {{
                                        "trader_type": "Scalper|Day Trader|Swing Trader|Position Trader|Mixed",
                                        "performance_score": 75,
                                        "score_breakdown": {{
                                            "profitability": 80,
                                            "risk_management": 70,
                                            "consistency": 75,
                                            "psychology": 65
                                        }},
                                        "risk_appetite": "Conservative|Moderate|Aggressive",
                                        "strengths": ["Strength 1", "Strength 2"],
                                        "weaknesses": ["Weakness 1", "Weakness 2"],
                                        "key_insights": "Overall insights...",
                                        "improvement_plan": ["Step 1", "Step 2", "Step 3"],
                                        "recommended_courses": [
                                            {{"title": "Course Name", "level": "Beginner|Intermediate|Advanced", "priority": "High|Medium|Low"}}
                                        ],
                                        "monthly_goal": "Specific achievable goal..."
                                    }}"""
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{file_b64}"}
                                }
                            ]
                        }
                    ],
                    "max_tokens": 1500
                },
                timeout=90
            )
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                analysis_result = json.loads(json_match.group())
        except Exception as e:
            print(f"AI performance analysis error: {e}")
    
    # Fallback or if no AI
    if not analysis_result:
        analysis_result = {
            "trader_type": "Day Trader" if trades_summary["total_trades"] > 10 else "Developing Trader",
            "performance_score": 65,
            "score_breakdown": {
                "profitability": trades_summary["win_rate"],
                "risk_management": 60,
                "consistency": 55,
                "psychology": 70
            },
            "risk_appetite": "Moderate",
            "strengths": ["Consistent journaling", "Following process"],
            "weaknesses": ["Need more data for detailed analysis"],
            "key_insights": "Continue logging trades for AI-powered insights.",
            "improvement_plan": [
                "Complete pre-trade checklist for every trade",
                "Review losing trades weekly",
                "Set specific monthly pip targets"
            ],
            "recommended_courses": [
                {"title": "Trading Psychology Mastery", "level": "Beginner", "priority": "High"},
                {"title": "Risk Management Fundamentals", "level": "Beginner", "priority": "High"}
            ],
            "monthly_goal": f"Log 20 trades with complete checklist. Current: {trades_summary['total_trades']} trades"
        }
    
    # Store analysis
    await db.execute("""
        INSERT INTO performance_analyses 
        (user_id, file_name, file_data, analysis_result, trader_type, performance_score, risk_appetite, recommendations, courses_recommended)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    """, user["id"], file.filename, file_b64[:1000], json.dumps(analysis_result),
        analysis_result["trader_type"], analysis_result["performance_score"],
        analysis_result["risk_appetite"], analysis_result["improvement_plan"],
        json.dumps(analysis_result["recommended_courses"]))
    
    return {
        "success": True,
        "analysis": analysis_result
    }

@app.get("/performance/history")
async def get_performance_history(user=Depends(get_current_user), db=Depends(get_db)):
    rows = await db.fetch("""
        SELECT id, trader_type, performance_score, risk_appetite, created_at
        FROM performance_analyses
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT 10
    """, user["id"])
    return [dict(row) for row in rows]

# Mentor chat endpoint
@app.get("/mentor-chat")
async def mentor_chat(
    message: str = Query(...),
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    if not is_subscription_active(user):
        raise HTTPException(status_code=403, detail="Subscription required")
    
    # Get user's context
    trades = await db.fetch("SELECT * FROM trades WHERE user_id = $1 LIMIT 20", user["id"])
    recent_analyses = await db.fetch(
        "SELECT * FROM performance_analyses WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1", 
        user["id"]
    )
    
    # Get available courses for recommendations
    courses = await db.fetch("SELECT id, title, level FROM courses ORDER BY level")
    courses_list = [dict(c) for c in courses]
    
    context = {
        "user_name": user["name"],
        "total_trades": len(trades),
        "recent_performance": dict(recent_analyses[0]) if recent_analyses else None,
        "available_courses": courses_list
    }
    
    if OPENROUTER_API_KEY:
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://pipways.com"
                },
                json={
                    "model": "anthropic/claude-3.5-sonnet",
                    "messages": [
                        {
                            "role": "system",
                            "content": f"""You are an expert trading mentor and psychologist. 
                            Help traders with psychology, risk management, and discipline.
                            User context: {json.dumps(context)}
                            Available courses: {json.dumps(courses_list)}
                            
                            When relevant, recommend specific courses from the available list.
                            Be encouraging but firm about discipline and risk management."""
                        },
                        {
                            "role": "user",
                            "content": message
                        }
                    ],
                    "max_tokens": 800
                },
                timeout=30
            )
            
            result = response.json()
            return {
                "response": result["choices"][0]["message"]["content"],
                "fallback": False
            }
        except Exception as e:
            print(f"Mentor chat error: {e}")
    
    # Fallback responses
    fallbacks = {
        "fomo": "FOMO is a common challenge. Remember: there's always another trade. Stick to your plan and only take A-grade setups. Consider reviewing the 'Trading Psychology Mastery' course.",
        "risk": "Never risk more than 1-2% per trade. Your position size should allow you to be wrong 10 times in a row and still have capital to trade. Check out 'Risk Management Fundamentals'.",
        "loss": "Every trader has losing streaks. Review your trades objectively - were they good setups that just didn't work, or did you break your rules? Learn from both.",
        "discipline": "Discipline is what separates successful traders from failed ones. Use the pre-trade checklist for EVERY trade, no exceptions. Track your discipline score daily."
    }
    
    response_text = fallbacks.get("discipline")
    for key in fallbacks:
        if key in message.lower():
            response_text = fallbacks[key]
            break
    
    return {
        "response": response_text,
        "fallback": True
    }

# Blog endpoints
@app.get("/blog/posts")
async def get_blog_posts(limit: int = 10, db=Depends(get_db)):
    rows = await db.fetch("""
        SELECT id, title, slug, excerpt, category, featured_image, view_count, created_at
        FROM blog_posts
        WHERE published = TRUE
        ORDER BY created_at DESC
        LIMIT $1
    """, limit)
    return [dict(row) for row in rows]

@app.get("/blog/posts/{slug}")
async def get_blog_post(slug: str, db=Depends(get_db)):
    row = await db.fetchrow("""
        SELECT * FROM blog_posts WHERE slug = $1 AND published = TRUE
    """, slug)
    
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Increment view count
    await db.execute(
        "UPDATE blog_posts SET view_count = view_count + 1 WHERE id = $1",
        row["id"]
    )
    
    return dict(row)

# Admin endpoints
@app.get("/admin/stats")
async def admin_stats(user=Depends(get_current_user), db=Depends(get_db)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    
    users_count = await db.fetchval("SELECT COUNT(*) FROM users")
    trades_count = await db.fetchval("SELECT COUNT(*) FROM trades")
    posts = await db.fetch("SELECT published, view_count FROM blog_posts")
    
    total_posts = len(posts)
    published_posts = sum(1 for p in posts if p["published"])
    total_views = sum(p["view_count"] for p in posts)
    
    return {
        "users": users_count,
        "trades": trades_count,
        "blog_posts": {
            "total": total_posts,
            "published": published_posts,
            "total_views": total_views
        }
    }

@app.get("/admin/blog/posts")
async def admin_get_posts(user=Depends(get_current_user), db=Depends(get_db)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    
    rows = await db.fetch("""
        SELECT id, title, slug, category, published, view_count, created_at
        FROM blog_posts
        ORDER BY created_at DESC
    """)
    return [dict(row) for row in rows]

@app.post("/admin/blog/posts")
async def admin_create_post(
    title: str = Form(...),
    slug: str = Form(...),
    content: str = Form(...),
    excerpt: str = Form(""),
    category: str = Form(""),
    tags: str = Form(""),
    featured_image: str = Form(""),
    published: str = Form("false"),
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    
    tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    
    try:
        post_id = await db.fetchval("""
            INSERT INTO blog_posts (title, slug, content, excerpt, category, tags, featured_image, published)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
        """, title, slug, content, excerpt, category, tags_list, featured_image, published.lower() == "true")
        
        return {"id": post_id, "message": "Post created successfully"}
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=400, detail="Slug already exists")

@app.put("/admin/blog/posts/{post_id}")
async def admin_update_post(
    post_id: int,
    title: str = Form(...),
    slug: str = Form(...),
    content: str = Form(...),
    excerpt: str = Form(""),
    category: str = Form(""),
    tags: str = Form(""),
    featured_image: str = Form(""),
    published: str = Form("false"),
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    
    tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    
    await db.execute("""
        UPDATE blog_posts 
        SET title = $1, slug = $2, content = $3, excerpt = $4, 
            category = $5, tags = $6, featured_image = $7, 
            published = $8, updated_at = CURRENT_TIMESTAMP
        WHERE id = $9
    """, title, slug, content, excerpt, category, tags_list, featured_image, 
        published.lower() == "true", post_id)
    
    return {"message": "Post updated successfully"}

@app.delete("/admin/blog/posts/{post_id}")
async def admin_delete_post(post_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    
    await db.execute("DELETE FROM blog_posts WHERE id = $1", post_id)
    return {"message": "Post deleted successfully"}

# Course endpoints
@app.get("/courses")
async def get_courses(user=Depends(get_current_user), db=Depends(get_db)):
    if not is_subscription_active(user):
        raise HTTPException(status_code=403, detail="Subscription required")
    
    rows = await db.fetch("""
        SELECT c.*, 
               uc.progress_percentage, uc.completed_lessons, uc.quiz_score,
               uc.certificate_issued, uc.certificate_url
        FROM courses c
        LEFT JOIN user_courses uc ON c.id = uc.course_id AND uc.user_id = $1
        ORDER BY c.level, c.created_at
    """, user["id"])
    
    return [dict(row) for row in rows]

@app.get("/courses/{course_id}")
async def get_course(course_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    if not is_subscription_active(user):
        raise HTTPException(status_code=403, detail="Subscription required")
    
    course = await db.fetchrow("SELECT * FROM courses WHERE id = $1", course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Get or create user progress
    progress = await db.fetchrow("""
        SELECT * FROM user_courses WHERE user_id = $1 AND course_id = $2
    """, user["id"], course_id)
    
    if not progress:
        progress = await db.fetchrow("""
            INSERT INTO user_courses (user_id, course_id)
            VALUES ($1, $2)
            RETURNING *
        """, user["id"], course_id)
    
    result = dict(course)
    result["progress"] = dict(progress)
    return result

@app.post("/courses/{course_id}/progress")
async def update_course_progress(
    course_id: int,
    lesson_id: int = Form(...),
    completed: bool = Form(...),
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    if not is_subscription_active(user):
        raise HTTPException(status_code=403, detail="Subscription required")
    
    # Get current progress
    progress = await db.fetchrow("""
        SELECT * FROM user_courses WHERE user_id = $1 AND course_id = $2
    """, user["id"], course_id)
    
    if not progress:
        raise HTTPException(status_code=404, detail="Course not started")
    
    completed_lessons = list(progress["completed_lessons"] or [])
    
    if completed and lesson_id not in completed_lessons:
        completed_lessons.append(lesson_id)
    elif not completed and lesson_id in completed_lessons:
        completed_lessons.remove(lesson_id)
    
    # Calculate progress percentage
    course = await db.fetchrow("SELECT lessons FROM courses WHERE id = $1", course_id)
    total_lessons = len(json.loads(course["lessons"])) if course["lessons"] else 1
    progress_pct = int((len(completed_lessons) / total_lessons) * 100)
    
    await db.execute("""
        UPDATE user_courses 
        SET completed_lessons = $1, progress_percentage = $2, last_accessed = CURRENT_TIMESTAMP
        WHERE id = $3
    """, completed_lessons, progress_pct, progress["id"])
    
    return {"progress": progress_pct, "completed_lessons": completed_lessons}

@app.post("/courses/{course_id}/quiz")
async def submit_quiz(
    course_id: int,
    answers: str = Form(...),  # JSON array of answer indices
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    if not is_subscription_active(user):
        raise HTTPException(status_code=403, detail="Subscription required")
    
    course = await db.fetchrow("SELECT quiz_questions, passing_score FROM courses WHERE id = $1", course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    questions = json.loads(course["quiz_questions"]) if course["quiz_questions"] else []
    user_answers = json.loads(answers)
    
    correct = sum(1 for i, q in enumerate(questions) if user_answers[i] == q["correct"])
    score = int((correct / len(questions)) * 100) if questions else 0
    
    # Update quiz score and attempts
    progress = await db.fetchrow("""
        SELECT * FROM user_courses WHERE user_id = $1 AND course_id = $2
    """, user["id"], course_id)
    
    if progress:
        await db.execute("""
            UPDATE user_courses 
            SET quiz_score = $1, quiz_attempts = quiz_attempts + 1
            WHERE id = $2
        """, score, progress["id"])
    
    # Generate certificate if passed
    certificate_url = None
    if score >= course["passing_score"] and progress:
        if not progress["certificate_issued"]:
            certificate_url = await generate_certificate(user["id"], course_id, user["name"], db)
            await db.execute("""
                UPDATE user_courses 
                SET certificate_issued = TRUE, certificate_url = $1, completed_at = CURRENT_TIMESTAMP
                WHERE id = $2
            """, certificate_url, progress["id"])
        else:
            certificate_url = progress["certificate_url"]
    
    return {
        "score": score,
        "passed": score >= course["passing_score"],
        "certificate_url": certificate_url
    }

async def generate_certificate(user_id: int, course_id: int, user_name: str, db) -> str:
    """Generate a PDF certificate and return the URL/path"""
    course = await db.fetchrow("SELECT title FROM courses WHERE id = $1", course_id)
    
    # Create PDF in memory
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Certificate design
    c.setFillColorRGB(0.95, 0.95, 0.95)
    c.rect(0, 0, width, height, fill=True, stroke=False)
    
    # Border
    c.setStrokeColorRGB(0.2, 0.4, 0.8)
    c.setLineWidth(3)
    c.rect(50, 50, width-100, height-100)
    
    # Title
    c.setFillColorRGB(0.1, 0.2, 0.4)
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(width/2, height-150, "CERTIFICATE")
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(width/2, height-200, "OF COMPLETION")
    
    # Content
    c.setFont("Helvetica", 18)
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.drawCentredString(width/2, height-280, "This certifies that")
    
    c.setFont("Helvetica-Bold", 28)
    c.setFillColorRGB(0.1, 0.2, 0.4)
    c.drawCentredString(width/2, height-330, user_name or "Student")
    
    c.setFont("Helvetica", 18)
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.drawCentredString(width/2, height-380, "has successfully completed")
    
    c.setFont("Helvetica-Bold", 22)
    c.setFillColorRGB(0.2, 0.4, 0.8)
    c.drawCentredString(width/2, height-430, course["title"])
    
    # Date
    c.setFont("Helvetica", 14)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    date_str = datetime.now().strftime("%B %d, %Y")
    c.drawCentredString(width/2, height-500, f"Completed on {date_str}")
    
    # Signature line
    c.setStrokeColorRGB(0.2, 0.2, 0.2)
    c.line(width/2-100, 150, width/2+100, 150)
    c.setFont("Helvetica", 12)
    c.drawCentredString(width/2, 130, "Pipways Academy")
    
    c.save()
    
    # In production, upload to cloud storage and return URL
    # For now, return a data URL
    buffer.seek(0)
    pdf_b64 = base64.b64encode(buffer.read()).decode()
    return f"data:application/pdf;base64,{pdf_b64}"

# Webinar endpoints
@app.get("/webinars")
async def get_webinars(user=Depends(get_current_user), db=Depends(get_db)):
    if not is_subscription_active(user):
        raise HTTPException(status_code=403, detail="Subscription required")
    
    # Get upcoming and recent webinars
    rows = await db.fetch("""
        SELECT w.*, 
               EXISTS(SELECT 1 FROM webinar_registrations 
                      WHERE webinar_id = w.id AND user_id = $1) as is_registered
        FROM webinars w
        WHERE w.scheduled_at > NOW() - INTERVAL '7 days'
        ORDER BY w.scheduled_at ASC
    """, user["id"])
    
    return [dict(row) for row in rows]

@app.post("/webinars/{webinar_id}/register")
async def register_webinar(webinar_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    if not is_subscription_active(user):
        raise HTTPException(status_code=403, detail="Subscription required")
    
    try:
        await db.execute("""
            INSERT INTO webinar_registrations (webinar_id, user_id)
            VALUES ($1, $2)
        """, webinar_id, user["id"])
        return {"message": "Registered successfully"}
    except asyncpg.UniqueViolationError:
        return {"message": "Already registered"}

# Paystack payment endpoints
@app.get("/payments/config")
async def get_payment_config(user=Depends(get_current_user)):
    return {
        "public_key": PAYSTACK_PUBLIC_KEY,
        "amount": int(SUBSCRIPTION_PRICE * 100),  # Paystack uses kobo/cents
        "email": user["email"]
    }

@app.post("/payments/initialize")
async def initialize_payment(user=Depends(get_current_user), db=Depends(get_db)):
    if not PAYSTACK_SECRET_KEY or "your_key" in PAYSTACK_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payment system not configured")
    
    # Create or get Paystack customer
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    
    # Initialize transaction
    payload = {
        "email": user["email"],
        "amount": int(SUBSCRIPTION_PRICE * 100),
        "plan": "monthly",  # You'd create this plan in Paystack dashboard
        "callback_url": "https://pipways-web.onrender.com/payment/callback"
    }
    
    response = requests.post(
        "https://api.paystack.co/transaction/initialize",
        headers=headers,
        json=payload
    )
    
    result = response.json()
    if result.get("status"):
        return {
            "authorization_url": result["data"]["authorization_url"],
            "reference": result["data"]["reference"]
        }
    else:
        raise HTTPException(status_code=400, detail=result.get("message", "Payment initialization failed"))

@app.get("/payments/verify/{reference}")
async def verify_payment(reference: str, user=Depends(get_current_user), db=Depends(get_db)):
    if not PAYSTACK_SECRET_KEY or "your_key" in PAYSTACK_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payment system not configured")
    
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(
        f"https://api.paystack.co/transaction/verify/{reference}",
        headers=headers
    )
    
    result = response.json()
    if result.get("status") and result["data"]["status"] == "success":
        # Update user subscription
        subscription_ends = datetime.utcnow() + timedelta(days=30)
        await db.execute("""
            UPDATE users 
            SET subscription_status = 'active',
                subscription_ends_at = $1,
                paystack_subscription_code = $2
            WHERE id = $3
        """, subscription_ends, result["data"].get("subscription_code"), user["id"])
        
        # Record payment
        await db.execute("""
            INSERT INTO payments (user_id, paystack_reference, amount, status, paid_at)
            VALUES ($1, $2, $3, 'success', CURRENT_TIMESTAMP)
        """, user["id"], reference, SUBSCRIPTION_PRICE)
        
        return {
            "status": "success",
            "message": "Subscription activated",
            "subscription_ends_at": subscription_ends.isoformat()
        }
    else:
        raise HTTPException(status_code=400, detail="Payment verification failed")

@app.get("/subscription/status")
async def get_subscription_status(user=Depends(get_current_user)):
    is_active = is_subscription_active(user)
    is_trial = is_trial_active(user) and user.get("subscription_status") != "active"
    
    return {
        "is_active": is_active,
        "is_trial": is_trial,
        "status": user.get("subscription_status", "trial"),
        "trial_ends_at": user["trial_ends_at"].isoformat() if user.get("trial_ends_at") else None,
        "subscription_ends_at": user["subscription_ends_at"].isoformat() if user.get("subscription_ends_at") else None
    }

# Zoom webhook for recording
@app.post("/webhooks/zoom/recording")
async def zoom_recording_webhook(request: dict, db=Depends(get_db)):
    """Handle Zoom recording completed webhook"""
    if request.get("event") == "recording.completed":
        meeting_id = request["payload"]["object"]["id"]
        recording_url = request["payload"]["object"]["recording_files"][0]["download_url"]
        
        # Update webinar with recording
        await db.execute("""
            UPDATE webinars 
            SET recording_url = $1, is_recorded = TRUE
            WHERE zoom_meeting_id = $2
        """, recording_url, meeting_id)
    
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
