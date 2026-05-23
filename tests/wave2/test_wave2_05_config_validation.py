import pytest

from app.config import Settings


def test_production_empty_secrets_raise():
    with pytest.raises(RuntimeError):
        Settings(app_env="production", secret_key="", master_encryption_key="")


def test_debug_requires_explicit_env_value():
    settings = Settings(app_env="development", debug=True, secret_key="", master_encryption_key="")
    assert settings.debug is True
