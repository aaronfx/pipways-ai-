"""
Pipways Trading Platform - Complete Blog Integration
All functionality in single file - no external dependencies
"""

from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

# Initialize FastAPI app
app = FastAPI(
    title="Pipways Trading Platform",
    description="Trading education platform with integrated blog",
    version="3.0.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create static directories
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("static/images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory storage
posts_db: List[Dict[str, Any]] = []
users_db = [
    {"email": "admin@pipways.com", "password": "admin123", "role": "admin", "name": "Admin User"},
    {"email": "demo@pipways.com", "password": "demo123", "role": "user", "name": "Demo User"}
]

# ============================================================================
# AUTHENTICATION
# ============================================================================

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify token and return user"""
    token = credentials.credentials
    # Demo tokens
    if token == "admin-token":
        return users_db[0]
    elif token == "user-token":
        return users_db[1]
    elif token.startswith("demo-"):
        return users_db[0]
    raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/api/auth/login")
async def login(credentials: dict):
    """Login endpoint"""
    email = credentials.get("email")
    password = credentials.get("password")

    for user in users_db:
        if user["email"] == email and user["password"] == password:
            return {
                "access_token": f"demo-{user['role']}-token",
                "token_type": "bearer",
                "user": {"email": user["email"], "role": user["role"], "name": user["name"]}
            }
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/api/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user"""
    return {"user": current_user}

# ============================================================================
# BLOG API - ALL FUNCTIONALITY BUILT-IN
# ============================================================================

@app.get("/api/posts")
async def get_all_posts(status: Optional[str] = None, limit: int = 100):
    """Get all blog posts with optional filtering"""
    result = posts_db
    if status:
        result = [p for p in result if p.get("status") == status]
    return {"posts": result[-limit:], "count": len(result)}

@app.get("/api/posts/{post_id}")
async def get_post_by_id(post_id: int):
    """Get single post by ID"""
    for post in posts_db:
        if post.get("id") == post_id:
            return post
    raise HTTPException(status_code=404, detail="Post not found")

@app.post("/api/posts")
async def create_new_post(
    title: str = Form(...),
    content: str = Form(...),
    excerpt: Optional[str] = Form(None),
    status: str = Form("draft"),
    tags: Optional[str] = Form(""),
    featured_image: Optional[str] = Form(None),
    meta_title: Optional[str] = Form(None),
    meta_description: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """Create new blog post"""
    try:
        content_data = json.loads(content) if isinstance(content, str) else content
    except:
        content_data = {"blocks": [{"type": "paragraph", "data": {"text": content}}]}

    post = {
        "id": len(posts_db) + 1,
        "title": title,
        "slug": title.lower().replace(" ", "-").replace("[^a-z0-9-]", "")[:50],
        "content": content_data,
        "excerpt": excerpt or (title[:150] + "..."),
        "status": status,
        "tags": [t.strip() for t in tags.split(",") if t.strip()] if tags else [],
        "featured_image": featured_image,
        "meta_title": meta_title or title,
        "meta_description": meta_description or excerpt or title,
        "author": current_user["email"],
        "author_name": current_user.get("name", current_user["email"]),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "views": 0,
        "likes": 0
    }
    posts_db.append(post)
    return {"success": True, "post": post}

@app.put("/api/posts/{post_id}")
async def update_existing_post(
    post_id: int,
    title: str = Form(...),
    content: str = Form(...),
    excerpt: Optional[str] = Form(None),
    status: str = Form("draft"),
    tags: Optional[str] = Form(""),
    featured_image: Optional[str] = Form(None),
    meta_title: Optional[str] = Form(None),
    meta_description: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """Update existing post"""
    for i, post in enumerate(posts_db):
        if post.get("id") == post_id:
            try:
                content_data = json.loads(content) if isinstance(content, str) else content
            except:
                content_data = post["content"]

            posts_db[i].update({
                "title": title,
                "slug": title.lower().replace(" ", "-").replace("[^a-z0-9-]", "")[:50],
                "content": content_data,
                "excerpt": excerpt or (title[:150] + "..."),
                "status": status,
                "tags": [t.strip() for t in tags.split(",") if t.strip()] if tags else post.get("tags", []),
                "featured_image": featured_image or post.get("featured_image"),
                "meta_title": meta_title or title,
                "meta_description": meta_description or excerpt or title,
                "updated_at": datetime.now().isoformat()
            })
            return {"success": True, "post": posts_db[i]}
    raise HTTPException(status_code=404, detail="Post not found")

@app.delete("/api/posts/{post_id}")
async def delete_post(post_id: int, current_user: dict = Depends(get_current_user)):
    """Delete post"""
    global posts_db
    initial_count = len(posts_db)
    posts_db = [p for p in posts_db if p.get("id") != post_id]
    if len(posts_db) < initial_count:
        return {"success": True, "message": "Post deleted successfully"}
    raise HTTPException(status_code=404, detail="Post not found")

@app.post("/api/posts/{post_id}/publish")
async def publish_post(post_id: int, current_user: dict = Depends(get_current_user)):
    """Publish a draft post"""
    for i, post in enumerate(posts_db):
        if post.get("id") == post_id:
            posts_db[i]["status"] = "published"
            posts_db[i]["published_at"] = datetime.now().isoformat()
            posts_db[i]["updated_at"] = datetime.now().isoformat()
            return {"success": True, "post": posts_db[i]}
    raise HTTPException(status_code=404, detail="Post not found")

@app.post("/api/posts/{post_id}/unpublish")
async def unpublish_post(post_id: int, current_user: dict = Depends(get_current_user)):
    """Unpublish a post (move to draft)"""
    for i, post in enumerate(posts_db):
        if post.get("id") == post_id:
            posts_db[i]["status"] = "draft"
            posts_db[i]["updated_at"] = datetime.now().isoformat()
            return {"success": True, "post": posts_db[i]}
    raise HTTPException(status_code=404, detail="Post not found")

# ============================================================================
# MEDIA UPLOAD (For Editor.js)
# ============================================================================

@app.post("/api/media/upload")
async def upload_media_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload image file for Editor.js"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = "".join(c for c in file.filename if c.isalnum() or c in "._-").rstrip()
        filename = f"{timestamp}_{safe_filename}"
        filepath = f"static/uploads/{filename}"

        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)

        return {
            "success": 1,
            "file": {
                "url": f"/static/uploads/{filename}",
                "name": filename,
                "size": len(content)
            }
        }
    except Exception as e:
        return {"success": 0, "message": str(e)}

@app.post("/api/media/upload-url")
async def upload_media_from_url(
    url: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload image from URL for Editor.js"""
    import requests
    try:
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
                    "name": filename,
                    "size": len(response.content)
                }
            }
        return {"success": 0, "message": "Failed to download image"}
    except Exception as e:
        return {"success": 0, "message": str(e)}

# ============================================================================
# AI & SEO TOOLS
# ============================================================================

@app.post("/api/ai/generate")
async def ai_generate_content(
    prompt: str = Form(...),
    content_type: str = Form("blog"),
    current_user: dict = Depends(get_current_user)
):
    """AI content generation (placeholder - integrate with OpenAI/Claude)"""
    # This is a placeholder - replace with actual AI integration
    suggestions = {
        "introduction": f"Welcome to our comprehensive guide on {prompt}. In this article, we'll explore...",
        "outline": [
            f"Understanding {prompt}",
            f"Key strategies for {prompt}",
            f"Common mistakes to avoid",
            f"Expert tips and recommendations",
            "Conclusion"
        ],
        "content": f"AI generated content about {prompt}...",
        "meta_description": f"Learn everything about {prompt} with our expert guide. Discover strategies, tips, and best practices."
    }
    return {"success": True, "data": suggestions}

@app.post("/api/seo/analyze")
async def analyze_seo(
    content: str = Form(...),
    title: str = Form(...),
    keywords: Optional[str] = Form("")
):
    """SEO analysis for blog post"""
    try:
        content_data = json.loads(content) if isinstance(content, str) else content
        text_content = " ".join([block.get("data", {}).get("text", "") for block in content_data.get("blocks", [])])
    except:
        text_content = content

    word_count = len(text_content.split())
    char_count = len(text_content)

    # Simple SEO scoring
    score = 50
    suggestions = []

    # Length checks
    if word_count < 300:
        suggestions.append("Content is too short. Aim for at least 300 words.")
        score -= 10
    elif word_count > 1000:
        score += 10
        suggestions.append("Good content length for SEO.")

    # Title checks
    if len(title) < 30:
        suggestions.append("Title is too short. Aim for 50-60 characters.")
        score -= 5
    elif len(title) > 60:
        suggestions.append("Title might be truncated in search results.")
    else:
        score += 5
        suggestions.append("Title length is optimal.")

    # Keyword checks
    if keywords:
        keyword_list = [k.strip().lower() for k in keywords.split(",")]
        text_lower = text_content.lower()
        for kw in keyword_list:
            if kw in text_lower:
                score += 5
            else:
                suggestions.append(f"Consider adding keyword: '{kw}'")

    # Heading structure
    has_headings = "#" in text_content or any(block.get("type") == "header" for block in content_data.get("blocks", []))
    if has_headings:
        score += 10
        suggestions.append("Good use of headings structure.")
    else:
        suggestions.append("Add headings (H1, H2, H3) to improve readability.")

    # Image usage
    has_images = any(block.get("type") == "image" for block in content_data.get("blocks", []))
    if has_images:
        score += 5
        suggestions.append("Good use of images.")
    else:
        suggestions.append("Consider adding images to improve engagement.")

    return {
        "score": min(100, max(0, score)),
        "word_count": word_count,
        "char_count": char_count,
        "suggestions": suggestions[:5],
        "readability": "Good" if word_count > 500 else "Fair"
    }

# ============================================================================
# FRONTEND - COMPLETE BLOG INTERFACE
# ============================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pipways - Blog Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/editorjs@2.28.2/dist/editorjs.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/header@2.7.0/dist/bundle.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/paragraph@2.10.0/dist/bundle.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/list@1.8.0/dist/bundle.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/image@2.8.1/dist/bundle.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/quote@2.5.0/dist/bundle.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/code@2.8.0/dist/bundle.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/embed@2.5.3/dist/bundle.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/delimiter@1.3.0/dist/bundle.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/table@2.2.1/dist/bundle.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@editorjs/marker@1.3.0/dist/bundle.umd.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background: #0f172a; color: #e2e8f0; }
        .ce-block__content, .ce-toolbar__content { max-width: 900px; }
        .codex-editor__redactor { padding-bottom: 100px !important; }
        .ce-toolbar__plus, .ce-toolbar__settings-btn { color: #64748b; background: #1e293b; border-radius: 4px; }
        .ce-toolbar__plus:hover, .ce-toolbar__settings-btn:hover { color: #e2e8f0; background: #334155; }
        .ce-toolbox__button { color: #64748b; }
        .ce-toolbox__button:hover { color: #e2e8f0; background: #334155; }
        .cdx-search-field__input { background: #1e293b; color: #e2e8f0; border-color: #334155; }
        .ce-popover__container { background: #1e293b; border-color: #334155; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5); }
        .ce-popover-item { color: #e2e8f0; }
        .ce-popover-item:hover { background: #334155; }
        .ce-inline-tool { color: #64748b; }
        .ce-inline-tool:hover { color: #e2e8f0; background: #334155; }
        .ce-conversion-tool__icon { color: #64748b; }
        .ce-block--selected .ce-block__content { background: #1e293b; }
        .cdx-block { padding: 0.5rem 0; }
        .ce-header { color: #f8fafc; font-weight: 700; }
        .cdx-list { padding-left: 1.5rem; }
        .cdx-quote { border-left: 3px solid #3b82f6; padding-left: 1rem; font-style: italic; color: #94a3b8; }
        .cdx-marker { background: rgba(59, 130, 246, 0.3); padding: 0 2px; }
        .image-tool__image { border-radius: 8px; overflow: hidden; }
        .image-tool__caption { color: #64748b; font-size: 0.875rem; }
        .cdx-input { background: #1e293b; border-color: #334155; color: #e2e8f0; }
        .cdx-input:focus { border-color: #3b82f6; }
        .tc-wrap { border-color: #334155; }
        .tc-cell { border-color: #334155; background: #1e293b; }
        .tc-row::after { background: #334155; }
        .tc-add-column, .tc-add-row { background: #334155; color: #64748b; }
        .tc-add-column:hover, .tc-add-row:hover { background: #475569; color: #e2e8f0; }
        .ce-code__textarea { background: #1e293b; color: #e2e8f0; font-family: 'Monaco', 'Menlo', monospace; }
        .ce-delimiter { color: #475569; }
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #475569; }
        .fade-in { animation: fadeIn 0.3s ease-in; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .slide-in { animation: slideIn 0.3s ease-out; }
        @keyframes slideIn { from { transform: translateX(-100%); } to { transform: translateX(0); } }
    </style>
</head>
<body class="min-h-screen bg-slate-900">
    <div id="app">
        <!-- Login Screen -->
        <div id="loginScreen" class="min-h-screen flex items-center justify-center p-4">
            <div class="bg-slate-800 rounded-2xl p-8 w-full max-w-md shadow-2xl">
                <div class="text-center mb-8">
                    <div class="w-16 h-16 bg-blue-600 rounded-xl flex items-center justify-center mx-auto mb-4">
                        <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                    </div>
                    <h1 class="text-2xl font-bold text-white mb-2">Pipways Blog</h1>
                    <p class="text-slate-400">Sign in to manage your content</p>
                </div>
                <form id="loginForm" class="space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-slate-300 mb-2">Email</label>
                        <input type="email" id="loginEmail" value="admin@pipways.com" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition" placeholder="admin@pipways.com">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-slate-300 mb-2">Password</label>
                        <input type="password" id="loginPassword" value="admin123" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition" placeholder="••••••••">
                    </div>
                    <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-lg transition duration-200 flex items-center justify-center gap-2">
                        <span>Sign In</span>
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6"></path></svg>
                    </button>
                </form>
                <div class="mt-6 text-center">
                    <p class="text-sm text-slate-500">Demo: admin@pipways.com / admin123</p>
                </div>
            </div>
        </div>

        <!-- Main App (Hidden until login) -->
        <div id="mainApp" class="hidden">
            <!-- Header -->
            <header class="bg-slate-800 border-b border-slate-700 sticky top-0 z-50">
                <div class="container mx-auto px-4 py-4">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-4">
                            <div class="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                                <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                            </div>
                            <div>
                                <h1 class="text-xl font-bold text-white">Pipways Blog</h1>
                                <p class="text-xs text-slate-400">Content Management</p>
                            </div>
                        </div>
                        <div class="flex items-center gap-3">
                            <button onclick="createNewPost()" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition flex items-center gap-2">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                                <span class="hidden sm:inline">New Post</span>
                            </button>
                            <button onclick="logout()" class="bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded-lg font-medium transition">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
                            </button>
                        </div>
                    </div>
                </div>
            </header>

            <!-- Main Content -->
            <main class="container mx-auto px-4 py-6">
                <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
                    <!-- Sidebar - Posts List -->
                    <div class="lg:col-span-1">
                        <div class="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
                            <div class="p-4 border-b border-slate-700 bg-slate-800/50">
                                <div class="flex items-center justify-between">
                                    <h2 class="font-semibold text-white">Posts</h2>
                                    <span id="postCount" class="bg-slate-700 text-slate-300 text-xs px-2 py-1 rounded-full">0</span>
                                </div>
                            </div>
                            <div class="p-2">
                                <div class="flex gap-2 mb-3">
                                    <button onclick="filterPosts('all')" class="filter-btn flex-1 py-1.5 px-3 rounded-lg text-xs font-medium bg-blue-600 text-white transition" data-filter="all">All</button>
                                    <button onclick="filterPosts('published')" class="filter-btn flex-1 py-1.5 px-3 rounded-lg text-xs font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition" data-filter="published">Live</button>
                                    <button onclick="filterPosts('draft')" class="filter-btn flex-1 py-1.5 px-3 rounded-lg text-xs font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition" data-filter="draft">Draft</button>
                                </div>
                                <div id="postsList" class="space-y-2 max-h-[calc(100vh-300px)] overflow-y-auto">
                                    <div class="text-center py-8 text-slate-500">
                                        <svg class="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                                        <p class="text-sm">No posts yet</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Editor Area -->
                    <div class="lg:col-span-3">
                        <!-- Empty State -->
                        <div id="emptyState" class="bg-slate-800 rounded-xl border border-slate-700 p-12 text-center">
                            <div class="w-20 h-20 bg-slate-700 rounded-full flex items-center justify-center mx-auto mb-4">
                                <svg class="w-10 h-10 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                            </div>
                            <h3 class="text-xl font-semibold text-white mb-2">Create Your First Post</h3>
                            <p class="text-slate-400 mb-6 max-w-md mx-auto">Start writing amazing content for your trading blog. Click the button below to begin.</p>
                            <button onclick="createNewPost()" class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium transition inline-flex items-center gap-2">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                                Create New Post
                            </button>
                        </div>

                        <!-- Editor Form -->
                        <div id="editorContainer" class="hidden bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
                            <!-- Editor Header -->
                            <div class="p-6 border-b border-slate-700 bg-slate-800/50">
                                <div class="flex items-center justify-between mb-4">
                                    <div class="flex items-center gap-2">
                                        <span id="editorMode" class="bg-blue-600 text-white text-xs px-2 py-1 rounded font-medium">NEW POST</span>
                                        <span id="lastSaved" class="text-slate-500 text-sm hidden">Last saved: Just now</span>
                                    </div>
                                    <div class="flex items-center gap-2">
                                        <button onclick="openSEOPanel()" class="bg-slate-700 hover:bg-slate-600 text-slate-300 px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center gap-2">
                                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
                                            SEO
                                        </button>
                                        <button onclick="openAIPanel()" class="bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center gap-2">
                                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                                            AI Assist
                                        </button>
                                    </div>
                                </div>
                                <input type="text" id="postTitle" placeholder="Enter post title..." class="w-full bg-transparent text-3xl font-bold text-white placeholder-slate-500 border-none focus:outline-none focus:ring-0">
                            </div>

                            <!-- Editor Content -->
                            <div class="p-6">
                                <div id="editorjs" class="min-h-[500px]"></div>
                            </div>

                            <!-- Editor Footer -->
                            <div class="p-6 border-t border-slate-700 bg-slate-800/50">
                                <div class="flex flex-wrap items-center justify-between gap-4">
                                    <div class="flex items-center gap-3">
                                        <select id="postStatus" class="bg-slate-900 border border-slate-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500">
                                            <option value="draft">Draft</option>
                                            <option value="published">Published</option>
                                        </select>
                                        <input type="text" id="postTags" placeholder="Tags (comma separated)" class="bg-slate-900 border border-slate-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500 hidden sm:block">
                                    </div>
                                    <div class="flex items-center gap-3">
                                        <button onclick="cancelEdit()" class="bg-slate-700 hover:bg-slate-600 text-white px-6 py-2 rounded-lg font-medium transition">Cancel</button>
                                        <button onclick="savePost()" class="bg-green-600 hover:bg-green-700 text-white px-6 py-2 rounded-lg font-medium transition flex items-center gap-2">
                                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                                            Save Post
                                        </button>
                                        <button onclick="deleteCurrentPost()" id="deleteBtn" class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg font-medium transition hidden">
                                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    </div>

    <!-- SEO Panel Modal -->
    <div id="seoPanel" class="hidden fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
        <div class="bg-slate-800 rounded-2xl border border-slate-700 w-full max-w-lg max-h-[90vh] overflow-hidden">
            <div class="p-6 border-b border-slate-700 flex items-center justify-between">
                <h3 class="text-lg font-semibold text-white">SEO Analysis</h3>
                <button onclick="closeSEOPanel()" class="text-slate-400 hover:text-white transition">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>
            <div class="p-6 overflow-y-auto">
                <div id="seoScore" class="text-center mb-6">
                    <div class="text-5xl font-bold text-blue-500 mb-2">--</div>
                    <p class="text-slate-400">SEO Score</p>
                </div>
                <div id="seoSuggestions" class="space-y-3">
                    <p class="text-slate-500 text-center">Click "Analyze" to check SEO</p>
                </div>
            </div>
            <div class="p-6 border-t border-slate-700 bg-slate-800/50">
                <button onclick="runSEOAnalysis()" class="w-full bg-blue-600 hover:bg-blue-700 text-white py-3 rounded-lg font-medium transition">Analyze Content</button>
            </div>
        </div>
    </div>

    <!-- AI Panel Modal -->
    <div id="aiPanel" class="hidden fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
        <div class="bg-slate-800 rounded-2xl border border-slate-700 w-full max-w-2xl max-h-[90vh] overflow-hidden">
            <div class="p-6 border-b border-slate-700 flex items-center justify-between">
                <h3 class="text-lg font-semibold text-white">AI Content Assistant</h3>
                <button onclick="closeAIPanel()" class="text-slate-400 hover:text-white transition">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>
            <div class="p-6 overflow-y-auto">
                <div class="space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-slate-300 mb-2">What would you like help with?</label>
                        <textarea id="aiPrompt" rows="3" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-purple-500" placeholder="e.g., Write an introduction about forex trading strategies..."></textarea>
                    </div>
                    <div class="flex gap-2">
                        <button onclick="generateWithAI('outline')" class="flex-1 bg-slate-700 hover:bg-slate-600 text-white py-2 rounded-lg text-sm font-medium transition">Generate Outline</button>
                        <button onclick="generateWithAI('introduction')" class="flex-1 bg-slate-700 hover:bg-slate-600 text-white py-2 rounded-lg text-sm font-medium transition">Introduction</button>
                        <button onclick="generateWithAI('content')" class="flex-1 bg-purple-600 hover:bg-purple-700 text-white py-2 rounded-lg text-sm font-medium transition">Full Content</button>
                    </div>
                    <div id="aiResult" class="hidden">
                        <label class="block text-sm font-medium text-slate-300 mb-2">Generated Content</label>
                        <div class="bg-slate-900 border border-slate-700 rounded-lg p-4 max-h-60 overflow-y-auto">
                            <pre id="aiResultText" class="text-sm text-slate-300 whitespace-pre-wrap font-sans"></pre>
                        </div>
                        <button onclick="insertAIContent()" class="mt-3 w-full bg-green-600 hover:bg-green-700 text-white py-2 rounded-lg text-sm font-medium transition">Insert into Editor</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Toast Notifications -->
    <div id="toastContainer" class="fixed bottom-4 right-4 z-50 space-y-2"></div>

    <script>
        // Configuration
        const API_BASE = window.location.origin;
        let authToken = localStorage.getItem('pipways_token') || '';
        let currentUser = JSON.parse(localStorage.getItem('pipways_user') || 'null');
        let editor = null;
        let currentPostId = null;
        let posts = [];
        let currentFilter = 'all';
        let aiGeneratedContent = '';

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            if (authToken && currentUser) {
                showMainApp();
                loadPosts();
            } else {
                showLoginScreen();
            }

            // Login form handler
            document.getElementById('loginForm').addEventListener('submit', handleLogin);
        });

        // Auth Functions
        async function handleLogin(e) {
            e.preventDefault();
            const email = document.getElementById('loginEmail').value;
            const password = document.getElementById('loginPassword').value;

            try {
                const response = await fetch(`${API_BASE}/api/auth/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password })
                });

                if (response.ok) {
                    const data = await response.json();
                    authToken = data.access_token;
                    currentUser = data.user;
                    localStorage.setItem('pipways_token', authToken);
                    localStorage.setItem('pipways_user', JSON.stringify(currentUser));
                    showMainApp();
                    loadPosts();
                    showToast('Welcome back!', 'success');
                } else {
                    showToast('Invalid credentials', 'error');
                }
            } catch (error) {
                showToast('Login failed', 'error');
            }
        }

        function logout() {
            authToken = '';
            currentUser = null;
            localStorage.removeItem('pipways_token');
            localStorage.removeItem('pipways_user');
            showLoginScreen();
            showToast('Logged out successfully', 'success');
        }

        function showLoginScreen() {
            document.getElementById('loginScreen').classList.remove('hidden');
            document.getElementById('mainApp').classList.add('hidden');
        }

        function showMainApp() {
            document.getElementById('loginScreen').classList.add('hidden');
            document.getElementById('mainApp').classList.remove('hidden');
        }

        // Posts Management
        async function loadPosts() {
            try {
                const response = await fetch(`${API_BASE}/api/posts`, {
                    headers: { 'Authorization': `Bearer ${authToken}` }
                });
                const data = await response.json();
                posts = data.posts || [];
                renderPostsList();
            } catch (error) {
                showToast('Failed to load posts', 'error');
            }
        }

        function renderPostsList() {
            const container = document.getElementById('postsList');
            const filteredPosts = currentFilter === 'all' 
                ? posts 
                : posts.filter(p => p.status === currentFilter);

            document.getElementById('postCount').textContent = filteredPosts.length;

            if (filteredPosts.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8 text-slate-500">
                        <svg class="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                        <p class="text-sm">No ${currentFilter} posts</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = filteredPosts.map(post => `
                <div onclick="editPost(${post.id})" class="group p-3 rounded-lg cursor-pointer transition ${currentPostId === post.id ? 'bg-blue-600/20 border border-blue-600/50' : 'hover:bg-slate-700/50 border border-transparent'}">
                    <div class="flex items-start justify-between mb-1">
                        <h3 class="font-medium text-white text-sm line-clamp-2 flex-1 ${currentPostId === post.id ? 'text-blue-400' : 'group-hover:text-blue-400'}">${escapeHtml(post.title)}</h3>
                        ${post.status === 'published' 
                            ? '<span class="w-2 h-2 bg-green-500 rounded-full ml-2 flex-shrink-0" title="Published"></span>' 
                            : '<span class="w-2 h-2 bg-yellow-500 rounded-full ml-2 flex-shrink-0" title="Draft"></span>'}
                    </div>
                    <p class="text-xs text-slate-500">${new Date(post.created_at).toLocaleDateString()}</p>
                </div>
            `).join('');
        }

        function filterPosts(filter) {
            currentFilter = filter;
            document.querySelectorAll('.filter-btn').forEach(btn => {
                if (btn.dataset.filter === filter) {
                    btn.classList.remove('bg-slate-700', 'text-slate-300');
                    btn.classList.add('bg-blue-600', 'text-white');
                } else {
                    btn.classList.remove('bg-blue-600', 'text-white');
                    btn.classList.add('bg-slate-700', 'text-slate-300');
                }
            });
            renderPostsList();
        }

        // Editor Functions
        function createNewPost() {
            currentPostId = null;
            document.getElementById('postTitle').value = '';
            document.getElementById('postStatus').value = 'draft';
            document.getElementById('postTags').value = '';
            document.getElementById('editorMode').textContent = 'NEW POST';
            document.getElementById('deleteBtn').classList.add('hidden');
            document.getElementById('lastSaved').classList.add('hidden');

            document.getElementById('emptyState').classList.add('hidden');
            document.getElementById('editorContainer').classList.remove('hidden');
            document.getElementById('editorContainer').classList.add('fade-in');

            initEditor();
        }

        function editPost(id) {
            const post = posts.find(p => p.id === id);
            if (!post) return;

            currentPostId = id;
            document.getElementById('postTitle').value = post.title;
            document.getElementById('postStatus').value = post.status || 'draft';
            document.getElementById('postTags').value = (post.tags || []).join(', ');
            document.getElementById('editorMode').textContent = 'EDITING';
            document.getElementById('deleteBtn').classList.remove('hidden');
            document.getElementById('lastSaved').textContent = 'Last saved: ' + new Date(post.updated_at).toLocaleString();
            document.getElementById('lastSaved').classList.remove('hidden');

            document.getElementById('emptyState').classList.add('hidden');
            document.getElementById('editorContainer').classList.remove('hidden');
            document.getElementById('editorContainer').classList.add('fade-in');

            initEditor(post.content);
            renderPostsList(); // Highlight active post
        }

        function initEditor(data = null) {
            if (editor && typeof editor.destroy === 'function') {
                editor.destroy();
            }

            const holder = document.getElementById('editorjs');
            holder.innerHTML = '';

            editor = new EditorJS({
                holder: 'editorjs',
                data: data,
                tools: {
                    header: {
                        class: Header,
                        config: { levels: [1, 2, 3, 4, 5, 6], defaultLevel: 2 }
                    },
                    paragraph: { class: Paragraph, inlineToolbar: true },
                    list: { class: List, inlineToolbar: true },
                    image: {
                        class: ImageTool,
                        config: {
                            endpoints: {
                                byFile: `${API_BASE}/api/media/upload`,
                                byUrl: `${API_BASE}/api/media/upload-url`
                            },
                            additionalRequestHeaders: { 'Authorization': `Bearer ${authToken}` }
                        }
                    },
                    quote: { class: Quote, inlineToolbar: true },
                    code: CodeTool,
                    embed: {
                        class: Embed,
                        config: { services: { youtube: true, vimeo: true, twitter: true } }
                    },
                    delimiter: Delimiter,
                    table: { class: Table, inlineToolbar: true },
                    marker: Marker
                },
                placeholder: 'Start writing your amazing content here...',
                autofocus: true,
                onReady: () => {
                    console.log('Editor.js is ready!');
                },
                onError: (error) => {
                    console.error('Editor error:', error);
                    showToast('Editor error occurred', 'error');
                }
            });
        }

        async function savePost() {
            const title = document.getElementById('postTitle').value.trim();
            if (!title) {
                showToast('Please enter a title', 'error');
                document.getElementById('postTitle').focus();
                return;
            }

            try {
                const outputData = await editor.save();
                const status = document.getElementById('postStatus').value;
                const tags = document.getElementById('postTags').value;

                const formData = new FormData();
                formData.append('title', title);
                formData.append('content', JSON.stringify(outputData));
                formData.append('status', status);
                formData.append('tags', tags);

                const url = currentPostId ? `${API_BASE}/api/posts/${currentPostId}` : `${API_BASE}/api/posts`;
                const method = currentPostId ? 'PUT' : 'POST';

                const response = await fetch(url, {
                    method: method,
                    headers: { 'Authorization': `Bearer ${authToken}` },
                    body: formData
                });

                if (response.ok) {
                    const result = await response.json();
                    showToast(currentPostId ? 'Post updated!' : 'Post created!', 'success');
                    await loadPosts();
                    if (!currentPostId && result.post) {
                        editPost(result.post.id);
                    } else {
                        document.getElementById('lastSaved').textContent = 'Last saved: Just now';
                        document.getElementById('lastSaved').classList.remove('hidden');
                    }
                } else {
                    throw new Error('Save failed');
                }
            } catch (error) {
                console.error('Save error:', error);
                showToast('Error saving post', 'error');
            }
        }

        async function deleteCurrentPost() {
            if (!currentPostId) return;
            if (!confirm('Are you sure you want to delete this post? This cannot be undone.')) return;

            try {
                const response = await fetch(`${API_BASE}/api/posts/${currentPostId}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${authToken}` }
                });

                if (response.ok) {
                    showToast('Post deleted', 'success');
                    await loadPosts();
                    cancelEdit();
                } else {
                    throw new Error('Delete failed');
                }
            } catch (error) {
                showToast('Error deleting post', 'error');
            }
        }

        function cancelEdit() {
            document.getElementById('editorContainer').classList.add('hidden');
            document.getElementById('emptyState').classList.remove('hidden');
            currentPostId = null;
            if (editor && typeof editor.destroy === 'function') {
                editor.destroy();
                editor = null;
            }
            renderPostsList();
        }

        // SEO Panel
        function openSEOPanel() {
            document.getElementById('seoPanel').classList.remove('hidden');
        }

        function closeSEOPanel() {
            document.getElementById('seoPanel').classList.add('hidden');
        }

        async function runSEOAnalysis() {
            const title = document.getElementById('postTitle').value;
            if (!title) {
                showToast('Please enter a title first', 'error');
                return;
            }

            try {
                const outputData = await editor.save();
                const content = JSON.stringify(outputData);

                const formData = new FormData();
                formData.append('title', title);
                formData.append('content', content);
                formData.append('keywords', document.getElementById('postTags').value);

                const response = await fetch(`${API_BASE}/api/seo/analyze`, {
                    method: 'POST',
                    body: formData
                });

                if (response.ok) {
                    const result = await response.json();
                    document.getElementById('seoScore').innerHTML = `
                        <div class="text-5xl font-bold ${result.score >= 70 ? 'text-green-500' : result.score >= 50 ? 'text-yellow-500' : 'text-red-500'} mb-2">${result.score}</div>
                        <p class="text-slate-400">SEO Score</p>
                        <p class="text-sm text-slate-500 mt-1">${result.word_count} words • ${result.readability} readability</p>
                    `;

                    document.getElementById('seoSuggestions').innerHTML = result.suggestions.map(s => `
                        <div class="flex items-start gap-3 p-3 bg-slate-900 rounded-lg">
                            <svg class="w-5 h-5 ${s.includes('Good') || s.includes('optimal') ? 'text-green-500' : 'text-yellow-500'} flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${s.includes('Good') || s.includes('optimal') ? 'M5 13l4 4L19 7' : 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z'}"></path></svg>
                            <span class="text-sm text-slate-300">${s}</span>
                        </div>
                    `).join('');
                }
            } catch (error) {
                showToast('SEO analysis failed', 'error');
            }
        }

        // AI Panel
        function openAIPanel() {
            document.getElementById('aiPanel').classList.remove('hidden');
        }

        function closeAIPanel() {
            document.getElementById('aiPanel').classList.add('hidden');
            document.getElementById('aiResult').classList.add('hidden');
            document.getElementById('aiPrompt').value = '';
        }

        async function generateWithAI(type) {
            const prompt = document.getElementById('aiPrompt').value;
            if (!prompt) {
                showToast('Please enter a prompt', 'error');
                return;
            }

            try {
                const formData = new FormData();
                formData.append('prompt', prompt);
                formData.append('content_type', type);

                const response = await fetch(`${API_BASE}/api/ai/generate`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${authToken}` },
                    body: formData
                });

                if (response.ok) {
                    const result = await response.json();
                    aiGeneratedContent = result.data.content || JSON.stringify(result.data, null, 2);

                    document.getElementById('aiResultText').textContent = aiGeneratedContent;
                    document.getElementById('aiResult').classList.remove('hidden');
                }
            } catch (error) {
                showToast('AI generation failed', 'error');
            }
        }

        async function insertAIContent() {
            if (!aiGeneratedContent || !editor) return;

            try {
                await editor.blocks.insert('paragraph', { text: aiGeneratedContent });
                closeAIPanel();
                showToast('Content inserted', 'success');
            } catch (error) {
                showToast('Failed to insert content', 'error');
            }
        }

        // Utility Functions
        function showToast(message, type = 'info') {
            const container = document.getElementById('toastContainer');
            const toast = document.createElement('div');
            const colors = type === 'success' ? 'bg-green-600' : type === 'error' ? 'bg-red-600' : 'bg-blue-600';
            const icon = type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ';

            toast.className = `${colors} text-white px-6 py-3 rounded-lg shadow-lg flex items-center gap-3 transform translate-x-full transition-transform duration-300`;
            toast.innerHTML = `<span class="font-bold">${icon}</span><span>${message}</span>`;

            container.appendChild(toast);

            setTimeout(() => toast.classList.remove('translate-x-full'), 100);
            setTimeout(() => {
                toast.classList.add('translate-x-full');
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Close modals on backdrop click
        document.getElementById('seoPanel').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) closeSEOPanel();
        });
        document.getElementById('aiPanel').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) closeAIPanel();
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                e.preventDefault();
                if (!document.getElementById('editorContainer').classList.contains('hidden')) {
                    savePost();
                }
            }
        });
    </script>
</body>
</html>
"""

# Serve the complete HTML interface for ALL routes
@app.get("/")
@app.get("/blog")
@app.get("/admin")
@app.get("/admin/blog")
@app.get("/editor")
async def serve_blog_interface():
    """Serve the complete blog admin interface"""
    return HTMLResponse(content=HTML_TEMPLATE)

# API Documentation endpoint
@app.get("/api")
async def api_info():
    """API information"""
    return {
        "name": "Pipways Blog API",
        "version": "3.0.0",
        "endpoints": {
            "auth": {
                "login": "POST /api/auth/login",
                "me": "GET /api/auth/me"
            },
            "posts": {
                "list": "GET /api/posts",
                "get": "GET /api/posts/{id}",
                "create": "POST /api/posts",
                "update": "PUT /api/posts/{id}",
                "delete": "DELETE /api/posts/{id}",
                "publish": "POST /api/posts/{id}/publish",
                "unpublish": "POST /api/posts/{id}/unpublish"
            },
            "media": {
                "upload": "POST /api/media/upload",
                "upload_url": "POST /api/media/upload-url"
            },
            "tools": {
                "ai_generate": "POST /api/ai/generate",
                "seo_analyze": "POST /api/seo/analyze"
            }
        }
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "posts_count": len(posts_db),
        "version": "3.0.0"
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
