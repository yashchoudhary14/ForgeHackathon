from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/adhikaar"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    gemini_fallback_models: str = "gemini-3.6-flash,gemini-3.5-flash-lite"
    # browser loop makes ~30 calls per run, latency matters more than depth there
    agent_model: str = "gemini-3.6-flash"
    gemini_embed_model: str = "gemini-embedding-001"
    embed_dim: int = 768

    sarvam_api_key: str = ""
    profile_secret: str = ""

    client_origin: str = "http://localhost:5173"
    agent_headless: bool = True
    agent_browser_channel: str | None = None  # e.g. chrome; default is bundled Chromium
    agent_allowed_domains: str = "gov.in,nic.in"
    storage_dir: str = "storage"

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.gemini_fallback_models.split(",") if m.strip()]

    @property
    def allowed_domains(self) -> list[str]:
        return [d.strip() for d in self.agent_allowed_domains.split(",") if d.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
