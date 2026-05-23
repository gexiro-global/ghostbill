import pytest

from app.api import auth


class Result:
    def scalars(self):
        return self

    def all(self):
        return []


class DB:
    async def execute(self, _stmt):
        return Result()


@pytest.mark.asyncio
async def test_prefix_miss_runs_dummy_bcrypt(monkeypatch):
    called = False

    def fake_verify(token, key_hash):
        nonlocal called
        called = True
        assert key_hash == auth.DUMMY_API_KEY_HASH
        return False

    monkeypatch.setattr(auth, "verify_api_key", fake_verify)
    with pytest.raises(Exception) as exc:
        await auth._auth_via_api_key("gb_live_" + "a" * 32, DB())
    assert exc.value.status_code == 401
    assert called is True
