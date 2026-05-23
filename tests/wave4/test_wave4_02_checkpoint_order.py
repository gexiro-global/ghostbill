from pathlib import Path


def test_checkpoint_saved_after_commit():
    source = (Path("backend/app/tasks/detection_engine.py")).read_text()
    assert source.index("await db.commit()") < source.index("await save_last_scanned_height(checkpoint_to_save)")
