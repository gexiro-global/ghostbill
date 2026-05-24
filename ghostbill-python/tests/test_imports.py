from __future__ import annotations


def test_top_level_imports() -> None:
    import ghostbill

    assert hasattr(ghostbill, "GhostBill")
    assert hasattr(ghostbill, "AsyncGhostBill")
    assert hasattr(ghostbill, "GhostBillError")
    assert hasattr(ghostbill, "__version__")


def test_version_string() -> None:
    import ghostbill
    from ghostbill import __version__

    assert __version__ == "0.1.0"
    assert __version__ in ghostbill.__version__


def test_events_module_importable() -> None:
    import ghostbill.events as events

    assert len(events.ALL_EVENTS) == 22


def test_events_not_reexported_at_package_root() -> None:
    import ghostbill

    assert not hasattr(ghostbill, "INVOICE_PAID")
