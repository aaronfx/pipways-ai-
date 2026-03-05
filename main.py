"""
Pipways Trading Platform API
Enhanced with SEO-friendly blog, media management, and optimized PDF processing
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Form, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
from pathlib import Path
import uuid
import os
import json
import re
import asyncio
import aiofiles
import hashlib
from contextlib import asynccontextmanager

# Security & Auth
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# Database (using SQLite for simplicity - replace with PostgreSQL for production)
import sqlite3
from contextlib import contextmanager

# PDF Processing - Using PyMuPDF for speed and reliability
import fitz  # PyMuPDF - faster than pdfplumber and PyPDF2
import pandas as pd
import io

# Image processing
from PIL import Image
import imghdr

# Email validation
import email_validator

app = FastAPI(
    title="Pipways API",
    description="Institutional Trader Development Platform",
    version="2.0.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
MEDIA_DIR = UPLOAD_DIR / "media"
MEDIA_DIR.mkdir(exist_ok=True)
PDF_TEMP_DIR = UPLOAD_DIR / "pdf_temp"
PDF_TEMP_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf", 
    "text/csv", 
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/html"
}

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Database Setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pipways.db")

def get_db_connection():
    """Get database connection with row factory"""
    # Parse DATABASE_URL to extract file path
    # Handle both "sqlite:///path/to/db.db" and just "path/to/db.db"
    db_url = DATABASE_URL
    
    if db_url.startswith("sqlite:///"):
        # Remove the sqlite:/// prefix (handles both absolute and relative paths)
        db_path = db_url[10:]
    elif db_url.startswith("sqlite://"):
        db_path = db_url[9:]
    else:
        db_path = db_url
    
    # Ensure the directory exists for the database file
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initialize database tables"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                name TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pair TEXT NOT NULL,
                direction TEXT NOT NULL,
                pips REAL NOT NULL,
                grade TEXT NOT NULL,
                entry_price REAL,
                exit_price REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Enhanced Blog Posts table with SEO fields
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blog_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                excerpt TEXT,
                featured_image TEXT,
                category TEXT DEFAULT 'general',
                tags TEXT, -- JSON array
                status TEXT DEFAULT 'draft', -- draft, published, archived
                meta_title TEXT, -- SEO meta title
                meta_description TEXT, -- SEO meta description
                meta_keywords TEXT, -- SEO keywords
                og_image TEXT, -- Open Graph image
                author_id INTEGER,
                view_count INTEGER DEFAULT 0,
                published_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (author_id) REFERENCES users(id)
            )
        """)
        
        # Media Library table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                mime_type TEXT NOT NULL,
                alt_text TEXT,
                uploaded_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (uploaded_by) REFERENCES users(id)
            )
        """)
        
        # Trade Analyses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                trader_score INTEGER,
                trader_type TEXT,
                analysis_data TEXT, -- JSON
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Chart Analyses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chart_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                analysis_data TEXT, -- JSON
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        conn.commit()

@app.on_event("startup")
async def startup_event():
    init_db()

# Pydantic Models
class UserCreate(BaseModel):
    email: str
    password: str
    name: str

class User(BaseModel):
    id: int
    email: str
    name: str
    is_admin: bool
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user: User

class TradeCreate(BaseModel):
    pair: str
    direction: str
    pips: float
    grade: str
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None

class Trade(BaseModel):
    id: int
    pair: str
    direction: str
    pips: float
    grade: str
    created_at: datetime
    
    class Config:
        from_attributes = True

# Enhanced Blog Models with SEO
class BlogPostCreate(BaseModel):
    title: str
    content: str
    excerpt: Optional[str] = None
    category: str = "general"
    tags: Optional[List[str]] = None
    status: str = "draft"
    featured_image_id: Optional[int] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None

class BlogPostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    excerpt: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    featured_image_id: Optional[int] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None

class BlogPostResponse(BaseModel):
    id: int
    title: str
    slug: str
    content: str
    excerpt: Optional[str]
    featured_image: Optional[str]
    category: str
    tags: List[str]
    status: str
    meta_title: Optional[str]
    meta_description: Optional[str]
    meta_keywords: Optional[str]
    og_image: Optional[str]
    author: Optional[User]
    view_count: int
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class MediaResponse(BaseModel):
    id: int
    filename: str
    original_name: str
    url: str
    file_type: str
    file_size: int
    mime_type: str
    alt_text: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

class ChartAnalysisResponse(BaseModel):
    success: bool
    analysis: Dict[str, Any]
    image_data: Optional[str] = None
    error: Optional[str] = None

class TradeAnalysisResponse(BaseModel):
    success: bool
    analysis: Dict[str, Any]
    error: Optional[str] = None

# Helper Functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def generate_slug(title: str) -> str:
    """Generate URL-friendly slug from title"""
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug[:200]  # Limit length

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if user is None:
            raise credentials_exception
        return dict(user)

async def validate_file_type(file: UploadFile, allowed_types: set) -> bool:
    """Validate file type by content"""
    content = await file.read(2048)  # Read first 2KB for magic number check
    await file.seek(0)
    
    # Check MIME type
    if file.content_type not in allowed_types:
        return False
    
    # Additional magic number check for images
    if file.content_type.startswith('image/'):
        file_type = imghdr.what(None, content)
        if not file_type:
            return False
    
    return True

async def save_upload_file(upload_file: UploadFile, destination: Path) -> str:
    """Save uploaded file with streaming for large files"""
    file_id = str(uuid.uuid4())
    extension = Path(upload_file.filename).suffix
    filename = f"{file_id}{extension}"
    file_path = destination / filename
    
    # Stream file in chunks
    async with aiofiles.open(file_path, 'wb') as out_file:
        while chunk := await upload_file.read(1024 * 1024):  # 1MB chunks
            await out_file.write(chunk)
    
    return str(file_path.relative_to(UPLOAD_DIR))

def process_image_for_web(file_path: Path, max_width: int = 1920, max_height: int = 1080) -> Path:
    """Process and optimize image for web"""
    with Image.open(file_path) as img:
        # Convert to RGB if necessary
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1] if img.mode != 'P' else None)
            img = background
        
        # Resize if too large
        if img.width > max_width or img.height > max_height:
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        
        # Save optimized version
        output_path = file_path.parent / f"{file_path.stem}_optimized{file_path.suffix}"
        img.save(output_path, 'JPEG', quality=85, optimize=True)
        return output_path

# Optimized PDF Processing with PyMuPDF
async def extract_text_from_pdf(file_path: Path) -> str:
    """Fast PDF text extraction using PyMuPDF"""
    text = []
    try:
        # Open PDF with PyMuPDF (much faster than pdfplumber)
        doc = fitz.open(file_path)
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            # Extract text with layout preservation
            text.append(f"\n--- Page {page_num + 1} ---\n")
            text.append(page.get_text("text"))
        
        doc.close()
        return "\n".join(text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF processing error: {str(e)}")

async def extract_tables_from_pdf(file_path: Path) -> List[pd.DataFrame]:
    """Extract tables from PDF using PyMuPDF + pandas"""
    tables = []
    try:
        doc = fitz.open(file_path)
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            # Find tables using PyMuPDF
            tabs = page.find_tables()
            
            if tabs.tables:
                for tab in tabs.tables:
                    # Extract table as pandas DataFrame
                    df = pd.DataFrame(tab.extract())
                    tables.append(df)
        
        doc.close()
        return tables
    except Exception as e:
        # If table extraction fails, return empty list
        return []

async def process_trading_statement(file_path: Path, file_type: str) -> Dict[str, Any]:
    """Process trading statement with optimized extraction"""
    content = ""
    tables = []
    
    try:
        if file_type == "application/pdf":
            # Use PyMuPDF for fast extraction
            content = await extract_text_from_pdf(file_path)
            tables = await extract_tables_from_pdf(file_path)
        elif file_type in ["text/csv", "application/vnd.ms-excel", 
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]:
            # Process Excel/CSV
            if file_type == "text/csv":
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            tables = [df]
            content = df.to_string()
        elif file_type == "text/html":
            # Process HTML (MT4/MT5 statements)
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = await f.read()
            # Parse HTML tables
            tables = pd.read_html(str(file_path))
        
        # Analyze trading data
        analysis = analyze_trading_data(content, tables)
        return analysis
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Processing error: {str(e)}")

def analyze_trading_data(content: str, tables: List[pd.DataFrame]) -> Dict[str, Any]:
    """AI-powered trading analysis (simplified version - integrate with your AI)"""
    # This is a placeholder - replace with your actual AI analysis logic
    analysis = {
        "trader_score": 75,
        "trader_type": "developing_scalper",
        "trader_type_confidence": 80,
        "score_breakdown": {
            "risk_management": 70,
            "consistency": 65,
            "profitability": 80,
            "psychology": 75,
            "strategy": 85
        },
        "mistakes_detected": [
            {
                "mistake": "Oversized positions",
                "frequency": "frequent",
                "impact": "High risk exposure",
                "evidence": "Position sizes exceed 2% risk rule"
            }
        ],
        "patterns_detected": [
            {
                "pattern": "Revenge trading",
                "occurrence": "After losses",
                "consequence": "Increased drawdown"
            }
        ],
        "recommendations": [
            "Implement strict position sizing",
            "Use stop losses consistently",
            "Keep a trading journal"
        ],
        "learning_resources": [
            "Risk Management Masterclass",
            "Trading Psychology Guide"
        ],
        "projected_improvement": "With consistent practice, expect 15% improvement in 3 months"
    }
    
    return analysis

# Authentication Endpoints
@app.post("/auth/register", response_model=Token)
async def register(
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form(...)
):
    """Register new user"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create user
        hashed_password = get_password_hash(password)
        cursor.execute(
            "INSERT INTO users (email, hashed_password, name) VALUES (?, ?, ?)",
            (email, hashed_password, name)
        )
        conn.commit()
        user_id = cursor.lastrowid
        
        # Get created user
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = dict(cursor.fetchone())
        
        access_token = create_access_token(
            data={"sub": str(user_id)},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": User(**user)
        }

@app.post("/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login user"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (form_data.username,))
        user = cursor.fetchone()
        
        if not user or not verify_password(form_data.password, user["hashed_password"]):
            raise HTTPException(
                status_code=401,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token = create_access_token(
            data={"sub": str(user["id"])},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": User(**dict(user))
        }

# Trade Endpoints
@app.get("/trades", response_model=List[Trade])
async def get_trades(current_user: dict = Depends(get_current_user)):
    """Get all trades for current user"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM trades WHERE user_id = ? ORDER BY created_at DESC",
            (current_user["id"],)
        )
        trades = [dict(row) for row in cursor.fetchall()]
        return [Trade(**trade) for trade in trades]

@app.post("/trades", response_model=Trade)
async def create_trade(
    trade: TradeCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create new trade"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO trades 
               (user_id, pair, direction, pips, grade, entry_price, exit_price) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (current_user["id"], trade.pair.upper(), trade.direction, 
             trade.pips, trade.grade, trade.entry_price, trade.exit_price)
        )
        conn.commit()
        trade_id = cursor.lastrowid
        
        cursor.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
        return Trade(**dict(cursor.fetchone()))

# Enhanced Blog Endpoints with SEO
@app.get("/blog/posts", response_model=Dict[str, Any])
async def get_blog_posts(
    status: str = Query("published"),
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=100)
):
    """Get blog posts with filtering and pagination"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        query = "SELECT * FROM blog_posts WHERE status = ?"
        params = [status]
        
        if category and category != "all":
            query += " AND category = ?"
            params.append(category)
        
        if search:
            query += " AND (title LIKE ? OR content LIKE ? OR meta_keywords LIKE ?)"
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])
        
        # Get total count
        count_query = query.replace("SELECT *", "SELECT COUNT(*)")
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
        
        # Get paginated results
        query += " ORDER BY published_at DESC LIMIT ? OFFSET ?"
        params.extend([per_page, (page - 1) * per_page])
        
        cursor.execute(query, params)
        posts = [dict(row) for row in cursor.fetchall()]
        
        # Parse tags and get author info
        for post in posts:
            post["tags"] = json.loads(post["tags"]) if post["tags"] else []
            if post["author_id"]:
                cursor.execute("SELECT id, email, name, is_admin FROM users WHERE id = ?", 
                             (post["author_id"],))
                author = cursor.fetchone()
                post["author"] = dict(author) if author else None
        
        return {
            "posts": [BlogPostResponse(**post) for post in posts],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        }

@app.get("/blog/post/{slug}", response_model=BlogPostResponse)
async def get_blog_post(slug: str):
    """Get single blog post by slug"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM blog_posts WHERE slug = ?", (slug,))
        post = cursor.fetchone()
        
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        post = dict(post)
        
        # Increment view count
        cursor.execute("UPDATE blog_posts SET view_count = view_count + 1 WHERE id = ?", 
                      (post["id"],))
        conn.commit()
        
        post["tags"] = json.loads(post["tags"]) if post["tags"] else []
        
        # Get author
        if post["author_id"]:
            cursor.execute("SELECT id, email, name, is_admin FROM users WHERE id = ?", 
                         (post["author_id"],))
            author = cursor.fetchone()
            post["author"] = dict(author) if author else None
        
        return BlogPostResponse(**post)

@app.post("/admin/blog/posts", response_model=BlogPostResponse)
async def create_blog_post(
    title: str = Form(...),
    content: str = Form(...),
    excerpt: Optional[str] = Form(None),
    category: str = Form("general"),
    tags: Optional[str] = Form(None),  # JSON string
    status: str = Form("draft"),
    featured_image_id: Optional[int] = Form(None),
    meta_title: Optional[str] = Form(None),
    meta_description: Optional[str] = Form(None),
    meta_keywords: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """Create new blog post with SEO fields"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Generate slug
    base_slug = generate_slug(title)
    slug = base_slug
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Ensure unique slug
        counter = 1
        while True:
            cursor.execute("SELECT id FROM blog_posts WHERE slug = ?", (slug,))
            if not cursor.fetchone():
                break
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        # Parse tags
        tag_list = json.loads(tags) if tags else []
        
        # Get featured image URL if provided
        featured_image = None
        og_image = None
        if featured_image_id:
            cursor.execute("SELECT file_path FROM media WHERE id = ?", (featured_image_id,))
            media = cursor.fetchone()
            if media:
                featured_image = f"/uploads/{media['file_path']}"
                og_image = featured_image
        
        # Set published date if publishing
        published_at = None
        if status == "published":
            published_at = datetime.utcnow().isoformat()
        
        # Auto-generate meta description if not provided
        if not meta_description and excerpt:
            meta_description = excerpt[:160]
        elif not meta_description:
            meta_description = content[:160].replace("<[^>]*>", "")  # Strip HTML
        
        cursor.execute("""
            INSERT INTO blog_posts 
            (title, slug, content, excerpt, featured_image, category, tags, status,
             meta_title, meta_description, meta_keywords, og_image, author_id, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            title, slug, content, excerpt, featured_image, category, 
            json.dumps(tag_list), status, meta_title or title, meta_description,
            meta_keywords, og_image, current_user["id"], published_at
        ))
        conn.commit()
        post_id = cursor.lastrowid
        
        cursor.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,))
        post = dict(cursor.fetchone())
        post["tags"] = tag_list
        post["author"] = User(**current_user)
        
        return BlogPostResponse(**post)

@app.put("/admin/blog/posts/{post_id}", response_model=BlogPostResponse)
async def update_blog_post(
    post_id: int,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    featured_image_id: Optional[int] = Form(None),
    meta_title: Optional[str] = Form(None),
    meta_description: Optional[str] = Form(None),
    meta_keywords: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """Update blog post"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,))
        post = cursor.fetchone()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Build update query dynamically
        updates = []
        params = []
        
        if title:
            updates.append("title = ?")
            params.append(title)
            # Update slug if title changes
            new_slug = generate_slug(title)
            cursor.execute("SELECT id FROM blog_posts WHERE slug = ? AND id != ?", 
                          (new_slug, post_id))
            if not cursor.fetchone():
                updates.append("slug = ?")
                params.append(new_slug)
        
        if content:
            updates.append("content = ?")
            params.append(content)
        if excerpt is not None:
            updates.append("excerpt = ?")
            params.append(excerpt)
        if category:
            updates.append("category = ?")
            params.append(category)
        if tags is not None:
            updates.append("tags = ?")
            params.append(tags)
        if status:
            updates.append("status = ?")
            params.append(status)
            if status == "published" and post["status"] != "published":
                updates.append("published_at = ?")
                params.append(datetime.utcnow().isoformat())
        if featured_image_id is not None:
            if featured_image_id:
                cursor.execute("SELECT file_path FROM media WHERE id = ?", (featured_image_id,))
                media = cursor.fetchone()
                if media:
                    updates.append("featured_image = ?")
                    params.append(f"/uploads/{media['file_path']}")
                    updates.append("og_image = ?")
                    params.append(f"/uploads/{media['file_path']}")
            else:
                updates.append("featured_image = NULL")
        if meta_title is not None:
            updates.append("meta_title = ?")
            params.append(meta_title)
        if meta_description is not None:
            updates.append("meta_description = ?")
            params.append(meta_description)
        if meta_keywords is not None:
            updates.append("meta_keywords = ?")
            params.append(meta_keywords)
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        
        if updates:
            query = f"UPDATE blog_posts SET {', '.join(updates)} WHERE id = ?"
            params.append(post_id)
            cursor.execute(query, params)
            conn.commit()
        
        cursor.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,))
        updated_post = dict(cursor.fetchone())
        updated_post["tags"] = json.loads(updated_post["tags"]) if updated_post["tags"] else []
        
        return BlogPostResponse(**updated_post)

@app.delete("/admin/blog/posts/{post_id}")
async def delete_blog_post(
    post_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Delete blog post"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM blog_posts WHERE id = ?", (post_id,))
        conn.commit()
        return {"message": "Post deleted successfully"}

# Media Management Endpoints
@app.post("/admin/media/upload", response_model=MediaResponse)
async def upload_media(
    file: UploadFile = File(...),
    alt_text: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """Upload media file with validation and optimization"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Validate file type
    if not await validate_file_type(file, ALLOWED_IMAGE_TYPES | ALLOWED_DOCUMENT_TYPES):
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    # Check file size
    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE and file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Image too large (max 10MB)")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")
    
    await file.seek(0)
    
    # Generate safe filename
    file_id = str(uuid.uuid4())
    extension = Path(file.filename).suffix.lower()
    if file.content_type == "image/jpeg" and extension not in ['.jpg', '.jpeg']:
        extension = '.jpg'
    elif file.content_type == "image/png" and extension != '.png':
        extension = '.png'
    
    filename = f"{file_id}{extension}"
    file_path = MEDIA_DIR / filename
    
    # Save file
    async with aiofiles.open(file_path, 'wb') as out_file:
        await out_file.write(content)
    
    # Process images for web
    if file.content_type.startswith('image/'):
        try:
            optimized_path = process_image_for_web(file_path)
            # Replace original with optimized
            file_path.unlink()
            optimized_path.rename(file_path)
            file_size = file_path.stat().st_size
        except Exception:
            file_size = len(content)
    else:
        file_size = len(content)
    
    # Save to database
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO media (filename, original_name, file_path, file_type, file_size, mime_type, alt_text, uploaded_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            filename, file.filename, f"media/{filename}", 
            extension.lstrip('.'), file_size, file.content_type, alt_text, current_user["id"]
        ))
        conn.commit()
        media_id = cursor.lastrowid
        
        return MediaResponse(
            id=media_id,
            filename=filename,
            original_name=file.filename,
            url=f"/uploads/media/{filename}",
            file_type=extension.lstrip('.'),
            file_size=file_size,
            mime_type=file.content_type,
            alt_text=alt_text,
            created_at=datetime.utcnow()
        )

@app.get("/admin/media", response_model=List[MediaResponse])
async def list_media(
    file_type: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """List all media files"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        if file_type:
            cursor.execute("SELECT * FROM media WHERE file_type = ? ORDER BY created_at DESC", (file_type,))
        else:
            cursor.execute("SELECT * FROM media ORDER BY created_at DESC")
        
        media_list = []
        for row in cursor.fetchall():
            media = dict(row)
            media["url"] = f"/uploads/{media['file_path']}"
            media_list.append(MediaResponse(**media))
        
        return media_list

@app.delete("/admin/media/{media_id}")
async def delete_media(
    media_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Delete media file"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM media WHERE id = ?", (media_id,))
        media = cursor.fetchone()
        
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")
        
        # Delete file
        file_path = UPLOAD_DIR / media["file_path"]
        if file_path.exists():
            file_path.unlink()
        
        cursor.execute("DELETE FROM media WHERE id = ?", (media_id,))
        conn.commit()
        
        return {"message": "Media deleted successfully"}

# Optimized Chart Analysis
@app.post("/analyze-chart", response_model=ChartAnalysisResponse)
async def analyze_chart(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Analyze chart image with AI"""
    # Validate image
    if not await validate_file_type(file, ALLOWED_IMAGE_TYPES):
        raise HTTPException(status_code=400, detail="Invalid image format. Use JPEG, PNG, or WebP.")
    
    # Save uploaded file
    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}{Path(file.filename).suffix}"
    
    async with aiofiles.open(file_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)
    
    try:
        # Convert image to base64 for AI processing
        import base64
        with open(file_path, "rb") as img_file:
            image_data = base64.b64encode(img_file.read()).decode()
        
        # TODO: Integrate with your AI model here
        # For now, return mock analysis
        analysis = {
            "setup_quality": "A",
            "pair": "EURUSD",
            "direction": "LONG",
            "entry_price": "1.08500",
            "stop_loss": "1.08200",
            "take_profit": "1.09200",
            "risk_reward": "1:2.3",
            "analysis": "Strong bullish setup with support at 1.08200. Price action shows higher lows formation.",
            "recommendations": "Enter on pullback to 1.08400-1.08500 zone with stop below 1.08200.",
            "key_levels": ["1.08200", "1.08500", "1.09000", "1.09200"]
        }
        
        # Save analysis to database
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO chart_analyses (user_id, image_path, analysis_data) VALUES (?, ?, ?)",
                (current_user["id"], str(file_path.relative_to(UPLOAD_DIR)), json.dumps(analysis))
            )
            conn.commit()
        
        return ChartAnalysisResponse(
            success=True,
            analysis=analysis,
            image_data=image_data
        )
        
    except Exception as e:
        return ChartAnalysisResponse(
            success=False,
            analysis={},
            error=str(e)
        )
    finally:
        # Cleanup
        if file_path.exists():
            file_path.unlink()

# Optimized Trade Analysis with Fast PDF Processing
@app.post("/analyze-trade-file", response_model=TradeAnalysisResponse)
async def analyze_trade_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Analyze trading statement with optimized processing"""
    # Validate file type
    allowed_types = ALLOWED_DOCUMENT_TYPES | {"application/octet-stream"}
    if file.content_type not in allowed_types and not file.filename.endswith(('.pdf', '.csv', '.xls', '.xlsx', '.html', '.htm')):
        raise HTTPException(status_code=400, detail="Invalid file format")
    
    # Save file temporarily
    file_id = str(uuid.uuid4())
    extension = Path(file.filename).suffix or '.pdf'
    temp_path = PDF_TEMP_DIR / f"{file_id}{extension}"
    
    try:
        # Stream file to disk
        async with aiofiles.open(temp_path, 'wb') as out_file:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                await out_file.write(chunk)
        
        # Determine MIME type if not provided
        mime_type = file.content_type
        if mime_type == "application/octet-stream":
            if extension == '.pdf':
                mime_type = "application/pdf"
            elif extension in ['.csv']:
                mime_type = "text/csv"
            elif extension in ['.xls', '.xlsx']:
                mime_type = "application/vnd.ms-excel"
            elif extension in ['.html', '.htm']:
                mime_type = "text/html"
        
        # Process with timeout
        try:
            analysis = await asyncio.wait_for(
                process_trading_statement(temp_path, mime_type),
                timeout=30.0  # 30 second timeout
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=408, detail="Analysis timeout - file too complex")
        
        # Save to database
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trade_analyses 
                (user_id, filename, file_type, trader_score, trader_type, analysis_data)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                current_user["id"], file.filename, mime_type,
                analysis.get("trader_score"), analysis.get("trader_type"),
                json.dumps(analysis)
            ))
            conn.commit()
        
        return TradeAnalysisResponse(success=True, analysis=analysis)
        
    except HTTPException:
        raise
    except Exception as e:
        return TradeAnalysisResponse(success=False, analysis={}, error=str(e))
    finally:
        # Cleanup temp file
        if temp_path.exists():
            temp_path.unlink()

@app.get("/trade-analyses")
async def get_trade_analyses(current_user: dict = Depends(get_current_user)):
    """Get user's trade analysis history"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, filename, trader_type, trader_score, created_at 
            FROM trade_analyses 
            WHERE user_id = ? 
            ORDER BY created_at DESC
        """, (current_user["id"],))
        
        analyses = []
        for row in cursor.fetchall():
            analyses.append({
                "id": row["id"],
                "filename": row["filename"],
                "trader_type": row["trader_type"],
                "trader_score": row["trader_score"],
                "created_at": row["created_at"]
            })
        
        return analyses

# AI Mentor Endpoint
@app.post("/mentorship/personalized")
async def mentorship_personalized(
    message: str = Form(...),
    context_type: str = Form("general"),
    current_user: dict = Depends(get_current_user)
):
    """AI Mentor for trading psychology"""
    # TODO: Integrate with your AI model
    responses = {
        "fomo": "FOMO (Fear Of Missing Out) is dangerous. Stick to your trading plan and only take setups that meet your criteria.",
        "risk": "Proper risk management means never risking more than 1-2% of your account per trade.",
        "review": "Review losing trades by checking: 1) Did you follow your plan? 2) Was the setup valid? 3) What can you improve?",
        "plan": "A trading plan should include: entry criteria, exit rules, position sizing, and risk management."
    }
    
    # Simple keyword matching (replace with AI)
    response_text = responses.get(context_type, 
        "I'm here to help with your trading psychology and discipline. What specific aspect would you like to discuss?")
    
    return {
        "personalized_response": response_text,
        "identified_pattern": context_type if context_type != "general" else None,
        "actionable_steps": ["Stick to your plan", "Manage risk properly", "Review trades daily"]
    }

# Admin Dashboard
@app.get("/admin/dashboard")
async def admin_dashboard(current_user: dict = Depends(get_current_user)):
    """Get admin dashboard statistics"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # User stats
        cursor.execute("SELECT COUNT(*) as total FROM users")
        total_users = cursor.fetchone()["total"]
        
        cursor.execute("""
            SELECT COUNT(*) as new_users 
            FROM users 
            WHERE created_at >= datetime('now', '-7 days')
        """)
        new_users_7d = cursor.fetchone()["new_users"]
        
        # Trade stats
        cursor.execute("SELECT COUNT(*) as total FROM trades")
        total_trades = cursor.fetchone()["total"]
        
        cursor.execute("""
            SELECT COUNT(*) as recent 
            FROM trades 
            WHERE created_at >= datetime('now', '-7 days')
        """)
        trades_7d = cursor.fetchone()["recent"]
        
        # Blog stats
        cursor.execute("""
            SELECT COUNT(*) as published 
            FROM blog_posts 
            WHERE status = 'published'
        """)
        published_posts = cursor.fetchone()["published"]
        
        cursor.execute("SELECT SUM(view_count) as total_views FROM blog_posts")
        total_views = cursor.fetchone()["total_views"] or 0
        
        # Analysis stats
        cursor.execute("SELECT AVG(trader_score) as avg_score FROM trade_analyses")
        avg_trader_score = cursor.fetchone()["avg_score"] or 0
        
        cursor.execute("SELECT COUNT(*) as total FROM trade_analyses")
        total_analyses = cursor.fetchone()["total"]
        
        # Recent activity
        cursor.execute("""
            SELECT id, name, created_at 
            FROM users 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        recent_users = [dict(row) for row in cursor.fetchall()]
        
        return {
            "users": {
                "total_users": total_users,
                "new_users_7d": new_users_7d
            },
            "trades": {
                "total_trades": total_trades,
                "trades_7d": trades_7d
            },
            "blog": {
                "published_posts": published_posts,
                "total_views": total_views
            },
            "analyses": {
                "avg_trader_score": round(avg_trader_score, 1),
                "total_analyses": total_analyses
            },
            "recent_activity": {
                "users": recent_users
            }
        }

@app.get("/admin/users")
async def list_users(current_user: dict = Depends(get_current_user)):
    """List all users (admin only)"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, name, is_admin, created_at FROM users ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]

# Static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
