from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query
from typing import Optional
from .main import get_db, get_current_admin, MEDIA_DIR, MAX_FILE_SIZE
from .main import uuid, Path
from .main import asyncpg

media_router = APIRouter(prefix="/media", tags=["media"])

@media_router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    alt_text: Optional[str] = None,
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """Upload media file (admin only)"""
    try:
        contents = await file.read()
        file_size = len(contents)
        
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large")
        
        # Get file extension
        ext = Path(file.filename).suffix.lower()
        
        # Generate unique filename
        unique_filename = f"{uuid.uuid4()}{ext}"
        file_path = MEDIA_DIR / unique_filename
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Determine file type
        file_type = ext.replace('.', '')
        
        # Save to database
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", current_user)
        
        media_id = await conn.fetchval("""
            INSERT INTO media_files 
            (filename, original_name, file_path, file_type, file_size, mime_type, alt_text, uploaded_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
        """,
            unique_filename,
            file.filename,
            str(file_path),
            file_type,
            file_size,
            file.content_type or "application/octet-stream",
            alt_text,
            user["id"]
        )
        
        return {
            "success": True,
            "media_id": media_id,
            "filename": unique_filename,
            "url": f"/media/{unique_filename}",
            "size": file_size
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@media_router.get("/")
async def list_media(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    current_user: str = Depends(get_current_admin),
    conn=Depends(get_db)
):
    """List all media files (admin only) with search"""
    try:
        offset = (page - 1) * per_page
        
        where_clause = ""
        params = []
        if search:
            where_clause = "WHERE filename ILIKE $1 OR alt_text ILIKE $1 OR original_name ILIKE $1"
            params.append(f"%{search}%")
        
        media = await conn.fetch(f"""
            SELECT m.*, u.name as uploaded_by_name
            FROM media_files m
            JOIN users u ON m.uploaded_by = u.id
            {where_clause}
            ORDER BY m.created_at DESC
            LIMIT ${len(params)+1} OFFSET ${len(params)+2}
        """, *params, per_page, offset)
        
        count = await conn.fetchrow(f"SELECT COUNT(*) as total FROM media_files {where_clause}", *params)
        
        return {
            "media": [dict(m) for m in media],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": count['total'] if count else 0
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
