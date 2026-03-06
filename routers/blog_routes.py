"""
Blog Routes Module for Pipways Platform
Can be imported into main.py or used standalone
"""

from fastapi import APIRouter, HTTPException, Depends, Form, UploadFile, File
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Optional, List
import json
import os

router = APIRouter()

# In-memory storage (replace with database in production)
posts_db = []

# Simple auth dependency (should match main.py)
def get_current_user():
    # This is a placeholder - import from main.py in production
    return {"email": "admin@pipways.com", "role": "admin"}

@router.get("/posts")
async def get_all_posts():
    """Get all blog posts"""
    return {"posts": posts_db, "count": len(posts_db)}

@router.get("/posts/{post_id}")
async def get_post_by_id(post_id: int):
    """Get single post by ID"""
    for post in posts_db:
        if post["id"] == post_id:
            return post
    raise HTTPException(status_code=404, detail="Post not found")

@router.post("/posts")
async def create_new_post(
    title: str = Form(...),
    content: str = Form(...),
    excerpt: Optional[str] = Form(None),
    status: str = Form("draft"),
    featured_image: Optional[str] = Form(None)
):
    """Create new blog post"""
    post = {
        "id": len(posts_db) + 1,
        "title": title,
        "content": json.loads(content) if isinstance(content, str) else content,
        "excerpt": excerpt or title[:100] + "...",
        "status": status,
        "featured_image": featured_image,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    posts_db.append(post)
    return {"success": True, "post": post}

@router.put("/posts/{post_id}")
async def update_existing_post(
    post_id: int,
    title: str = Form(...),
    content: str = Form(...),
    excerpt: Optional[str] = Form(None),
    status: str = Form("draft")
):
    """Update existing post"""
    for i, post in enumerate(posts_db):
        if post["id"] == post_id:
            posts_db[i].update({
                "title": title,
                "content": json.loads(content) if isinstance(content, str) else content,
                "excerpt": excerpt or title[:100] + "...",
                "status": status,
                "updated_at": datetime.now().isoformat()
            })
            return {"success": True, "post": posts_db[i]}
    raise HTTPException(status_code=404, detail="Post not found")

@router.delete("/posts/{post_id}")
async def delete_existing_post(post_id: int):
    """Delete post"""
    global posts_db
    initial_count = len(posts_db)
    posts_db = [p for p in posts_db if p["id"] != post_id]
    if len(posts_db) < initial_count:
        return {"success": True, "message": "Post deleted"}
    raise HTTPException(status_code=404, detail="Post not found")

@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    """Upload image for blog posts"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        filepath = f"static/uploads/{filename}"

        os.makedirs("static/uploads", exist_ok=True)

        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)

        return {
            "success": 1,
            "file": {
                "url": f"/static/uploads/{filename}",
                "name": filename
            }
        }
    except Exception as e:
        return {"success": 0, "message": str(e)}
