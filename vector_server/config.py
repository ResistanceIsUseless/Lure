from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Domains
    oob_domain: str = "oob.cbhzdev.com"
    content_domain: str = "content.cbhzdev.com"
    public_ip: str = ""

    # Interactsh
    interactsh_url: str = "http://127.0.0.1:80"
    interactsh_token: str = "changeme"
    interactsh_poll_interval: int = 5  # seconds

    # Correlation store
    token_ttl: int = 86400  # 24 hours
    token_max_size: int = 100_000

    # Admin
    admin_token: str = "changeme"

    @property
    def callback_base(self) -> str:
        return f"https://{self.oob_domain}"

    @property
    def content_base(self) -> str:
        return f"https://{self.content_domain}"


settings = Settings()
