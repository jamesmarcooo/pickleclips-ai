import pytest
from unittest.mock import patch, MagicMock


def test_generate_reel_updates_status_to_ready():
    from app.workers.reel_gen import generate_reel

    db_updates = {}

    def fake_db_update(reel_id, status, r2_key=None, share_token=None):
        db_updates[reel_id] = {"status": status, "r2_key": r2_key}

    with patch("app.workers.reel_gen._db_update_reel", side_effect=fake_db_update), \
         patch("app.workers.reel_gen._fetch_clips_and_lowlights", return_value=([], [])), \
         patch("app.workers.reel_gen._get_user_center_x", return_value=0.5), \
         patch("app.workers.reel_gen.assemble_and_upload", return_value="reels/reel1/output.mp4"), \
         patch("app.workers.reel_gen.generate_share_token", return_value="tok123"):
        generate_reel(
            reel_id="reel1",
            video_id="vid1",
            user_id="u1",
            output_type="highlight_montage",
            format="horizontal",
        )

    assert db_updates["reel1"]["status"] == "ready"
    assert db_updates["reel1"]["r2_key"] == "reels/reel1/output.mp4"


def test_generate_reel_sets_failed_status_on_error():
    from app.workers.reel_gen import generate_reel

    db_updates = {}

    def fake_db_update(reel_id, status, r2_key=None, share_token=None):
        db_updates[reel_id] = {"status": status}

    with patch("app.workers.reel_gen._db_update_reel", side_effect=fake_db_update), \
         patch("app.workers.reel_gen._fetch_clips_and_lowlights", return_value=([], [])), \
         patch("app.workers.reel_gen._get_user_center_x", return_value=0.5), \
         patch("app.workers.reel_gen.assemble_and_upload", side_effect=RuntimeError("FFmpeg error")), \
         patch.object(generate_reel, "retry", side_effect=RuntimeError("retrying")):
        with pytest.raises(RuntimeError):
            generate_reel(
                reel_id="reel2",
                video_id="v1",
                user_id="u1",
                output_type="highlight_montage",
                format="horizontal",
            )

    assert db_updates.get("reel2", {}).get("status") == "failed"
