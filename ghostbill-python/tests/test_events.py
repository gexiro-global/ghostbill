from __future__ import annotations

import re

import ghostbill.events as events


def test_all_events_count_is_22() -> None:
    assert len(events.ALL_EVENTS) == 22


def test_individual_constants_match_all_events() -> None:
    event_names = {name for name in events.__all__ if name != "ALL_EVENTS"}
    event_values = {getattr(events, name) for name in event_names}

    assert event_values == events.ALL_EVENTS


def test_event_string_format() -> None:
    pattern = re.compile(r"^[a-z]+\.[a-z_]+$")

    assert all(pattern.match(event) for event in events.ALL_EVENTS)


def test_event_domains_present() -> None:
    assert any(event.startswith("payment.") for event in events.ALL_EVENTS)
    assert any(event.startswith("invoice.") for event in events.ALL_EVENTS)
    assert any(event.startswith("subscription.") for event in events.ALL_EVENTS)
