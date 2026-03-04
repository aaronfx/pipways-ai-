
from fastapi import APIRouter

router = APIRouter()

@router.get("/courses")
def list_courses():
    return {"courses": ["Course 1", "Course 2"]}
