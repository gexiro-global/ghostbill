"""Subscription exceptions and state machine constants.

Used by subscription_service, subscription_renewal, routes, and renewer task.
Phase 6C: SkipRenewalError now carries result_type for event logging.
"""

from app.db.models import SubscriptionStatus

# ── State Machine ────────────────────────────────────────────────────────────

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
    SubscriptionStatus.trialing: [  # Phase 8A
        SubscriptionStatus.active,
        SubscriptionStatus.cancelled,
    ],
    SubscriptionStatus.cancelled: [],
    SubscriptionStatus.expired: [],
}

TERMINAL_STATUSES: set[SubscriptionStatus] = {
    SubscriptionStatus.cancelled,
    SubscriptionStatus.expired,
}


# ── Exceptions ──────────────────────────────────────────────────────────────


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
    """Renewal skipped — unpaid invoice exists or already renewed.

    Phase 6C: carries result_type for event logging.
    """

    def __init__(self, message: str = "", result_type: str = "skipped"):
        super().__init__(message)
        self.result_type = result_type
