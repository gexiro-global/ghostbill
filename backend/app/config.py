from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "GhostBill"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = ""
    api_prefix: str = "/v1"

    # Admin (operator of this GhostBill instance)
    admin_merchant_id: str = ""  # Phase 9: set in .env to enable admin panel

    # PostgreSQL
    postgres_user: str = "ghostbill"
    postgres_password: str = ""
    postgres_host: str = "ghostbill_postgres"
    postgres_port: int = 5432
    postgres_db: str = "ghostbill"

    # Redis
    redis_host: str = "ghostbill_redis"
    redis_port: int = 6379
    redis_url: str = ""

    # monerod RPC
    monerod_rpc_host: str = "127.0.0.1"
    monerod_rpc_port: int = 31208
    monerod_rpc_user: str = ""
    monerod_rpc_pass: str = ""

    # wallet-rpc
    wallet_rpc_host: str = "127.0.0.1"
    wallet_rpc_port: int = 18083
    wallet_rpc_user: str = "ghostbill"
    wallet_rpc_pass: str = ""
    wallet_password: str = ""

    # Encryption
    master_encryption_key: str = ""

    # Webhooks
    webhook_signing_key: str = ""

    # Tor
    tor_proxy: str = "socks5h://127.0.0.1:9050"
    use_tor_proxy: bool = True
    tor_only: bool = False

    # Onion addresses (set after Tor generates them)
    onion_api: str = ""
    onion_dashboard: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_dsn(self) -> str:
        if self.redis_url:
            return self.redis_url
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
