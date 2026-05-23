from app.config import Settings


def test_debug_does_not_enable_database_echo_by_default():
    settings = Settings(app_env="development", debug=True, secret_key="", master_encryption_key="")
    assert settings.debug is True
    assert settings.database_echo is False
