import pytest
from unittest.mock import AsyncMock, patch
from app.services.usage_guard import (
    UsageSnapshot,
    QuotaExceededError,
    evaluate,
    assert_can_ingest,
)
from app.config import FREE_TIER_LIMITS, ALERT_THRESHOLD_PCT, BLOCK_THRESHOLD_PCT


def _snap_at_pct(field: str, limit_key: str, pct: float) -> UsageSnapshot:
    """Helper: create a snapshot with one field set to pct% of its limit."""
    snap = UsageSnapshot()
    setattr(snap, field, int(FREE_TIER_LIMITS[limit_key] * pct))
    return snap


# ── evaluate() tests (pure/sync) ──────────────────────────────────────────────


def test_no_alerts_when_under_threshold():
    """Snapshot with all fields at 0 → evaluate() returns empty alerts and blocks."""
    snap = UsageSnapshot()
    evaluate(snap)
    assert snap.alerts == []
    assert snap.blocks == []


def test_alert_at_80_pct_supabase_db():
    """supabase_db_bytes at 82% → alerts contains the field, blocks is empty."""
    snap = _snap_at_pct("supabase_db_bytes", "supabase_db_bytes", 0.82)
    evaluate(snap)
    assert any("supabase_db_bytes" in a for a in snap.alerts)
    assert snap.blocks == []


def test_block_at_90_pct_r2_storage():
    """r2_storage_bytes at 92% → blocks contains the field."""
    snap = _snap_at_pct("r2_storage_bytes", "r2_storage_bytes", 0.92)
    evaluate(snap)
    assert any("r2_storage_bytes" in b for b in snap.blocks)


def test_critical_metric_appears_in_both_alerts_and_blocks():
    """r2_storage_bytes at 95% → both alerts AND blocks contain r2_storage_bytes.

    This verifies the if/if (not if/elif) logic in evaluate() — a critical metric
    above BLOCK_THRESHOLD_PCT must appear in BOTH lists.
    """
    snap = _snap_at_pct("r2_storage_bytes", "r2_storage_bytes", 0.95)
    evaluate(snap)
    assert any("r2_storage_bytes" in a for a in snap.alerts), "expected r2_storage_bytes in alerts"
    assert any("r2_storage_bytes" in b for b in snap.blocks), "expected r2_storage_bytes in blocks"


def test_upstash_memory_is_alert_only():
    """upstash_memory_bytes at 95% → alerts non-empty, blocks empty (non-critical field)."""
    snap = _snap_at_pct("upstash_memory_bytes", "upstash_memory_bytes", 0.95)
    evaluate(snap)
    assert len(snap.alerts) > 0
    assert snap.blocks == []


def test_multiple_services_near_limit():
    """supabase_db_bytes at 85% AND r2_storage_bytes at 85% → len(alerts) == 2."""
    snap = UsageSnapshot()
    snap.supabase_db_bytes = int(FREE_TIER_LIMITS["supabase_db_bytes"] * 0.85)
    snap.r2_storage_bytes = int(FREE_TIER_LIMITS["r2_storage_bytes"] * 0.85)
    evaluate(snap)
    assert len(snap.alerts) == 2


# ── assert_can_ingest() tests (async) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_assert_can_ingest_passes_when_under_limit():
    """When fetch_snapshot returns a clean snapshot, assert_can_ingest does not raise."""
    clean_snap = UsageSnapshot()

    with patch("app.services.usage_guard.fetch_snapshot", new=AsyncMock(return_value=clean_snap)):
        # Should complete without raising
        await assert_can_ingest(db=None)


@pytest.mark.asyncio
async def test_assert_can_ingest_raises_when_critical():
    """When fetch_snapshot returns a snapshot with r2 at 95%, QuotaExceededError is raised."""
    snap = _snap_at_pct("r2_storage_bytes", "r2_storage_bytes", 0.95)

    with patch("app.services.usage_guard.fetch_snapshot", new=AsyncMock(return_value=snap)):
        with pytest.raises(QuotaExceededError):
            await assert_can_ingest(db=None)
