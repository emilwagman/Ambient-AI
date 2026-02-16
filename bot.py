"""Telegram bot handlers, session management, and synthesis triggers."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import Config
from memory import MemoryManager
from claude_client import ClaudeClient

logger = logging.getLogger(__name__)


def split_message(text: str, max_len: int = 4096) -> list[str]:
    """Split a message into chunks respecting Telegram's character limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        # Try to split at paragraph boundary
        split_at = text.rfind("\n\n", 0, max_len)
        if split_at == -1:
            # Try sentence boundary
            split_at = text.rfind(". ", 0, max_len)
            if split_at != -1:
                split_at += 1  # Include the period
        if split_at == -1:
            # Try any newline
            split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            # Hard split
            split_at = max_len

        chunks.append(text[:split_at].rstrip())
        text = text[split_at:].lstrip()

    return chunks


class Session:
    """Tracks a conversation session with a user."""

    def __init__(self):
        self.messages: list[dict] = []  # {"role": "user"/"assistant", "content": str}
        self.last_activity: datetime = datetime.now(timezone.utc)
        self.message_count: int = 0

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        self.last_activity = datetime.now(timezone.utc)
        self.message_count += 1

    def is_expired(self, timeout_minutes: int) -> bool:
        elapsed = (datetime.now(timezone.utc) - self.last_activity).total_seconds()
        return elapsed > timeout_minutes * 60

    def get_conversation_text(self) -> str:
        lines = []
        for msg in self.messages:
            prefix = "User" if msg["role"] == "user" else "Claude"
            lines.append(f"{prefix}: {msg['content']}")
        return "\n\n".join(lines)

    def clear(self):
        self.messages.clear()
        self.message_count = 0
        self.last_activity = datetime.now(timezone.utc)


class AmbientBot:
    def __init__(self, config: Config, memory: MemoryManager, claude: ClaudeClient):
        self.config = config
        self.memory = memory
        self.claude = claude
        self.sessions: dict[int, Session] = {}
        self.last_message_time: Optional[datetime] = None
        self.proactive_messages_today: int = 0
        self.proactive_messages_date: Optional[str] = None
        self._synthesis_lock = asyncio.Lock()
        self._ptb_bot = None  # Set via set_ptb_bot() to reuse for proactive messages

    def set_ptb_bot(self, bot):
        """Store the PTB bot instance for sending proactive messages."""
        self._ptb_bot = bot

    def _is_authorized(self, user_id: int) -> bool:
        if not self.config.allowed_user_ids:
            return True
        return user_id in self.config.allowed_user_ids

    def _get_session(self, user_id: int) -> Session:
        if user_id not in self.sessions:
            self.sessions[user_id] = Session()
        return self.sessions[user_id]

    async def _maybe_synthesize(self, user_id: int, session: Session):
        """Run memory synthesis if threshold reached."""
        async with self._synthesis_lock:
            try:
                memory_context = self.memory.load_full_context()
                conversation_text = session.get_conversation_text()
                updates = await self.claude.synthesize(memory_context, conversation_text)

                for filename, content in updates.items():
                    if filename != "identity.md":
                        self.memory.update_file(filename, content)
                        logger.info(f"Updated memory file: {filename}")

            except Exception as e:
                logger.error(f"Synthesis failed: {e}")

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            return

        session = self._get_session(user_id)
        user_text = update.message.text

        # Check for session expiry — synthesize old session first
        if session.messages and session.is_expired(self.config.session_timeout_minutes):
            logger.info(f"Session expired for user {user_id}, synthesizing...")
            await self._maybe_synthesize(user_id, session)
            session.clear()

        # Add user message
        session.add_message("user", user_text)

        # Get response
        try:
            memory_context = self.memory.load_full_context()
            response = await self.claude.chat(memory_context, session.messages)
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            response = "I'm having trouble thinking right now. Give me a moment and try again."

        # Add assistant response
        session.add_message("assistant", response)
        self.last_message_time = datetime.now(timezone.utc)

        # Send response (handle long messages)
        for chunk in split_message(response):
            await update.message.reply_text(chunk)

        # Check synthesis threshold
        if session.message_count >= self.config.synthesis_message_threshold:
            logger.info(f"Message threshold reached for user {user_id}, synthesizing...")
            asyncio.create_task(self._maybe_synthesize(user_id, session))
            session.message_count = 0  # Reset counter

    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            return

        await update.message.reply_text(
            "Hey! I'm your ambient AI companion. I maintain memory across our conversations "
            "and I'm always here when you need me.\n\n"
            "Just message me naturally — I'll remember our conversations.\n\n"
            "Commands:\n"
            "/memory — see what I remember\n"
            "/forget — clear current session"
        )

    async def _memory_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            return

        debug = self.memory.get_memory_debug()
        for chunk in split_message(debug):
            await update.message.reply_text(chunk)

    async def _forget_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            return

        session = self._get_session(user_id)
        session.clear()
        await update.message.reply_text("Session cleared. My long-term memory is still intact though.")

    def register_handlers(self, app: Application):
        app.add_handler(CommandHandler("start", self._start_command))
        app.add_handler(CommandHandler("memory", self._memory_command))
        app.add_handler(CommandHandler("forget", self._forget_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

    async def send_proactive_message(self, user_id: int, text: str):
        """Send a proactive message to a user. Called by the autonomy loop."""
        if self._ptb_bot is None:
            logger.error("Cannot send proactive message: no bot reference set")
            return

        for chunk in split_message(text):
            await self._ptb_bot.send_message(chat_id=user_id, text=chunk)

        self.last_message_time = datetime.now(timezone.utc)

        # Track daily count
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.proactive_messages_date != today:
            self.proactive_messages_today = 0
            self.proactive_messages_date = today
        self.proactive_messages_today += 1

        logger.info(f"Sent proactive message to {user_id} ({self.proactive_messages_today} today)")
