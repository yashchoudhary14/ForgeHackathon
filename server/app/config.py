from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/adhikaar"
    # Neon WSS uses HTTPS port 443, including on port-restricted Spaces.
    database_transport: Literal["auto", "tcp", "websocket"] = "auto"

    gemini_api_key: str = ""
    # "vertex" bills gemini to a google cloud project (free trial credits work there, not on ai studio keys)
    gemini_backend: str = "aistudio"
    gcp_project: str = ""
    gcp_location: str = "global"
    # either a vertex api key (console > credentials > api key bound to a service account) ...
    vertex_api_key: str = ""
    # ... or a credentials json (service account or gcloud user login): file path or the json itself
    # empty = default credentials (gcloud auth application-default login, or the cloud run service account)
    gcp_credentials: str = ""
    gemini_model: str = "gemini-3.5-flash"
    gemini_fallback_models: str = "gemini-3.6-flash,gemini-3.5-flash-lite"
    gemini_model_pool: str = (
        "gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash,"
        "gemini-3-flash-preview,gemini-3.5-flash-lite,gemini-3.1-flash-lite"
    )
    gemini_rpm: int = Field(default=12, ge=1)
    gemini_model_rpm: dict[str, Annotated[int, Field(ge=1)]] = Field(default_factory=dict)
    gemini_queue_timeout: float = Field(default=45, gt=0)
    gemini_call_timeout: float = Field(default=25, gt=0)
    gemini_probe_timeout: float = Field(default=10, gt=0)
    llm_cache_ttl_hours: float = Field(default=24, gt=0)
    # browser loop makes ~30 calls per run, latency matters more than depth there
    agent_model: str = "gemini-3.6-flash"
    gemini_embed_model: str = "gemini-embedding-001"
    embed_dim: int = 768

    sarvam_api_key: str = ""
    profile_secret: str = ""

    client_origin: str = "http://localhost:5173"
    agent_headless: bool = True
    agent_allowed_domains: str = "gov.in,nic.in"
    storage_dir: str = "storage"

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.gemini_fallback_models.split(",") if m.strip()]

    @property
    def model_pool(self) -> list[str]:
        return list(dict.fromkeys(m.strip().removeprefix("models/")
                                  for m in self.gemini_model_pool.split(",") if m.strip()))

    @property
    def allowed_domains(self) -> list[str]:
        return [d.strip() for d in self.agent_allowed_domains.split(",") if d.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
