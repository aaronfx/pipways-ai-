"""
Pipways Trading Platform - Main Application
With proper frontend integration for Blog
"""

from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import uvicorn
import os
from datetime import datetime
from typing import Optional, List
import json

# Initialize FastAPI app
app = FastAPI(
    title="Pipways Trading Platform",
    description="Trading education platform with blog functionality",
    version="2.0.0"
)

# CORS Configuration - CRITICAL for frontend-backend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pipways-web-nhem.onrender.com",
        "http://localhost:3000",
        "http://localhost:8000",
        "*"  # Remove in production and specify exact origins
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create static directories
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("static/images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Storage
posts_db = []
users_db = [{"email": "admin@pipways.com", "password": "admin123", "role": "admin"}]

# ============================================================================
# AUTHENTICATION
# ============================================================================

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if token == "demo-token-12345":
        return {"email": "admin@pipways.com", "role": "admin"}
    raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/auth/login")
async def login(email: str = Form(...), password: str = Form(...)):
    for user in users_db:
        if user["email"] == email and user["password"] == password:
            return {
                "access_token": "demo-token-12345",
                "token_type": "bearer",
                "user": {"email": user["email"], "role": user["role"]}
            }
    raise HTTPException(status_code=401, detail="Invalid credentials")

# ============================================================================
# BLOG API ENDPOINTS
# ============================================================================

@app.get("/api/posts")
async def get_posts():
    """Get all blog posts"""
    return {"posts": posts_db}

@app.get("/api/posts/{post_id}")
async def get_post(post_id: int):
    """Get single post"""
    for post in posts_db:
        if post["id"] == post_id:
            return post
    raise HTTPException(status_code=404, detail="Post not found")

@app.post("/api/posts")
async def create_post(
    title: str = Form(...),
    content: str = Form(...),
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

@app.put("/api/posts/{post_id}")
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

@app.delete("/api/posts/{post_id}")
async def delete_post(post_id: int, current_user: dict = Depends(get_current_user)):
    """Delete blog post"""
    global posts_db
    posts_db = [p for p in posts_db if p["id"] != post_id]
    return {"success": True}

# ============================================================================
# MEDIA UPLOAD (For Editor.js)
# ============================================================================

@app.post("/api/media/upload")
async def upload_media(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """Upload image file for Editor.js"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        filepath = f"static/uploads/{filename}"

        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)

        return {
            "success": 1,
            "file": {"url": f"/static/uploads/{filename}", "name": filename}
        }
    except Exception as e:
        return {"success": 0, "message": str(e)}

@app.post("/api/media/upload-url")
async def upload_media_by_url(url: str = Form(...), current_user: dict = Depends(get_current_user)):
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
                "file": {"url": f"/static/uploads/{filename}", "name": filename}
            }
        return {"success": 0, "message": "Failed to download image"}
    except Exception as e:
        return {"success": 0, "message": str(e)}

# ============================================================================
# AI & SEO
# ============================================================================

@app.post("/api/ai/generate")
async def ai_generate(prompt: str = Form(...), current_user: dict = Depends(get_current_user)):
    """AI content generation"""
    return {"content": f"AI generated: {prompt}", "suggestions": ["Point 1", "Point 2"]}

@app.post("/api/seo/analyze")
async def seo_analyze(content: str = Form(...), title: str = Form(...)):
    """SEO analysis"""
    word_count = len(content.split())
    return {
        "score": min(100, word_count // 10),
        "word_count": word_count,
        "suggestions": ["Add headings", "Add images", f"Length: {word_count} words"]
    }

# ============================================================================
# FRONTEND SERVING - CRITICAL FOR SPA ROUTES
# ============================================================================

# Serve index.html for all routes (SPA behavior)
@app.get("/", response_class=HTMLResponse)
@app.get("/blog")
@app.get("/admin/blog")
@app.get("/admin")
@app.get("/dashboard")
@app.get("/trade-journal")
@app.get("/chart-analysis")
async def serve_spa():
    """Serve the main SPA for all frontend routes"""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        # Return a basic HTML that loads the blog functionality
        return HTMLResponse(content=generate_fallback_html())

def generate_fallback_html():
    """Generate fallback HTML if index.html not found"""
    return """
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
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Inter', sans-serif; background: #0f172a; color: #e2e8f0; }
            .ce-block__content, .ce-toolbar__content { max-width: 900px; }
            .codex-editor__redactor { padding-bottom: 100px !important; }
            .ce-toolbar__plus, .ce-toolbar__settings-btn { color: #64748b; }
            .ce-toolbox__button { color: #64748b; }
            .cdx-search-field__input { background: #1e293b; color: #e2e8f0; }
            .ce-popover__container { background: #1e293b; border-color: #334155; }
            .ce-inline-tool { color: #64748b; }
            .ce-conversion-tool__icon { color: #64748b; }
        </style>
    </head>
    <body class="min-h-screen bg-slate-900">
        <div id="app" class="container mx-auto px-4 py-8">
            <header class="mb-8">
                <h1 class="text-3xl font-bold text-white mb-2">Pipways Blog Admin</h1>
                <p class="text-slate-400">Create and manage your trading blog posts</p>
            </header>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <!-- Posts List -->
                <div class="lg:col-span-1 bg-slate-800 rounded-lg p-4">
                    <div class="flex justify-between items-center mb-4">
                        <h2 class="text-xl font-semibold">Posts</h2>
                        <button onclick="createNewPost()" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm font-medium transition">
                            + New Post
                        </button>
                    </div>
                    <div id="postsList" class="space-y-2 max-h-96 overflow-y-auto">
                        <p class="text-slate-500 text-sm">Loading posts...</p>
                    </div>
                </div>

                <!-- Editor -->
                <div class="lg:col-span-2 bg-slate-800 rounded-lg p-6">
                    <div id="editorForm" class="hidden">
                        <input type="text" id="postTitle" placeholder="Post Title" 
                            class="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-xl font-bold mb-4 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500">

                        <div id="editorjs" class="bg-slate-900 rounded-lg min-h-[400px] p-4"></div>

                        <div class="flex gap-3 mt-4">
                            <button onclick="savePost()" class="bg-green-600 hover:bg-green-700 px-6 py-2 rounded-lg font-medium transition">
                                Save Post
                            </button>
                            <button onclick="cancelEdit()" class="bg-slate-700 hover:bg-slate-600 px-6 py-2 rounded-lg font-medium transition">
                                Cancel
                            </button>
                            <button onclick="deleteCurrentPost()" id="deleteBtn" class="bg-red-600 hover:bg-red-700 px-6 py-2 rounded-lg font-medium transition hidden">
                                Delete
                            </button>
                        </div>
                    </div>

                    <div id="emptyState" class="text-center py-12">
                        <p class="text-slate-500 mb-4">Select a post to edit or create a new one</p>
                        <button onclick="createNewPost()" class="bg-blue-600 hover:bg-blue-700 px-6 py-3 rounded-lg font-medium transition">
                            Create New Post
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <script>
            const API_BASE = window.location.origin.includes('localhost') ? 'http://localhost:8000' : window.location.origin;
            let editor = null;
            let currentPostId = null;
            let posts = [];

            // Initialize
            document.addEventListener('DOMContentLoaded', () => {
                loadPosts();
            });

            async function loadPosts() {
                try {
                    const response = await fetch(`${API_BASE}/api/posts`);
                    const data = await response.json();
                    posts = data.posts || [];
                    renderPostsList();
                } catch (error) {
                    console.error('Error loading posts:', error);
                    document.getElementById('postsList').innerHTML = '<p class="text-red-400 text-sm">Failed to load posts</p>';
                }
            }

            function renderPostsList() {
                const container = document.getElementById('postsList');
                if (posts.length === 0) {
                    container.innerHTML = '<p class="text-slate-500 text-sm">No posts yet</p>';
                    return;
                }

                container.innerHTML = posts.map(post => `
                    <div onclick="editPost(${post.id})" class="p-3 bg-slate-700 rounded-lg cursor-pointer hover:bg-slate-600 transition group">
                        <h3 class="font-medium text-white group-hover:text-blue-400 transition">${post.title}</h3>
                        <p class="text-xs text-slate-400 mt-1">${new Date(post.created_at).toLocaleDateString()}</p>
                        <span class="inline-block mt-2 px-2 py-1 text-xs rounded ${post.status === 'published' ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'}">${post.status}</span>
                    </div>
                `).join('');
            }

            function createNewPost() {
                currentPostId = null;
                document.getElementById('postTitle').value = '';
                document.getElementById('emptyState').classList.add('hidden');
                document.getElementById('editorForm').classList.remove('hidden');
                document.getElementById('deleteBtn').classList.add('hidden');

                initEditor();
            }

            function editPost(id) {
                const post = posts.find(p => p.id === id);
                if (!post) return;

                currentPostId = id;
                document.getElementById('postTitle').value = post.title;
                document.getElementById('emptyState').classList.add('hidden');
                document.getElementById('editorForm').classList.remove('hidden');
                document.getElementById('deleteBtn').classList.remove('hidden');

                initEditor(post.content);
            }

            function initEditor(data = {}) {
                if (editor && typeof editor.destroy === 'function') {
                    editor.destroy();
                }

                editor = new EditorJS({
                    holder: 'editorjs',
                    data: Object.keys(data).length > 0 ? data : undefined,
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
                                additionalRequestHeaders: {
                                    'Authorization': 'Bearer demo-token-12345'
                                }
                            }
                        },
                        quote: { class: Quote, inlineToolbar: true },
                        code: CodeTool,
                        embed: {
                            class: Embed,
                            config: { services: { youtube: true, vimeo: true } }
                        },
                        delimiter: Delimiter,
                        table: { class: Table, inlineToolbar: true }
                    },
                    placeholder: 'Start writing your post...'
                });
            }

            async function savePost() {
                const title = document.getElementById('postTitle').value;
                if (!title) {
                    alert('Please enter a title');
                    return;
                }

                try {
                    const outputData = await editor.save();

                    const formData = new FormData();
                    formData.append('title', title);
                    formData.append('content', JSON.stringify(outputData));
                    formData.append('status', 'draft');

                    const url = currentPostId ? `${API_BASE}/api/posts/${currentPostId}` : `${API_BASE}/api/posts`;
                    const method = currentPostId ? 'PUT' : 'POST';

                    const response = await fetch(url, {
                        method: method,
                        headers: {
                            'Authorization': 'Bearer demo-token-12345'
                        },
                        body: formData
                    });

                    if (response.ok) {
                        alert('Post saved successfully!');
                        loadPosts();
                        cancelEdit();
                    } else {
                        throw new Error('Failed to save');
                    }
                } catch (error) {
                    console.error('Error saving:', error);
                    alert('Error saving post. Please try again.');
                }
            }

            async function deleteCurrentPost() {
                if (!currentPostId) return;
                if (!confirm('Are you sure you want to delete this post?')) return;

                try {
                    const response = await fetch(`${API_BASE}/api/posts/${currentPostId}`, {
                        method: 'DELETE',
                        headers: {
                            'Authorization': 'Bearer demo-token-12345'
                        }
                    });

                    if (response.ok) {
                        alert('Post deleted');
                        loadPosts();
                        cancelEdit();
                    }
                } catch (error) {
                    console.error('Error deleting:', error);
                }
            }

            function cancelEdit() {
                document.getElementById('editorForm').classList.add('hidden');
                document.getElementById('emptyState').classList.remove('hidden');
                currentPostId = null;
                if (editor && typeof editor.destroy === 'function') {
                    editor.destroy();
                    editor = null;
                }
            }
        </script>
    </body>
    </html>
    """

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
