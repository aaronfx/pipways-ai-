from fastapi import APIRouter, Depends, HTTPException, Form, Query, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional, List, Dict
from datetime import datetime
import json
import re
import uuid

# Change relative imports to absolute imports
# Assuming your project structure has main.py at the root level
try:
    # Try relative import first (when imported as module)
    from .main import get_db, get_current_admin, get_current_user
except ImportError:
    # Fall back to absolute import (when run directly or in different contexts)
    from main import get_db, get_current_admin, get_current_user

try:
    from .ai_blog_tools import generate_blog_content, calculate_seo_score, get_link_suggestions, calculate_reading_time
except ImportError:
    from ai_blog_tools import generate_blog_content, calculate_seo_score, get_link_suggestions, calculate_reading_time

try:
    from .main import asyncpg
except ImportError:
    import asyncpg

blog_router = APIRouter(tags=["blog"])

# ... rest of your code remains the same ...
