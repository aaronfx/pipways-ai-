"""
Zoom Webinar Router
Completely separate from main app - handles all webinar-related endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from typing import Optional, List
from datetime import datetime
import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import Zoom service
try:
    from services.zoom_service import (
        ZoomService, ZoomWebinar, 
        create_webinar, get_webinar, list_webinars, generate_sdk_signature
    )
except ImportError:
    # Fallback for development
    ZoomService = None
    ZoomWebinar = None

# Import auth from main app (shared dependency)
try:
    from main import get_current_user, get_current_admin, get_db
except ImportError:
    # Mock auth for standalone testing
    async def get_current_user():
        return {"email": "test@pipways.com", "id": 1, "name": "Test User"}
    async def get_current_admin():
        return {"email": "admin@pipways.com", "id": 1, "name": "Admin"}
    async def get_db():
        return None

router = APIRouter(
    prefix="/api/webinars",
    tags=["zoom-webinars"],
    responses={404: {"description": "Not found"}}
)

# In-memory storage for webinar metadata (use DB in production)
# Maps our internal ID to Zoom webinar ID
webinar_registry = {}


@router.get("/health")
async def zoom_health_check():
    """Check if Zoom API is configured and accessible"""
    try:
        # Try to list webinars to verify credentials
        webinars = list_webinars(page_size=1)
        return {
            "status": "connected",
            "configured": True,
            "webinars_found": len(webinars)
        }
    except Exception as e:
        return {
            "status": "error",
            "configured": False,
            "error": str(e)
        }


@router.get("/", response_class=JSONResponse)
async def get_all_webinars(
    upcoming: bool = Query(False),
    current_user=Depends(get_current_user)
):
    """
    List all webinars from Zoom
    """
    try:
        zoom_webinars = list_webinars(page_size=30)
        
        # Filter for upcoming if requested
        if upcoming:
            now = datetime.utcnow()
            zoom_webinars = [w for w in zoom_webinars if w.start_time > now]
        
        # Convert to response format
        result = []
        for w in zoom_webinars:
            result.append({
                "id": w.id,
                "topic": w.topic,
                "start_time": w.start_time.isoformat(),
                "duration": w.duration,
                "status": w.status,
                "join_url": w.join_url,
                "is_registered": False  # Would check DB in production
            })
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Zoom API error: {str(e)}")


@router.post("/", response_class=JSONResponse)
async def create_new_webinar(
    topic: str = Form(...),
    description: str = Form(...),
    scheduled_at: datetime = Form(...),
    duration: int = Form(60),
    password: Optional[str] = Form(None),
    max_attendees: int = Form(100),
    current_user=Depends(get_current_user),
    conn=Depends(get_db)
):
    """
    Create a new Zoom webinar
    """
    try:
        # Create webinar in Zoom
        webinar = create_webinar(
            topic=topic,
            start_time=scheduled_at,
            duration=duration,
            agenda=description,
            password=password,
            settings={
                "approval_type": 0,  # Auto-approve
                "registration_type": 1,  # Register once
                "enforce_login": False,
                "allow_multiple_devices": True,
                "auto_recording": "cloud"
            }
        )
        
        # Store in our registry (use DB in production)
        webinar_registry[webinar.id] = {
            "zoom_id": webinar.id,
            "created_by": current_user.get("email") if isinstance(current_user, dict) else current_user,
            "max_attendees": max_attendees,
            "created_at": datetime.utcnow().isoformat()
        }
        
        return {
            "success": True,
            "webinar": {
                "id": webinar.id,
                "topic": webinar.topic,
                "start_url": webinar.start_url,
                "join_url": webinar.join_url,
                "password": webinar.password,
                "start_time": webinar.start_time.isoformat(),
                "duration": webinar.duration
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create webinar: {str(e)}")


@router.get("/{webinar_id}", response_class=JSONResponse)
async def get_webinar_details(
    webinar_id: str,
    current_user=Depends(get_current_user)
):
    """
    Get detailed information about a specific webinar
    """
    try:
        webinar = get_webinar(webinar_id)
        if not webinar:
            raise HTTPException(status_code=404, detail="Webinar not found")
        
        # Get additional metadata from our registry
        meta = webinar_registry.get(webinar_id, {})
        
        return {
            "id": webinar.id,
            "topic": webinar.topic,
            "description": webinar.settings.get("agenda", ""),
            "start_time": webinar.start_time.isoformat(),
            "duration": webinar.duration,
            "status": webinar.status,
            "join_url": webinar.join_url,
            "password": webinar.password,
            "settings": webinar.settings,
            "max_attendees": meta.get("max_attendees", 100),
            "created_by": meta.get("created_by", "unknown")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{webinar_id}/join", response_class=JSONResponse)
async def get_join_credentials(
    webinar_id: str,
    current_user=Depends(get_current_user)
):
    """
    Get SDK credentials for joining a webinar
    Returns signature and meeting details for embedded Zoom client
    """
    try:
        webinar = get_webinar(webinar_id)
        if not webinar:
            raise HTTPException(status_code=404, detail="Webinar not found")
        
        # Determine role (1 = host if they created it, 0 = attendee)
        meta = webinar_registry.get(webinar_id, {})
        user_email = current_user.get("email") if isinstance(current_user, dict) else current_user
        is_host = meta.get("created_by") == user_email
        
        role = 1 if is_host else 0
        
        # Generate SDK signature
        signature = generate_sdk_signature(webinar_id, role)
        
        return {
            "success": True,
            "meeting_number": webinar_id,
            "signature": signature,
            "sdk_key": os.getenv("ZOOM_SDK_KEY"),
            "role": role,
            "password": webinar.password,
            "user_name": current_user.get("name") if isinstance(current_user, dict) else "Guest",
            "user_email": user_email,
            "join_url": webinar.join_url if not is_host else webinar.start_url,
            "is_host": is_host
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate credentials: {str(e)}")


@router.delete("/{webinar_id}", response_class=JSONResponse)
async def delete_webinar(
    webinar_id: str,
    notify: bool = Form(False),
    current_user=Depends(get_current_user),
    conn=Depends(get_db)
):
    """
    Cancel/delete a webinar
    """
    try:
        # Verify ownership
        meta = webinar_registry.get(webinar_id, {})
        user_email = current_user.get("email") if isinstance(current_user, dict) else current_user
        
        if meta.get("created_by") != user_email:
            # Check if admin
            try:
                await get_current_admin()
            except:
                raise HTTPException(status_code=403, detail="Not authorized to delete this webinar")
        
        success = ZoomService.delete_webinar(webinar_id, cancel_notification=notify)
        
        if success:
            webinar_registry.pop(webinar_id, None)
            return {"success": True, "message": "Webinar cancelled"}
        else:
            raise HTTPException(status_code=400, detail="Failed to delete webinar")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{webinar_id}/panelists", response_class=JSONResponse)
async def add_panelist(
    webinar_id: str,
    email: str = Form(...),
    name: str = Form(...),
    current_user=Depends(get_current_user)
):
    """
    Add a panelist (co-host) to the webinar
    """
    try:
        success = ZoomService.add_panelist(webinar_id, email, name)
        
        if success:
            return {"success": True, "message": f"Added {name} as panelist"}
        else:
            raise HTTPException(status_code=400, detail="Failed to add panelist")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{webinar_id}/recordings", response_class=JSONResponse)
async def get_recordings(
    webinar_id: str,
    current_user=Depends(get_current_user)
):
    """
    Get cloud recordings for a past webinar
    """
    try:
        recordings = ZoomService.get_past_webinar_recordings(webinar_id)
        return {
            "webinar_id": webinar_id,
            "recordings": recordings
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Host dashboard endpoints
@router.get("/host/stats", response_class=JSONResponse)
async def get_host_statistics(
    current_user=Depends(get_current_user)
):
    """
    Get webinar statistics for the current host
    """
    try:
        user_email = current_user.get("email") if isinstance(current_user, dict) else current_user
        
        # Get webinars created by this user
        all_webinars = list_webinars(page_size=100)
        my_webinars = []
        
        for wid, meta in webinar_registry.items():
            if meta.get("created_by") == user_email:
                zoom_data = get_webinar(wid)
                if zoom_data:
                    my_webinars.append({
                        "id": wid,
                        "topic": zoom_data.topic,
                        "start_time": zoom_data.start_time.isoformat(),
                        "status": zoom_data.status
                    })
        
        return {
            "total_webinars": len(my_webinars),
            "upcoming": len([w for w in my_webinars if w["status"] == "upcoming"]),
            "past": len([w for w in my_webinars if w["status"] == "ended"]),
            "webinars": my_webinars
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
