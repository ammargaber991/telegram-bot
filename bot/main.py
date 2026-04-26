from __future__ import annotations

import asyncio
import logging
import time

from telegram import Bot
from telegram.error import NetworkError, TelegramError
from telegram.ext import Application, ContextTypes
from telegram.request import HTTPXRequest

from bot.config import Settings, load_settings
from bot.database import Database
from bot.handlers import VISIBLE_COMMANDS, register_handlers


STARTUP_RETRY_ATTEMPTS = 5


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def build_request() -> HTTPXRequest:
    # Always disable environment proxy inheritance for direct Telegram API calls.
    return HTTPXRequest(proxy=None, httpx_kwargs={"trust_env": False})


async def verify_telegram_connectivity(token: str, request: HTTPXRequest, logger: logging.Logger) -> None:
    backoff_seconds = 1
    for attempt in range(1, STARTUP_RETRY_ATTEMPTS + 1):
        bot = Bot(token=token, request=request)
        try:
            me = await bot.get_me()
            logger.info("Telegram API connection verified for @%s (id=%s)", me.username, me.id)
            return
        except NetworkError as exc:
            logger.warning(
                "Telegram connectivity check failed (attempt %s/%s): %s",
                attempt,
                STARTUP_RETRY_ATTEMPTS,
                exc,
            )
            if attempt == STARTUP_RETRY_ATTEMPTS:
                raise
            await asyncio.sleep(backoff_seconds)
            backoff_seconds *= 2
        finally:
            await bot.shutdown()


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.getLogger(__name__).exception("Unhandled update error", exc_info=context.error)


def create_application(settings: Settings, db: Database, request: HTTPXRequest) -> Application:
    app = Application.builder().token(settings.bot_token).request(request).build()
    app.bot_data["db"] = db
    app.bot_data["owner_id"] = settings.owner_telegram_id
    app.bot_data["max_warns"] = settings.max_warns
    app.bot_data["default_language"] = settings.default_language

    register_handlers(app)
    app.add_error_handler(on_error)

    async def post_init(application: Application) -> None:
        await application.bot.set_my_commands(VISIBLE_COMMANDS)

    app.post_init = post_init
    return app


def ensure_startup_event_loop() -> None:
    """Ensure a current event loop exists for libraries using get_event_loop()."""
    asyncio.set_event_loop(asyncio.new_event_loop())


def run_connectivity_check(token: str, request: HTTPXRequest, logger: logging.Logger) -> None:
    """Run async connectivity check using an explicitly managed event loop (Py3.11 safe)."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(verify_telegram_connectivity(token, request, logger))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def run_bot_forever(settings: Settings) -> None:
    logger = logging.getLogger(__name__)
    db = Database(settings.database_path)

    reconnect_sleep = 5
    while True:
        request = build_request()

        try:
            run_connectivity_check(settings.bot_token, request, logger)
            ensure_startup_event_loop()

            app = create_application(settings, db, request)
            logger.info("Starting polling loop")
            app.run_polling(drop_pending_updates=True, bootstrap_retries=5)
            # If polling exits without exception, restart after a short delay.
            logger.warning("Polling loop exited unexpectedly; restarting in %ss", reconnect_sleep)
        except NetworkError as exc:
            logger.error("Network issue while running bot: %s", exc)
        except TelegramError as exc:
            logger.error("Fatal Telegram API error (check BOT_TOKEN/settings): %s", exc)
            return
        except Exception:
            logger.exception("Unexpected fatal error in bot runtime")

        logger.info("Reconnecting in %ss", reconnect_sleep)
        time.sleep(reconnect_sleep)
        reconnect_sleep = min(reconnect_sleep * 2, 60)


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    run_bot_forever(settings)


if __name__ == "__main__":
    main()
