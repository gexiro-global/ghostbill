from pathlib import Path


def test_health_metric_uses_post_scan_height():
    source = (Path("backend/app/tasks/detection_engine.py")).read_text()
    assert "scanned_height_for_health = checkpoint_to_save" in source
    assert "save_health_metrics(current_height, scanned_height_for_health)" in source
