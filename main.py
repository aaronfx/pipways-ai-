from fastapi import FastAPI, HTTPException, Depends, status, File, UploadFile, Form, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
import json
import os
import uvicorn

# Import your existing modules
from blog_routes import router as blog_router
from ai_blog_tools import router as ai_blog_router

# Security setup
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

app = FastAPI(title="Pipways API", version="2.0")

# CORS - Update this with your actual frontend URL in production
origins = [
    "http://localhost:8000",
    "http://localhost:3000",
    "http://localhost:5500",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:5500",
    "https://pipways-api-nhem.onrender.com",
    "https://pipways.com",
    "*"  # Remove this in production and specify exact origins
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(blog_router, prefix="/admin", tags=["blog-admin"])
app.include_router(ai_blog_router, prefix="/admin", tags=["ai-blog"])

# Static files - serve frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Models
class User(BaseModel):
    id: int
    email: EmailStr
    name: str
    is_admin: bool = False

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str

class Token(BaseModel):
    access_token: str
    token_type: str

class LoginData(BaseModel):
    email: EmailStr
    password: str

# Mock database - replace with your actual database
users_db = [
    {
        "id": 1,
        "email": "admin@pipways.com",
        "name": "Admin User",
        "hashed_password": pwd_context.hash("admin123"),
        "is_admin": True
    }
]

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_user(email: str):
    for user in users_db:
        if user["email"] == email:
            return user
    return None

def authenticate_user(email: str, password: str):
    user = get_user(email)
    if not user:
        return False
    if not verify_password(password, user["hashed_password"]):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user(email)
    if user is None:
        raise credentials_exception
    return user

# Routes
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main SPA"""
    try:
        with open("frontend/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Frontend not found")

@app.post("/auth/register")
async def register(
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form(...)
):
    """Register a new user"""
    if get_user(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create new user
    new_user = {
        "id": len(users_db) + 1,
        "email": email,
        "name": name,
        "hashed_password": get_password_hash(password),
        "is_admin": False  # Set to True for first user or handle separately
    }
    users_db.append(new_user)

    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": email}, expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "name": name,
        "email": email,
        "is_admin": new_user["is_admin"]
    }

@app.post("/auth/login")
async def login(email: str = Form(...), password: str = Form(...)):
    """Login user"""
    user = authenticate_user(email, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"]}, expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "name": user["name"],
        "email": user["email"],
        "is_admin": user["is_admin"]
    }

@app.get("/trades")
async def get_trades(current_user: dict = Depends(get_current_user)):
    """Get user trades - protected route"""
    return {"message": "Trades endpoint", "user": current_user["email"]}

@app.get("/admin/dashboard")
async def admin_dashboard(current_user: dict = Depends(get_current_user)):
    """Admin dashboard stats"""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    return {
        "users": {"total_users": len(users_db)},
        "trades": {"total_trades": 0},
        "blog": {"total_posts": 0},  # Update with actual blog post count
        "analyses": {"avg_trader_score": 75.5}
    }

# Blog public routes
@app.get("/posts")
async def get_posts(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=100),
    status: Optional[str] = Query("published"),
    category: Optional[str] = None
):
    """Get blog posts - public endpoint"""
    # This should connect to your actual blog database
    # Returning mock data for now
    return {
        "posts": [],
        "total": 0,
        "page": page,
        "per_page": per_page
    }

@app.get("/posts/{post_id}")
async def get_post(post_id: int):
    """Get single blog post - public endpoint"""
    raise HTTPException(status_code=404, detail="Post not found")

# Upload endpoint for Editor.js
@app.post("/upload")
async def upload_image(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """Upload image for blog posts"""
    # Implement your image upload logic here
    # Return the URL of the uploaded image
    return {
        "success": 1,
        "file": {
            "url": f"/static/uploads/{file.filename}"
        }
    }

@app.post("/upload-url")
async def upload_image_by_url(url: str = Form(...), current_user: dict = Depends(get_current_user)):
    """Upload image by URL for blog posts"""
    return {
        "success": 1,
        "file": {
            "url": url
        }
    }

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "2.0"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
