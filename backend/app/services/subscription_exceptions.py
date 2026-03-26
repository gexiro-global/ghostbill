"""Subscription exceptions and state machine constants.

Used by subscription_service, subscription_renewal, routes, and renewer task.
"""

from app.db.models import SubscriptionStatus


# ─── State Machine ──────────────────────────────────────────────────────────

VALID_TRANSITIONS: dict[SubscriptionStatus, list[SubscriptionStatus]] = {
    SubscriptionStatus.active: [
        SubscriptionStatus.paused,
        SubscriptionStatus.past_due,
        SubscriptionStatus.cancelled,
    ],
    SubscriptionStatus.paused: [
        SubscriptionStatus.active,
        SubscriptionStatus.cancelled,
    ],
    SubscriptionStatus.past_due: [
        SubscriptionStatus.active,
        SubscriptionStatus.expired,
        SubscriptionStatus.cancelled,
    ],
    SubscriptionStatus.cancelled: [],
    SubscriptionStatus.expired: [],
}

TERMINAL_STATUSES: set[SubscriptionStatus] = {
    SubscriptionStatus.cancelled,
    SubscriptionStatus.expired,
}


# ─── Exceptions ────────────────────────────────────────────────────────────


class SubscriptionError(Exception):
    """Base subscription service error."""
    pass


class SubscriptionNotFoundError(SubscriptionError):
    """Subscription not found or wrong merchant."""
    pass


class SubscriptionValidationError(SubscriptionError):
    """Input validation failed."""
    pass


class SubscriptionStateError(SubscriptionError):
    """Invalid state transition."""
    pass


class SkipRenewalError(SubscriptionError):
    """Renewal skipped — unpaid invoice exists or already renewed."""
    pass
