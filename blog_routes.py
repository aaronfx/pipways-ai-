# blog_routes.py - Update the imports at the top
from fastapi import APIRouter, Depends, HTTPException, Form, Query, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional, List, Dict
from datetime import datetime
import json
import re
import uuid
import asyncpg

# Import from main instead of dependencies
# Use try/except to handle both direct run and imported scenarios
try:
    from main import get_db, get_current_admin, get_current_user
except ImportError:
    # When blog_routes is imported from main, we need to avoid circular import
    # The dependencies will be available via FastAPI's dependency injection system
    from typing import Callable
    def get_db(): pass
    def get_current_admin(): pass
    def get_current_user(): pass

# Import ai_blog_tools
try:
    from ai_blog_tools import generate_blog_content, calculate_seo_score, get_link_suggestions, calculate_reading_time
except ImportError:
    from .ai_blog_tools import generate_blog_content, calculate_seo_score, get_link_suggestions, calculate_reading_time

blog_router = APIRouter(tags=["blog"])

# ... rest of your blog_routes.py code remains the same ...
