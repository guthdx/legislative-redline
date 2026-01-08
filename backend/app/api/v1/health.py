from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db
from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Health check endpoint.

    Returns the service status and database connectivity.
    """
    # Check database connectivity
    db_status = "healthy"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "version": settings.VERSION,
        "database": db_status,
        "govinfo_configured": bool(settings.GOVINFO_API_KEY),
    }
