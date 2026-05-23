import pytest

from app.core.monero_auth import validate_nonce


class Redis:
    def __init__(self):
        self.value = "4" + "A" * 94
        self.deleted = False

    async def get(self, _key):
        return self.value

    async def delete(self, _key):
        self.deleted = True


@pytest.mark.asyncio
async def test_wrong_address_does_not_consume_nonce():
    redis = Redis()
    valid, message = await validate_nonce(redis, "nonce", "4" + "B" * 94)
    assert valid is False
    assert message == "Nonce not bound to this address"
    assert redis.deleted is False
