from pathlib import Path


def test_redis_lease_helper_and_loops():
    helper = (Path("backend/app/tasks/detection_helpers.py")).read_text()
    assert "nx=True" in helper and "ex=ttl_seconds" in helper
    for task_path in [
        "backend/app/tasks/detection_engine.py",
        "backend/app/tasks/webhook_worker.py",
        "backend/app/tasks/data_retention.py",
        "backend/app/tasks/price_updater.py",
        "backend/app/tasks/invoice_expirer.py",
        "backend/app/tasks/subscription_renewer.py",
    ]:
        assert "acquire_task_lease" in Path(task_path).read_text()
