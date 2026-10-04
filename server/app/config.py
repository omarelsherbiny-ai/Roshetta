# server/app/config.py
from pathlib import Path
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="allow",
    )

    PROJECT_NAME: str = "Roshetta Pharmacy System"
    VERSION: str = "0.1.0"
    SERVER_HOST: str = "127.0.0.1"
    SERVER_PORT: int = 8000
    SERVER_SECRET_KEY: str = ""
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    
    # Database: SQLite default for local zero-friction execution, or PostgreSQL
    DATABASE_URL: str = "sqlite+aiosqlite:///./roshetta.db"
    SEED_DEMO_DATA: bool = False
    
    # AI MicroMind workflow API. Off by default: general chat text is sent to an
    # external service only when server/.env sets BOTH of these values.
    MICROMIND_API_URL: str = ""
    USE_MICROMIND: bool = False

    # Let the MicroMind flow read this pharmacy's data through the /ai tools while it
    # answers a general chat message. Off by default. When on, the server sends the flow
    # a 5 minute read-only token for the signed-in user (never the user's own token).
    # Needs USE_MICROMIND and MICROMIND_API_URL, and a flow that accepts per-request
    # variables (see scripts/probe_micromind_override.py).
    AI_TOOLS_ENABLED: bool = False
    # A tool-using answer takes longer than a plain one (the flow calls /ai through the tunnel).
    AI_AGENT_TIMEOUT_SECONDS: float = 25.0

    # /api/chat rate limit per user and pharmacy. Counted in memory by each server
    # process, so with several workers the real ceiling is messages x workers.
    CHAT_RATE_LIMIT_MESSAGES: int = Field(default=20, ge=1)
    CHAT_RATE_LIMIT_WINDOW_SECONDS: float = Field(default=60.0, gt=0)

    # How long an assistant proposal (sale, expense, restock) stays confirmable. A proposal keeps
    # the prices it was drafted with, so an old one is refused at confirm and hidden from the
    # pending list; the person asks the assistant again. Hours, above 0.
    PENDING_ACTION_TTL_HOURS: float = Field(default=24.0, gt=0)

    # Addresses of reverse proxies or tunnels that sit in front of this server (comma
    # separated, exact IPs, for example 127.0.0.1 for a local ngrok agent). Only a request
    # whose direct peer is in this list may name the real client in X-Forwarded-For; for every
    # other peer the header is ignored. Empty (default) means no proxy is trusted.
    TRUSTED_PROXY_IPS: str = ""

    # Other LLM / AI Keys (Optional / Fallbacks)
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    
    # OCR Provider
    OCR_PROVIDER: str = "disabled"
    
    # Public HTTPS base of this server as MicroMind's OpenAPI Toolkit reaches it (for
    # example the tunnel URL, no trailing path). It goes into the `servers` entry of
    # /ai/openapi.json. Empty means a relative "/ai", which a toolkit may not resolve.
    AI_PUBLIC_URL: str = ""

    # Storage
    STORAGE_DRIVER: Literal["local"] = "local"
    STORAGE_LOCAL_DIR: str = "./uploads"

    @property
    def trusted_proxy_list(self) -> set[str]:
        return {address.strip() for address in self.TRUSTED_PROXY_IPS.split(",") if address.strip()}

    @property
    def allowed_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


settings = Settings()