"""
Zoom API Service Layer
Handles all Zoom API interactions - completely separate from main app logic
"""
import os
import base64
import hashlib
import hmac
import time
import json
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

# Zoom Configuration from environment
ZOOM_ACCOUNT_ID = os.getenv("ZOOM_ACCOUNT_ID")
ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET")
ZOOM_SDK_KEY = os.getenv("ZOOM_SDK_KEY")
ZOOM_SDK_SECRET = os.getenv("ZOOM_SDK_SECRET")

ZOOM_API_BASE = "https://api.zoom.us/v2"
ZOOM_OAUTH_URL = "https://zoom.us/oauth/token"


@dataclass
class ZoomWebinar:
    id: str
    topic: str
    start_time: datetime
    duration: int
    join_url: str
    start_url: str
    password: Optional[str]
    settings: Dict[str, Any]
    status: str


class ZoomService:
    """Service class for Zoom API operations"""
    
    _access_token: Optional[str] = None
    _token_expires_at: Optional[datetime] = None
    
    @classmethod
    def _get_access_token(cls) -> str:
        """Get OAuth access token for Server-to-Server app"""
        if cls._access_token and cls._token_expires_at and datetime.utcnow() < cls._token_expires_at:
            return cls._access_token
        
        if not all([ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET]):
            raise ValueError("Zoom credentials not configured")
        
        auth_string = base64.b64encode(
            f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()
        ).decode()
        
        response = requests.post(
            ZOOM_OAUTH_URL,
            headers={"Authorization": f"Basic {auth_string}"},
            params={
                "grant_type": "account_credentials",
                "account_id": ZOOM_ACCOUNT_ID
            }
        )
        response.raise_for_status()
        
        data = response.json()
        cls._access_token = data["access_token"]
        cls._token_expires_at = datetime.utcnow() + timedelta(seconds=data["expires_in"] - 60)
        
        return cls._access_token
    
    @classmethod
    def _headers(cls) -> Dict[str, str]:
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {cls._get_access_token()}",
            "Content-Type": "application/json"
        }
    
    @classmethod
    def create_webinar(
        cls,
        topic: str,
        start_time: datetime,
        duration: int = 60,
        agenda: str = "",
        password: Optional[str] = None,
        settings: Optional[Dict] = None
    ) -> ZoomWebinar:
        """
        Create a new Zoom webinar
        """
        default_settings = {
            "host_video": True,
            "panelists_video": True,
            "practice_session": True,
            "hd_video": True,
            "approval_type": 0,  # No registration required
            "audio": "both",
            "auto_recording": "cloud",
            "enforce_login": False,
            "question_answer": True,
            "attendees_and_panelists_video": True,
            "allow_multiple_devices": True
        }
        
        if settings:
            default_settings.update(settings)
        
        payload = {
            "topic": topic,
            "type": 5,  # Webinar
            "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration": duration,
            "timezone": "UTC",
            "agenda": agenda,
            "settings": default_settings
        }
        
        if password:
            payload["password"] = password
        
        response = requests.post(
            f"{ZOOM_API_BASE}/users/me/webinars",
            headers=cls._headers(),
            json=payload
        )
        response.raise_for_status()
        
        data = response.json()
        return ZoomWebinar(
            id=str(data["id"]),
            topic=data["topic"],
            start_time=datetime.fromisoformat(data["start_time"].replace('Z', '+00:00')),
            duration=data["duration"],
            join_url=data["join_url"],
            start_url=data["start_url"],
            password=data.get("password"),
            settings=data["settings"],
            status=data["status"]
        )
    
    @classmethod
    def get_webinar(cls, webinar_id: str) -> Optional[ZoomWebinar]:
        """Get webinar details"""
        try:
            response = requests.get(
                f"{ZOOM_API_BASE}/webinars/{webinar_id}",
                headers=cls._headers()
            )
            response.raise_for_status()
            data = response.json()
            
            return ZoomWebinar(
                id=str(data["id"]),
                topic=data["topic"],
                start_time=datetime.fromisoformat(data["start_time"].replace('Z', '+00:00')),
                duration=data["duration"],
                join_url=data["join_url"],
                start_url=data["start_url"],
                password=data.get("password"),
                settings=data["settings"],
                status=data["status"]
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    @classmethod
    def update_webinar(
        cls,
        webinar_id: str,
        topic: Optional[str] = None,
        start_time: Optional[datetime] = None,
        duration: Optional[int] = None,
        agenda: Optional[str] = None,
        settings: Optional[Dict] = None
    ) -> ZoomWebinar:
        """Update webinar details"""
        payload = {}
        if topic:
            payload["topic"] = topic
        if start_time:
            payload["start_time"] = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        if duration:
            payload["duration"] = duration
        if agenda:
            payload["agenda"] = agenda
        if settings:
            payload["settings"] = settings
        
        response = requests.patch(
            f"{ZOOM_API_BASE}/webinars/{webinar_id}",
            headers=cls._headers(),
            json=payload
        )
        response.raise_for_status()
        
        return cls.get_webinar(webinar_id)
    
    @classmethod
    def delete_webinar(cls, webinar_id: str, cancel_notification: bool = False) -> bool:
        """Delete/cancel a webinar"""
        try:
            response = requests.delete(
                f"{ZOOM_API_BASE}/webinars/{webinar_id}",
                headers=cls._headers(),
                params={"cancel_webinar_reminder": cancel_notification}
            )
            response.raise_for_status()
            return True
        except requests.exceptions.HTTPError:
            return False
    
    @classmethod
    def list_webinars(
        cls,
        user_id: str = "me",
        page_size: int = 30,
        page_number: int = 1
    ) -> List[ZoomWebinar]:
        """List all webinars"""
        response = requests.get(
            f"{ZOOM_API_BASE}/users/{user_id}/webinars",
            headers=cls._headers(),
            params={"page_size": page_size, "page_number": page_number}
        )
        response.raise_for_status()
        
        data = response.json()
        webinars = []
        
        for item in data.get("webinars", []):
            webinars.append(ZoomWebinar(
                id=str(item["id"]),
                topic=item["topic"],
                start_time=datetime.fromisoformat(item["start_time"].replace('Z', '+00:00')),
                duration=item["duration"],
                join_url=item.get("join_url", ""),
                start_url="",
                password=item.get("password"),
                settings={},
                status=item["status"]
            ))
        
        return webinars
    
    @classmethod
    def get_webinar_attendees(cls, webinar_id: str) -> List[Dict]:
        """Get list of webinar attendees (requires report scope)"""
        try:
            response = requests.get(
                f"{ZOOM_API_BASE}/report/webinars/{webinar_id}/participants",
                headers=cls._headers()
            )
            response.raise_for_status()
            return response.json().get("participants", [])
        except requests.exceptions.HTTPError:
            return []
    
    @classmethod
    def add_panelist(cls, webinar_id: str, email: str, name: str) -> bool:
        """Add a panelist to the webinar"""
        try:
            response = requests.post(
                f"{ZOOM_API_BASE}/webinars/{webinar_id}/panelists",
                headers=cls._headers(),
                json={"panelists": [{"email": email, "name": name}]}
            )
            response.raise_for_status()
            return True
        except requests.exceptions.HTTPError:
            return False
    
    @classmethod
    def generate_sdk_signature(
        cls,
        meeting_number: str,
        role: int = 0  # 0 = attendee, 1 = host
    ) -> str:
        """
        Generate signature for Zoom Meeting SDK
        Required for joining webinars from embedded client
        """
        if not ZOOM_SDK_KEY or not ZOOM_SDK_SECRET:
            raise ValueError("Zoom SDK credentials not configured")
        
        timestamp = int(time.time())
        msg = f"{ZOOM_SDK_KEY}{meeting_number}{timestamp}{role}"
        message = base64.b64encode(msg.encode()).decode()
        
        secret = ZOOM_SDK_SECRET.encode()
        hash_obj = hmac.new(secret, message.encode(), hashlib.sha256)
        hash_str = base64.b64encode(hash_obj.digest()).decode()
        
        signature = f"{ZOOM_SDK_KEY}.{meeting_number}.{timestamp}.{role}.{hash_str}"
        return base64.b64encode(signature.encode()).decode()
    
    @classmethod
    def get_past_webinar_recordings(cls, webinar_id: str) -> List[Dict]:
        """Get cloud recordings for a past webinar"""
        try:
            response = requests.get(
                f"{ZOOM_API_BASE}/meetings/{webinar_id}/recordings",
                headers=cls._headers()
            )
            response.raise_for_status()
            data = response.json()
            return data.get("recording_files", [])
        except requests.exceptions.HTTPError:
            return []


# Convenience functions for direct import
def create_webinar(*args, **kwargs) -> ZoomWebinar:
    return ZoomService.create_webinar(*args, **kwargs)

def get_webinar(webinar_id: str) -> Optional[ZoomWebinar]:
    return ZoomService.get_webinar(webinar_id)

def list_webinars(*args, **kwargs) -> List[ZoomWebinar]:
    return ZoomService.list_webinars(*args, **kwargs)

def generate_sdk_signature(meeting_number: str, role: int = 0) -> str:
    return ZoomService.generate_sdk_signature(meeting_number, role)
