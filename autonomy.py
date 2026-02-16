"""Autonomy loop: think → decide → act/message."""
import logging
from datetime import datetime, timezone

from telegram.ext import ContextTypes

from config import Config
from memory import MemoryManager
from claude_client import ClaudeClient

logger = logging.getLogger(__name__)


class AutonomyLoop:
    def __init__(self, config: Config, memory: MemoryManager, claude: ClaudeClient):
        self.config = config
        self.memory = memory
        self.claude = claude
        self.bot = None  # Set after bot is created

    def set_bot(self, bot):
        """Set the bot reference for sending proactive messages."""
        self.bot = bot

    def _in_quiet_hours(self) -> bool:
        hour = datetime.now(timezone.utc).hour
        start = self.config.quiet_hours_start
        end = self.config.quiet_hours_end

        if start > end:
            # Wraps midnight, e.g. 23-8
            return hour >= start or hour < end
        else:
            return start <= hour < end

    def _cooldown_active(self) -> bool:
        if self.bot is None or self.bot.last_message_time is None:
            return False
        elapsed = (datetime.now(timezone.utc) - self.bot.last_message_time).total_seconds()
        return elapsed < self.config.proactive_cooldown_hours * 3600

    def _daily_limit_reached(self) -> bool:
        if self.bot is None:
            return False
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.bot.proactive_messages_date != today:
            return False
        return self.bot.proactive_messages_today >= self.config.max_proactive_messages_per_day

    def _hours_since_last_message(self) -> float:
        if self.bot is None or self.bot.last_message_time is None:
            return 999.0
        elapsed = (datetime.now(timezone.utc) - self.bot.last_message_time).total_seconds()
        return elapsed / 3600

    async def run_cycle(self, context: ContextTypes.DEFAULT_TYPE):
        """Run one autonomy cycle. Called by PTB JobQueue."""
        try:
            logger.info("Autonomy cycle starting...")

            # Gate 1: Quiet hours
            if self._in_quiet_hours():
                logger.info("Autonomy cycle skipped: quiet hours")
                return

            # Phase 1: Think (cheap, Haiku)
            lightweight_context = self.memory.load_lightweight_context()
            current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            hours_since = self._hours_since_last_message()

            decision = await self.claude.think(
                lightweight_context, current_time, hours_since
            )

            # Handle journal entry
            journal = decision.get("journal_entry")
            if journal:
                path = self.memory.add_journal_entry(journal)
                logger.info(f"Journal entry written: {path}")

            # Handle queue updates
            queue_updates = decision.get("queue_updates")
            if queue_updates:
                self.memory.update_file("queue.md", queue_updates)
                logger.info("Queue updated by autonomy loop")

            # Phase 2: Maybe send proactive message
            should_message = decision.get("should_message", False)
            if not should_message:
                logger.info(f"Autonomy cycle complete: no message. Reasoning: {decision.get('reasoning', 'none')}")
                return

            # Gate 2: Cooldown
            if self._cooldown_active():
                logger.info("Proactive message suppressed: cooldown active")
                return

            # Gate 3: Daily limit
            if self._daily_limit_reached():
                logger.info("Proactive message suppressed: daily limit reached")
                return

            # Compose message (quality, Sonnet)
            trigger_reason = decision.get("message_reason", "autonomy loop trigger")
            full_context = self.memory.load_full_context()
            message = await self.claude.compose_proactive_message(
                full_context, trigger_reason, current_time
            )

            # Send to all allowed users
            if self.bot and self.config.allowed_user_ids:
                for user_id in self.config.allowed_user_ids:
                    try:
                        await self.bot.send_proactive_message(user_id, message)
                        logger.info(f"Proactive message sent to {user_id}")
                    except Exception as e:
                        logger.error(f"Failed to send proactive message to {user_id}: {e}")
            else:
                logger.warning("No bot or no allowed user IDs — proactive message not sent")

        except Exception as e:
            logger.error(f"Autonomy cycle failed: {e}", exc_info=True)
