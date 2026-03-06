"""
Pipways Trading Platform - Main Application
Fixed version that handles missing blog_routes properly
"""

from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
import os
from datetime import datetime
from typing import Optional, List
import json

# Try to import blog routes, create dummy if not available
try:
    from blog_routes import router as blog_router
    BLOG_ROUTES_AVAILABLE = True
except ImportError:
    BLOG_ROUTES_AVAILABLE = False
    print("Warning: blog_routes not found, blog features will be limited")
    # Create a dummy router if blog_routes doesn't exist
    from fastapi import APIRouter
    blog_router = APIRouter()

# Initialize FastAPI app
app = FastAPI(
    title="Pipways Trading Platform",
    description="Trading education platform with blog functionality",
    version="2.0.0"
)

# CORS Configuration - Allow frontend to communicate with backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create static directories if they don't exist
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("static/images", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory storage for demo (replace with database in production)
posts_db = []
users_db = [{"email": "admin@pipways.com", "password": "admin123", "role": "admin"}]

# ============================================================================
# AUTHENTICATION (Simple JWT-like token for demo)
# ============================================================================

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify token and return user"""
    token = credentials.credentials
    # Simple token check - in production use proper JWT
    if token == "demo-token-12345":
        return {"email": "admin@pipways.com", "role": "admin"}
    raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/auth/login")
async def login(email: str = Form(...), password: str = Form(...)):
    """Login endpoint"""
    for user in users_db:
        if user["email"] == email and user["password"] == password:
            return {
                "access_token": "demo-token-12345",
                "token_type": "bearer",
                "user": {"email": user["email"], "role": user["role"]}
            }
    raise HTTPException(status_code=401, detail="Invalid credentials")

# ============================================================================
# BLOG ENDPOINTS (Built-in if blog_routes not available)
# ============================================================================

@app.get("/posts")
async def get_posts():
    """Get all blog posts"""
    return {"posts": posts_db}

@app.get("/posts/{post_id}")
async def get_post(post_id: int):
    """Get single post"""
    for post in posts_db:
        if post["id"] == post_id:
            return post
    raise HTTPException(status_code=404, detail="Post not found")

@app.post("/posts")
async def create_post(
    title: str = Form(...),
    content: str = Form(...),  # JSON string from Editor.js
    excerpt: Optional[str] = Form(None),
    status: str = Form("draft"),
    current_user: dict = Depends(get_current_user)
):
    """Create new blog post"""
    post = {
        "id": len(posts_db) + 1,
        "title": title,
        "content": json.loads(content) if isinstance(content, str) else content,
        "excerpt": excerpt or title[:100],
        "status": status,
        "author": current_user["email"],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    posts_db.append(post)
    return {"success": True, "post": post}

@app.put("/posts/{post_id}")
async def update_post(
    post_id: int,
    title: str = Form(...),
    content: str = Form(...),
    excerpt: Optional[str] = Form(None),
    status: str = Form("draft"),
    current_user: dict = Depends(get_current_user)
):
    """Update blog post"""
    for i, post in enumerate(posts_db):
        if post["id"] == post_id:
            posts_db[i].update({
                "title": title,
                "content": json.loads(content) if isinstance(content, str) else content,
                "excerpt": excerpt or title[:100],
                "status": status,
                "updated_at": datetime.now().isoformat()
            })
            return {"success": True, "post": posts_db[i]}
    raise HTTPException(status_code=404, detail="Post not found")

@app.delete("/posts/{post_id}")
async def delete_post(post_id: int, current_user: dict = Depends(get_current_user)):
    """Delete blog post"""
    global posts_db
    posts_db = [p for p in posts_db if p["id"] != post_id]
    return {"success": True}

# ============================================================================
# MEDIA UPLOAD ENDPOINTS (For Editor.js image handling)
# ============================================================================

@app.post("/media/upload")
async def upload_media(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload image file for Editor.js"""
    try:
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        filepath = f"static/uploads/{filename}"

        # Save file
        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)

        # Return format expected by Editor.js ImageTool
        return {
            "success": 1,
            "file": {
                "url": f"/static/uploads/{filename}",
                "name": filename
            }
        }
    except Exception as e:
        return {"success": 0, "message": str(e)}

@app.post("/media/upload-url")
async def upload_media_by_url(
    url: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload image from URL for Editor.js"""
    import requests
    try:
        # Download image from URL
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_external.jpg"
            filepath = f"static/uploads/{filename}"

            with open(filepath, "wb") as f:
                f.write(response.content)

            return {
                "success": 1,
                "file": {
                    "url": f"/static/uploads/{filename}",
                    "name": filename
                }
            }
        return {"success": 0, "message": "Failed to download image"}
    except Exception as e:
        return {"success": 0, "message": str(e)}

# ============================================================================
# AI & SEO ENDPOINTS
# ============================================================================

@app.post("/ai/generate")
async def ai_generate(
    prompt: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """AI content generation endpoint"""
    # Placeholder - integrate with OpenAI/Claude
    return {
        "content": f"AI generated content based on: {prompt}",
        "suggestions": ["Point 1", "Point 2", "Point 3"]
    }

@app.post("/seo/analyze")
async def seo_analyze(
    content: str = Form(...),
    title: str = Form(...)
):
    """SEO analysis endpoint"""
    # Simple SEO analysis
    word_count = len(content.split())
    return {
        "score": min(100, word_count // 10),
        "word_count": word_count,
        "suggestions": [
            "Add more headings" if "#" not in content else "Good use of headings",
            "Add images" if "image" not in content.lower() else "Good visual content",
            f"Current length: {word_count} words"
        ]
    }

# ============================================================================
# INCLUDE EXTERNAL BLOG ROUTES (if available)
# ============================================================================

if BLOG_ROUTES_AVAILABLE:
    app.include_router(blog_router, prefix="/blog", tags=["blog"])

# ============================================================================
# FRONTEND SERVING
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main SPA"""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head><title>Pipways Platform</title></head>
        <body>
            <h1>Pipways Trading Platform</h1>
            <p>Frontend not found. Please ensure index.html exists.</p>
            <p>API is running at /docs</p>
        </body>
        </html>
        """)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "blog_routes": "loaded" if BLOG_ROUTES_AVAILABLE else "using built-in"
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
