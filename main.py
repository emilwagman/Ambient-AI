"""Entry point: Starlette webhook server + PTB Application + autonomy loop."""
import logging
import os
import sys
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

import uvicorn
from telegram import Update
from telegram.ext import Application, ApplicationBuilder

from config import Config
from memory import MemoryManager
from claude_client import ClaudeClient
from bot import AmbientBot
from autonomy import AutonomyLoop

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Global references set during startup
ptb_app: Application = None
ambient_bot: AmbientBot = None


async def telegram_webhook(request: Request):
    """Handle incoming Telegram webhook updates."""
    try:
        data = await request.json()
        update = Update.de_json(data, ptb_app.bot)
        await ptb_app.process_update(update)
        return PlainTextResponse("ok")
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return PlainTextResponse("error", status_code=500)


async def health_check(request: Request):
    """Health check endpoint."""
    return JSONResponse({"status": "ok", "mode": "webhook"})


@asynccontextmanager
async def lifespan(app):
    """Starlette lifespan: start and stop PTB application."""
    global ptb_app, ambient_bot

    config = Config.from_env()
    memory = MemoryManager(config.data_dir)
    claude = ClaudeClient(config)

    # Build PTB Application (no updater — we use Starlette for webhooks)
    ptb_app = (
        ApplicationBuilder()
        .token(config.telegram_bot_token)
        .updater(None)
        .build()
    )

    # Create and register bot handlers
    ambient_bot = AmbientBot(config, memory, claude)
    ambient_bot.register_handlers(ptb_app)

    # Store PTB bot reference so proactive messages reuse it
    ambient_bot.set_ptb_bot(ptb_app.bot)

    # Create and register autonomy loop
    autonomy = AutonomyLoop(config, memory, claude)
    autonomy.set_bot(ambient_bot)

    # Initialize and start PTB
    await ptb_app.initialize()
    await ptb_app.start()

    # Register autonomy loop with JobQueue
    ptb_app.job_queue.run_repeating(
        autonomy.run_cycle,
        interval=config.autonomy_interval_minutes * 60,
        first=config.autonomy_interval_minutes * 60,
        name="autonomy_loop",
    )

    # Set webhook
    webhook_url = f"{config.webhook_url}/telegram"
    await ptb_app.bot.set_webhook(url=webhook_url)
    logger.info(f"Webhook set to {webhook_url}")
    logger.info("Ambient Claude started (webhook mode)")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await ptb_app.bot.delete_webhook()
    await ptb_app.stop()
    await ptb_app.shutdown()


def run_polling(config: Config):
    """Run in polling mode for local development."""
    memory = MemoryManager(config.data_dir)
    claude = ClaudeClient(config)

    app = ApplicationBuilder().token(config.telegram_bot_token).build()

    bot = AmbientBot(config, memory, claude)
    bot.register_handlers(app)

    autonomy = AutonomyLoop(config, memory, claude)
    autonomy.set_bot(bot)

    # Register autonomy loop
    app.job_queue.run_repeating(
        autonomy.run_cycle,
        interval=config.autonomy_interval_minutes * 60,
        first=config.autonomy_interval_minutes * 60,
        name="autonomy_loop",
    )

    logger.info("Ambient Claude started (polling mode)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    config = Config.from_env()

    if "--polling" in sys.argv:
        run_polling(config)
    else:
        port = int(os.getenv("PORT", "8080"))
        starlette_app = Starlette(
            routes=[
                Route("/telegram", telegram_webhook, methods=["POST"]),
                Route("/health", health_check, methods=["GET"]),
            ],
            lifespan=lifespan,
        )
        uvicorn.run(starlette_app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
