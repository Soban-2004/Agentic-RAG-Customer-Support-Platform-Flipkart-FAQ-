"""Validated operational bounds, with no implicit trusted proxy headers."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeSettings:
    production: bool
    origins: frozenset[str]
    turn_timeout: int
    idle_timeout: int
    max_concurrent: int
    max_frame_bytes: int
    max_connections: int
    chat_per_hour: int
    shared_cache: bool


def _integer(name, default, low, high):
    value = int(os.getenv(name, str(default)))
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def settings():
    production = os.getenv("APP_ENV", "development") == "production"
    origins = frozenset(
        x.strip().rstrip("/")
        for x in os.getenv("TRUSTED_ORIGINS", "").split(",")
        if x.strip()
    )
    return RuntimeSettings(
        production,
        origins,
        _integer("TURN_TIMEOUT_SECONDS", 90, 5, 300),
        _integer("WS_IDLE_TIMEOUT_SECONDS", 300, 10, 3600),
        _integer("MAX_CONCURRENT_TURNS", 4, 1, 32),
        _integer("MAX_FRAME_BYTES", 6_000_000, 16_384, 8_000_000),
        _integer("MAX_CONNECTIONS", 50, 1, 1000),
        _integer("CHAT_PER_HOUR", 60, 1, 1000),
        os.getenv("ENABLE_SHARED_FAQ_CACHE", "false").lower() == "true",
    )


def validate_production():
    config = settings()
    for name, default, low, high in [
        ("DAILY_TURN_LIMIT", 500, 1, 100000),
        ("DAILY_IMAGE_LIMIT", 30, 1, 10000),
        ("DAILY_RESERVED_TOKEN_LIMIT", 10000000, 100000, 1000000000),
        ("ACCOUNT_DAILY_RESERVED_TOKEN_LIMIT", 2000000, 100000, 1000000000),
    ]:
        _integer(name, default, low, high)
    if _integer("DB_POOL_SIZE", 12, 4, 128) < 2 * config.max_concurrent + 2:
        raise ValueError("DB_POOL_SIZE must be at least 2*MAX_CONCURRENT_TURNS+2")
    if config.production:
        if (
            os.getenv("ENABLE_CONTENT_TRACING", "false").lower() == "true"
            and os.getenv("ENABLE_DEMO", "true").lower() != "false"
        ):
            raise ValueError("Disable the public demo before enabling content tracing")
        if len(os.getenv("JWT_SECRET", "")) < 32 or os.getenv(
            "JWT_SECRET", ""
        ).startswith(("replace-", "test-only")):
            raise ValueError(
                "Production JWT_SECRET must contain at least 32 characters"
            )
        if not config.origins or any(
            not x.startswith("https://") for x in config.origins
        ):
            raise ValueError("Production TRUSTED_ORIGINS must list exact HTTPS origins")
        if not os.getenv("COHERE_API_KEY") or not os.getenv("QDRANT_URL"):
            raise ValueError("Production requires COHERE_API_KEY and remote QDRANT_URL")
    if os.getenv("BUSINESS_BACKEND", "demo") != "demo":
        raise ValueError(
            "Only the explicitly simulated business backend is implemented; a real connector must enforce actor/resource authorization"
        )
    return config
