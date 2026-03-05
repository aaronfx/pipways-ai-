# dependencies.py
import os
import asyncpg
import jwt
from fastapi import HTTPException, Header, Request
from typing import Optional

DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")

async def get_db():
    """Database connection dependency"""
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL not configured")
    
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        await conn.close()

async def get_current_user(request: Request) -> str:
    """Extract current user from JWT token"""
    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload.get("sub") or payload.get("email")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_admin(request: Request) -> str:
    """Verify user is admin"""
    user_email = await get_current_user(request)
    # Add your admin verification logic here
    # For example, check if user is in admin list or has admin role
    return user_email
