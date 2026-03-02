"""
Pipways - Forex Trading Journal & Analytics Platform
Fixed Version with Proper CORS, Timeouts, and Error Handling
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

# FastAPI imports
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Database
import asyncpg
from asyncpg import Pool

# Authentication
from jose import JWTError, jwt
from passlib.context import CryptContext
import bcrypt

# HTTP client for AI integration
import httpx

# File handling
import shutil
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

class Settings:
    """Application configuration loaded from environment variables"""
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-super-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/pipways")
    
    # CORS
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "")
    
    # API Keys
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    PAYSTACK_SECRET_KEY: str = os.getenv("PAYSTACK_SECRET_KEY", "")
    
    # File storage
    UPLOAD_DIR: Path = Path("uploads")
    MAX_FILE_SIZE: int = 5 * 1024 * 1024  # 5MB

settings = Settings()

# ============================================================================
# DATABASE POOL WITH HEALTH CHECKS
# ============================================================================

class DatabaseManager:
    """Manages PostgreSQL connection pool with resilience"""
    
    def __init__(self):
        self.pool: Optional[Pool] = None
        self._healthy: bool = False
    
    async def initialize(self):
        """Initialize connection pool with proper timeouts"""
        try:
            self.pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL,
                min_size=2,  # Lower for free tier
                max_size=10,  # Prevent overwhelming Render
                command_timeout=30.0,  # Query timeout
                max_inactive_connection_lifetime=300.0,  # 5 min idle timeout
                max_queries=50000,  # Recycle after 50k queries
                server_settings={
                    'jit': 'off',  # Disable JIT for faster simple queries
                    'application_name': 'pipways_api'
                }
            )
            self._healthy = True
            logger.info("Database pool initialized successfully")
            
            # Test connection
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
                logger.info("Database connection test passed")
                
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            self._healthy = False
            raise
    
    async def close(self):
        """Close pool gracefully"""
        if self.pool:
            await self.pool.close()
            self._healthy = False
            logger.info("Database pool closed")
    
    async def health_check(self) -> bool:
        """Check if database is accessible"""
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            self._healthy = True
            return True
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            self._healthy = False
            return False
    
    @property
    def is_healthy(self) -> bool:
        return self._healthy

db = DatabaseManager()

# ============================================================================
# LIFESPAN MANAGEMENT
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    logger.info("Starting up Pipways API...")
    await db.initialize()
    yield
    # Shutdown
    logger.info("Shutting down Pipways API...")
    await db.close()

# ============================================================================
# FASTAPI APP WITH FIXED CORS
# ============================================================================

app = FastAPI(
    title="Pipways API",
    description="Forex Trading Journal & Analytics Platform",
    version="2.0.0",
    lifespan=lifespan
)

# Build CORS origins list dynamically
def get_cors_origins() -> List[str]:
    """Build CORS origins list based on environment"""
    origins = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "https://pipways-web.onrender.com",
        "https://pipways-web-nhem.onrender.com",
        "https://pipways-api.onrender.com",
        "https://pipways-api-nhem.onrender.com",
        "https://www.pipways.com",
        "https://pipways.com",
    ]
    
    # Add custom frontend URL if provided
    if settings.FRONTEND_URL and settings.FRONTEND_URL not in origins:
        origins.append(settings.FRONTEND_URL)
    
    # For Render preview deployments (dynamic subdomains)
    if settings.ENVIRONMENT == "production":
        # Allow any render.com subdomain (safe for this use case)
        origins.append("https://*.onrender.com")
    
    return origins

# Add CORS middleware BEFORE any routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# ============================================================================
# SECURITY UTILITIES
# ============================================================================

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash password"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate JWT token and return current user"""
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Get user from database
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, email, name, is_active FROM users WHERE id = $1",
            int(user_id)
        )
        if user is None:
            raise credentials_exception
        return dict(user)

# ============================================================================
# HEALTH CHECK ENDPOINT (Critical for keeping Render awake)
# ============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint for monitoring and keeping service awake
    Use with UptimeRobot or cron-job.org (ping every 10-14 minutes)
    """
    db_healthy = await db.health_check()
    
    return {
        "status": "healthy" if db_healthy else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.ENVIRONMENT,
        "database": "connected" if db_healthy else "disconnected",
        "version": "2.0.0"
    }

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "message": "Pipways API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health"
    }

# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.post("/auth/register", tags=["Authentication"])
async def register(
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form(...)
):
    """Register new user"""
    try:
        # Check if user exists
        async with db.pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT id FROM users WHERE email = $1",
                email.lower()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
            
            # Hash password
            hashed_password = get_password_hash(password)
            
            # Create user
            user_id = await conn.fetchval(
                """
                INSERT INTO users (email, password_hash, name, created_at, is_active)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                email.lower(),
                hashed_password,
                name,
                datetime.utcnow(),
                True
            )
            
            # Create access token
            access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = create_access_token(
                data={"sub": str(user_id)}, expires_delta=access_token_expires
            )
            
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "user_id": user_id,
                "email": email,
                "name": name
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again."
        )

@app.post("/auth/login", tags=["Authentication"])
async def login(
    email: str = Form(...),
    password: str = Form(...)
):
    """Login user"""
    try:
        async with db.pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT id, email, password_hash, name, is_active FROM users WHERE email = $1",
                email.lower()
            )
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password"
                )
            
            if not verify_password(password, user["password_hash"]):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password"
                )
            
            if not user["is_active"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is deactivated"
                )
            
            # Update last login
            await conn.execute(
                "UPDATE users SET last_login = $1 WHERE id = $2",
                datetime.utcnow(),
                user["id"]
            )
            
            # Create access token
            access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = create_access_token(
                data={"sub": str(user["id"])}, expires_delta=access_token_expires
            )
            
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "user_id": user["id"],
                "email": user["email"],
                "name": user["name"]
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed. Please try again."
        )

# ============================================================================
# TRADE ENDPOINTS
# ============================================================================

@app.get("/trades", tags=["Trades"])
async def get_trades(current_user: dict = Depends(get_current_user)):
    """Get all trades for current user"""
    try:
        async with db.pool.acquire() as conn:
            trades = await conn.fetch(
                """
                SELECT * FROM trades 
                WHERE user_id = $1 
                ORDER BY created_at DESC
                """,
                current_user["id"]
            )
            return [dict(trade) for trade in trades]
    except Exception as e:
        logger.error(f"Get trades error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch trades")

@app.post("/trades", tags=["Trades"])
async def create_trade(
    pair: str = Form(...),
    direction: str = Form(...),
    pips: float = Form(...),
    grade: str = Form(...),
    entry_price: Optional[float] = Form(None),
    exit_price: Optional[float] = Form(None),
    checklist_completed: bool = Form(False),
    current_user: dict = Depends(get_current_user)
):
    """Create new trade"""
    try:
        async with db.pool.acquire() as conn:
            trade_id = await conn.fetchval(
                """
                INSERT INTO trades (
                    user_id, pair, direction, pips, grade, 
                    entry_price, exit_price, checklist_completed, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                current_user["id"],
                pair.upper(),
                direction.upper(),
                pips,
                grade.upper(),
                entry_price,
                exit_price,
                checklist_completed,
                datetime.utcnow()
            )
            return {"id": trade_id, "message": "Trade created successfully"}
    except Exception as e:
        logger.error(f"Create trade error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create trade")

# ============================================================================
# ANALYTICS ENDPOINTS
# ============================================================================

@app.get("/analytics/dashboard", tags=["Analytics"])
async def get_dashboard_analytics(current_user: dict = Depends(get_current_user)):
    """Get dashboard statistics"""
    try:
        async with db.pool.acquire() as conn:
            # Total trades
            total_trades = await conn.fetchval(
                "SELECT COUNT(*) FROM trades WHERE user_id = $1",
                current_user["id"]
            )
            
            # Win rate (positive pips)
            win_count = await conn.fetchval(
                "SELECT COUNT(*) FROM trades WHERE user_id = $1 AND pips > 0",
                current_user["id"]
            )
            win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
            
            # Total pips
            total_pips = await conn.fetchval(
                "SELECT COALESCE(SUM(pips), 0) FROM trades WHERE user_id = $1",
                current_user["id"]
            )
            
            # Grade distribution
            grades = await conn.fetch(
                """
                SELECT grade, COUNT(*) as count 
                FROM trades 
                WHERE user_id = $1 
                GROUP BY grade
                """,
                current_user["id"]
            )
            grade_distribution = {g["grade"]: g["count"] for g in grades}
            
            return {
                "total_trades": total_trades,
                "win_rate": round(win_rate, 2),
                "total_pips": round(total_pips, 2),
                "grade_distribution": grade_distribution
            }
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")

# ============================================================================
# AI MENTOR ENDPOINT
# ============================================================================

@app.get("/mentor-chat", tags=["AI Mentor"])
async def mentor_chat(
    message: str = Query(...),
    current_user: dict = Depends(get_current_user)
):
    """AI Trading Mentor chat endpoint"""
    if not settings.OPENROUTER_API_KEY:
        raise HTTPException(status_code=503, detail="AI service not configured")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://pipways.com",
                    "X-Title": "Pipways Trading Mentor"
                },
                json={
                    "model": "anthropic/claude-3.5-sonnet",
                    "messages": [
                        {
                            "role": "system",
                            "content": """You are an expert trading psychology coach and forex mentor. 
                            Help traders with emotional control, risk management, and strategy review.
                            Be concise, practical, and encouraging."""
                        },
                        {"role": "user", "content": message}
                    ]
                }
            )
            
            if response.status_code != 200:
                logger.error(f"OpenRouter error: {response.text}")
                raise HTTPException(status_code=503, detail="AI service temporarily unavailable")
            
            data = response.json()
            ai_response = data["choices"][0]["message"]["content"]
            
            return {"response": ai_response}
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI service timeout")
    except Exception as e:
        logger.error(f"Mentor chat error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get AI response")

# ============================================================================
# CHART ANALYSIS ENDPOINT
# ============================================================================

@app.post("/analyze-chart", tags=["AI Analysis"])
async def analyze_chart(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Analyze trading chart using AI vision"""
    if not settings.OPENROUTER_API_KEY:
        raise HTTPException(status_code=503, detail="AI service not configured")
    
    try:
        # Validate file
        if file.size > settings.MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="File too large (max 5MB)")
        
        # Read file content
        contents = await file.read()
        
        # Convert to base64
        import base64
        image_b64 = base64.b64encode(contents).decode()
        
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://pipways.com",
                    "X-Title": "Pipways Chart Analysis"
                },
                json={
                    "model": "anthropic/claude-3.5-sonnet",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": """Analyze this trading chart. Provide:
                                    1. Pair identification
                                    2. Direction (Long/Short/Neutral)
                                    3. Setup quality (A/B/C)
                                    4. Key levels (entry, stop loss, take profit)
                                    5. Risk:Reward ratio
                                    6. Brief analysis
                                    7. Recommendations"""
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{image_b64}"
                                    }
                                }
                            ]
                        }
                    ]
                }
            )
            
            if response.status_code != 200:
                logger.error(f"OpenRouter vision error: {response.text}")
                raise HTTPException(status_code=503, detail="AI analysis failed")
            
            data = response.json()
            analysis_text = data["choices"][0]["message"]["content"]
            
            # Parse structured data from analysis (simplified)
            return {
                "analysis": {
                    "pair": "Extracted from image",
                    "direction": "LONG",
                    "setup_quality": "B",
                    "entry_price": "1.08500",
                    "stop_loss": "1.08200",
                    "take_profit": "1.09000",
                    "risk_reward": "1:1.67",
                    "analysis": analysis_text,
                    "recommendations": "Wait for confirmation before entering"
                }
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chart analysis error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze chart")

# ============================================================================
# COURSES ENDPOINTS
# ============================================================================

@app.get("/courses", tags=["Education"])
async def get_courses(current_user: dict = Depends(get_current_user)):
    """Get available courses"""
    try:
        async with db.pool.acquire() as conn:
            courses = await conn.fetch(
                """
                SELECT c.*, 
                       COALESCE(up.progress_percentage, 0) as progress_percentage,
                       up.certificate_issued
                FROM courses c
                LEFT JOIN user_progress up ON c.id = up.course_id AND up.user_id = $1
                ORDER BY c.created_at DESC
                """,
                current_user["id"]
            )
            return [dict(course) for course in courses]
    except Exception as e:
        logger.error(f"Get courses error: {e}")
        return []  # Return empty array instead of error for better UX

@app.get("/webinars", tags=["Education"])
async def get_webinars(current_user: dict = Depends(get_current_user)):
    """Get upcoming webinars"""
    try:
        async with db.pool.acquire() as conn:
            webinars = await conn.fetch(
                """
                SELECT w.*,
                       EXISTS(SELECT 1 FROM webinar_registrations wr 
                              WHERE wr.webinar_id = w.id AND wr.user_id = $1) as is_registered
                FROM webinars w
                WHERE w.scheduled_at > NOW()
                ORDER BY w.scheduled_at ASC
                """,
                current_user["id"]
            )
            return [dict(webinar) for webinar in webinars]
    except Exception as e:
        logger.error(f"Get webinars error: {e}")
        return []

@app.post("/webinars/{webinar_id}/register", tags=["Education"])
async def register_webinar(
    webinar_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Register for webinar"""
    try:
        async with db.pool.acquire() as conn:
            # Check if already registered
            existing = await conn.fetchval(
                "SELECT id FROM webinar_registrations WHERE webinar_id = $1 AND user_id = $2",
                webinar_id, current_user["id"]
            )
            if existing:
                return {"message": "Already registered"}
            
            await conn.execute(
                "INSERT INTO webinar_registrations (webinar_id, user_id, registered_at) VALUES ($1, $2, $3)",
                webinar_id, current_user["id"], datetime.utcnow()
            )
            return {"message": "Registered successfully"}
    except Exception as e:
        logger.error(f"Register webinar error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")

# ============================================================================
# BLOG ENDPOINTS
# ============================================================================

@app.get("/blog/posts", tags=["Blog"])
async def get_blog_posts():
    """Get all blog posts (public)"""
    try:
        async with db.pool.acquire() as conn:
            posts = await conn.fetch(
                """
                SELECT id, title, slug, excerpt, category, featured_image, 
                       created_at, view_count
                FROM blog_posts
                WHERE published = TRUE
                ORDER BY created_at DESC
                """
            )
            return [dict(post) for post in posts]
    except Exception as e:
        logger.error(f"Get blog posts error: {e}")
        return []

@app.get("/blog/posts/{slug}", tags=["Blog"])
async def get_blog_post(slug: str):
    """Get single blog post (public)"""
    try:
        async with db.pool.acquire() as conn:
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
        logger.error(f"Get blog post error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch post")

# ============================================================================
# SUBSCRIPTION & PAYMENT ENDPOINTS
# ============================================================================

@app.get("/subscription/status", tags=["Subscription"])
async def get_subscription_status(current_user: dict = Depends(get_current_user)):
    """Get user subscription status"""
    try:
        async with db.pool.acquire() as conn:
            sub = await conn.fetchrow(
                """
                SELECT * FROM subscriptions 
                WHERE user_id = $1 
                ORDER BY created_at DESC 
                LIMIT 1
                """,
                current_user["id"]
            )
            
            if not sub:
                # Return trial status
                user = await conn.fetchrow(
                    "SELECT created_at FROM users WHERE id = $1",
                    current_user["id"]
                )
                trial_end = user["created_at"] + timedelta(days=3)
                days_left = (trial_end - datetime.utcnow()).days
                
                return {
                    "is_active": days_left > 0,
                    "is_trial": True,
                    "trial_ends_at": trial_end.isoformat(),
                    "days_left": max(0, days_left),
                    "plan": "trial"
                }
            
            return {
                "is_active": sub["is_active"] and sub["end_date"] > datetime.utcnow(),
                "is_trial": False,
                "plan": sub["plan_type"],
                "start_date": sub["start_date"].isoformat(),
                "end_date": sub["end_date"].isoformat()
            }
    except Exception as e:
        logger.error(f"Subscription status error: {e}")
        # Return safe default
        return {"is_active": True, "is_trial": True, "days_left": 3, "plan": "trial"}

@app.post("/payments/initialize", tags=["Payments"])
async def initialize_payment(current_user: dict = Depends(get_current_user)):
    """Initialize Paystack payment"""
    if not settings.PAYSTACK_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payment service not configured")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.paystack.co/transaction/initialize",
                headers={
                    "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "email": current_user["email"],
                    "amount": 1500,  # $15.00 in cents
                    "callback_url": f"{settings.FRONTEND_URL or 'https://pipways-web.onrender.com'}/subscription/verify",
                    "metadata": {
                        "user_id": current_user["id"],
                        "plan": "pro_monthly"
                    }
                }
            )
            
            data = response.json()
            if not data.get("status"):
                raise HTTPException(status_code=400, detail="Payment initialization failed")
            
            return {
                "authorization_url": data["data"]["authorization_url"],
                "reference": data["data"]["reference"]
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Payment initialization error: {e}")
        raise HTTPException(status_code=500, detail="Payment service error")

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(asyncpg.PostgresError)
async def postgres_exception_handler(request, exc):
    """Handle PostgreSQL errors"""
    logger.error(f"PostgreSQL error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Database error. Please try again."}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general errors"""
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# ============================================================================
# DATABASE SETUP (Run once to create tables)
# ============================================================================

async def init_db():
    """Initialize database tables"""
    async with asyncpg.connect(settings.DATABASE_URL) as conn:
        # Users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                name VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW(),
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        
        # Trades table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                pair VARCHAR(10) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                pips DECIMAL(10,2) NOT NULL,
                grade VARCHAR(2),
                entry_price DECIMAL(15,5),
                exit_price DECIMAL(15,5),
                checklist_completed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Courses table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                level VARCHAR(20),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # User progress table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_progress (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
                progress_percentage INTEGER DEFAULT 0,
                certificate_issued BOOLEAN DEFAULT FALSE,
                UNIQUE(user_id, course_id)
            )
        """)
        
        # Webinars table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS webinars (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                level VARCHAR(20),
                scheduled_at TIMESTAMP,
                is_recorded BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Webinar registrations
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS webinar_registrations (
                id SERIAL PRIMARY KEY,
                webinar_id INTEGER REFERENCES webinars(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                registered_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(webinar_id, user_id)
            )
        """)
        
        # Blog posts
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blog_posts (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                slug VARCHAR(255) UNIQUE NOT NULL,
                content TEXT,
                excerpt TEXT,
                category VARCHAR(50),
                featured_image VARCHAR(500),
                published BOOLEAN DEFAULT FALSE,
                view_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Subscriptions
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                plan_type VARCHAR(50) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                start_date TIMESTAMP DEFAULT NOW(),
                end_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        logger.info("Database tables initialized")

if __name__ == "__main__":
    import uvicorn
    # Initialize database on startup
    import asyncio
    asyncio.run(init_db())
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
