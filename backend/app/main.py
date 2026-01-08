from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1 import health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup: ensure upload directory exists
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown
    pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="""
    ## Legislative Redline Tool

    Compare proposed statutory amendments against current federal law (USC and CFR),
    displaying visual redline comparisons.

    ### Features
    - Upload PDF/DOCX documents with proposed amendments
    - Auto-detect USC and CFR citations
    - Fetch current law from govinfo.gov and eCFR.gov
    - Generate visual redline comparisons (strikethrough/highlights)

    ### Workflow
    1. Upload a document containing proposed statutory changes
    2. System parses and detects all USC/CFR citations
    3. Current law is fetched from official sources
    4. Amendments are applied and diff is generated
    5. View results with redlined original and highlighted changes
    """,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix=settings.API_V1_STR, tags=["health"])


@app.get("/")
async def root():
    return {
        "name": settings.PROJECT_NAME,
        "message": "Compare proposed statutory amendments against current federal law",
        "version": settings.VERSION,
        "docs": f"{settings.API_V1_STR}/docs",
    }
