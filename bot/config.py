from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    owner_telegram_id: int
    database_path: str
    log_level: str
    default_language: str
    max_warns: int



def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be numeric") from exc



def load_settings() -> Settings:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    owner_raw = os.getenv("OWNER_TELEGRAM_ID", "").strip() or os.getenv("OWNER_ID", "").strip()
    database_path = os.getenv("DATABASE_PATH", "./design_lab_bot.db").strip()
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    default_language = os.getenv("DEFAULT_LANGUAGE", "ar_en").strip().lower() or "ar_en"
    max_warns = _int_env("MAX_WARNS", 3)

    if not bot_token:
        raise RuntimeError("Missing BOT_TOKEN environment variable")
    if not owner_raw:
        raise RuntimeError("Missing OWNER_TELEGRAM_ID (or OWNER_ID) environment variable")

    try:
        owner_telegram_id = int(owner_raw)
    except ValueError as exc:
        raise RuntimeError("OWNER_TELEGRAM_ID/OWNER_ID must be numeric") from exc

    return Settings(
        bot_token=bot_token,
        owner_telegram_id=owner_telegram_id,
        database_path=database_path,
        log_level=log_level,
        default_language=default_language,
        max_warns=max_warns,
    )
