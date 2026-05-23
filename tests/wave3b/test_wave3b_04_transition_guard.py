import pytest

from app.db.models import SubscriptionStatus
from app.services.subscription_exceptions import SubscriptionStateError, transition_subscription_status


class DummySubscription:
    status = SubscriptionStatus.cancelled


def test_invalid_subscription_transition_raises():
    sub = DummySubscription()
    with pytest.raises(SubscriptionStateError):
        transition_subscription_status(sub, SubscriptionStatus.active)
