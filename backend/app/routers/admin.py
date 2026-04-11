from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg

from app.auth import get_current_user
from app.database import get_db
from app.config import settings, FREE_TIER_LIMITS, ALLOWED_USER_CAP
from app.services.usage_guard import fetch_snapshot, evaluate

router = APIRouter(tags=["admin"])


@router.get("/admin/usage")
async def get_usage_snapshot(
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Owner-only endpoint: returns current free tier usage across all services.
    Returns alerts and blocks arrays so you can see what's approaching limits.
    """
    # admin_email stores the owner's Supabase user UUID. If unset, endpoint is disabled.
    if not settings.admin_email:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if user_id != settings.admin_email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner only")

    snap = evaluate(await fetch_snapshot(db))

    return {
        "snapshot": {
            "supabase_db_bytes":      snap.supabase_db_bytes,
            "r2_storage_bytes":       snap.r2_storage_bytes,
            "upstash_commands_today": snap.upstash_commands_today,
            "upstash_memory_bytes":   snap.upstash_memory_bytes,
            "total_users":            snap.total_users,
        },
        "limits":   FREE_TIER_LIMITS,
        "user_cap": ALLOWED_USER_CAP,
        "alerts":   snap.alerts,
        "blocks":   snap.blocks,
    }
