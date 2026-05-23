import pytest
from pydantic import ValidationError

from app.api.routes.customers import CustomerCreateRequest
from app.api.routes.merchants import MerchantRegisterRequest
from app.api.routes.subscription_schemas import SubscriptionCreateRequest


def test_invalid_email_rejected():
    with pytest.raises(ValidationError):
        CustomerCreateRequest(email="not-an-email")

    with pytest.raises(ValidationError):
        MerchantRegisterRequest(primary_address="4" + "A" * 94, view_key="a" * 64, email="bad")


def test_oversized_metadata_rejected():
    with pytest.raises(ValidationError):
        CustomerCreateRequest(metadata={f"k{i}": i for i in range(21)})

    with pytest.raises(ValidationError):
        SubscriptionCreateRequest(
            customer_id="123e4567-e89b-12d3-a456-426614174000",
            amount_xmr="0.5",
            interval_days=30,
            metadata={"a": {"b": {"c": "too deep"}}},
        )
