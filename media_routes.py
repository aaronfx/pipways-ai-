# media_routes.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse, FileResponse
from typing import Optional, List
from datetime import datetime
import os
import uuid
import shutil
from pathlib import Path

from dependencies import get_db, get_current_admin

media_router = APIRouter(tags=["media"])

# Upload directories
UPLOAD_DIR = Path("uploads")
IMAGES_DIR = UPLOAD_DIR / "images"
DOCUMENTS_DIR = UPLOAD_DIR / "documents"

# Create directories if they don't exist
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_TYPES = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/webp': '.webp',
    'image/gif': '.gif'
}

ALLOWED_DOCUMENT_TYPES = {
    'application/pdf': '.pdf',
    'application/msword': '.doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    'text/plain': '.txt',
    'application/vnd.ms-excel': '.xls',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx'
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

@media_router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    alt_text: Optional[str] = Form(None),
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Upload media file (images or documents)"""
    try:
        # Validate file size
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large (max 10MB)")
        
        # Determine file type and directory
        content_type = file.content_type
        
        if content_type in ALLOWED_IMAGE_TYPES:
            target_dir = IMAGES_DIR
            file_type = "image"
            allowed_types = ALLOWED_IMAGE_TYPES
        elif content_type in ALLOWED_DOCUMENT_TYPES:
            target_dir = DOCUMENTS_DIR
            file_type = "document"
            allowed_types = ALLOWED_DOCUMENT_TYPES
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file type: {content_type}"
            )
        
        # Generate unique filename
        ext = allowed_types.get(content_type, Path(file.filename).suffix)
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = target_dir / unique_name
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Get user ID
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        
        # Save to database
        media_id = await conn.fetchval("""
            INSERT INTO media_files 
            (filename, original_name, file_path, file_type, file_size, mime_type, alt_text, uploaded_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
        """,
            unique_name,
            file.filename,
            str(file_path),
            file_type,
            len(contents),
            content_type,
            alt_text,
            user["id"]
        )
        
        # Generate URL
        file_url = f"/uploads/{file_type}s/{unique_name}"
        
        return {
            "success": True,
            "media_id": media_id,
            "filename": unique_name,
            "original_name": file.filename,
            "url": file_url,
            "file_type": file_type,
            "size": len(contents),
            "alt_text": alt_text
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@media_router.get("/library")
async def get_media_library(
    file_type: Optional[str] = Query(None),
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Get media library with filtering and pagination"""
    try:
        offset = (page - 1) * per_page
        
        where_clauses = []
        params = []
        
        if file_type:
            where_clauses.append(f"file_type = ${len(params)+1}")
            params.append(file_type)
        
        if search:
            where_clauses.append(f"(original_name ILIKE ${len(params)+1} OR alt_text ILIKE ${len(params)+1})")
            params.append(f"%{search}%")
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        media = await conn.fetch(f"""
            SELECT m.*, u.name as uploaded_by_name
            FROM media_files m
            LEFT JOIN users u ON m.uploaded_by = u.id
            WHERE {where_sql}
            ORDER BY m.created_at DESC
            LIMIT ${len(params)+1} OFFSET ${len(params)+2}
        """, *params, per_page, offset)
        
        count = await conn.fetchrow(f"""
            SELECT COUNT(*) as total FROM media_files WHERE {where_sql}
        """, *params)
        
        # Add full URLs
        result = []
        for item in media:
            item_dict = dict(item)
            item_dict['url'] = f"/uploads/{item['file_type']}s/{item['filename']}"
            result.append(item_dict)
        
        return {
            "media": result,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": count['total'] if count else 0
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@media_router.delete("/{media_id}")
async def delete_media(
    media_id: int,
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Delete media file"""
    try:
        media = await conn.fetchrow("SELECT * FROM media_files WHERE id = $1", media_id)
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")
        
        # Delete file from disk
        file_path = Path(media['file_path'])
        if file_path.exists():
            file_path.unlink()
        
        # Delete from database
        await conn.execute("DELETE FROM media_files WHERE id = $1", media_id)
        
        return {"success": True, "message": "Media deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@media_router.get("/{media_id}")
async def get_media_detail(
    media_id: int,
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Get single media details"""
    try:
        media = await conn.fetchrow("""
            SELECT m.*, u.name as uploaded_by_name
            FROM media_files m
            LEFT JOIN users u ON m.uploaded_by = u.id
            WHERE m.id = $1
        """, media_id)
        
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")
        
        result = dict(media)
        result['url'] = f"/uploads/{media['file_type']}s/{media['filename']}"
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
