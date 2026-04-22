from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Domains
    oob_domain: str = "oob.example.com"
    content_domain: str = "content.example.com"
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

    # Azure AI Foundry
    foundry_endpoint: str = ""  # e.g. https://my-model.eastus.models.ai.azure.com
    foundry_api_key: str = ""
    foundry_model: str = ""  # optional — some endpoints require model name

    # Callback URL scheme — "http" if OOB domain has no TLS cert
    callback_scheme: str = "https"

    # Set at runtime after interactsh registration
    interactsh_correlation_id: str = ""
    interactsh_nonce: str = ""

    @property
    def callback_base(self) -> str:
        if self.interactsh_correlation_id:
            # Subdomain must be >= 33 chars: correlation_id (20) + nonce (14) = 34
            # Note: interactsh extracts the FIRST 20 chars as correlation ID
            return f"{self.callback_scheme}://{self.interactsh_correlation_id}{self.interactsh_nonce}.{self.oob_domain}"
        return f"{self.callback_scheme}://{self.oob_domain}"

    @property
    def content_base(self) -> str:
        return f"https://{self.content_domain}"


settings = Settings()
