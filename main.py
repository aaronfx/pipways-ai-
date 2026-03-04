# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

# Import routers
from lms_routes import router as lms_router
from admin_routes import router as admin_router

app = FastAPI(
    title="Trading Academy LMS",
    description="Enterprise-level LMS + Trading Academy Platform",
    version="1.0.0",
)

# CORS configuration
origins = [
    "*",  # Adjust to your frontend domain in production
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Include routers
app.include_router(lms_router, prefix="/lms", tags=["LMS"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])

# Root landing page
@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}

# Example of JWT-protected route placeholder
# from auth import get_current_user
# @app.get("/dashboard")
# async def dashboard(user=Depends(get_current_user)):
#     return {"message": f"Welcome {user.email} to your dashboard"}
