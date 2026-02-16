"""Configuration from environment variables."""
import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # Required
    telegram_bot_token: str = ""
    openrouter_api_key: str = ""
    webhook_url: str = ""  # e.g. https://your-app.railway.app

    # Telegram
    allowed_user_ids: list[int] = field(default_factory=list)

    # Storage
    data_dir: str = "/data"

    # Models
    chat_model: str = "anthropic/claude-sonnet-4-5"
    synthesis_model: str = "anthropic/claude-haiku-4-5"
    thinking_model: str = "anthropic/claude-haiku-4-5"

    # Autonomy
    autonomy_interval_minutes: int = 60
    quiet_hours_start: int = 23  # UTC
    quiet_hours_end: int = 8    # UTC
    proactive_cooldown_hours: int = 2
    max_proactive_messages_per_day: int = 3

    # Session
    session_timeout_minutes: int = 30
    synthesis_message_threshold: int = 10  # messages (5 exchanges)

    @classmethod
    def from_env(cls) -> "Config":
        user_ids_str = os.getenv("ALLOWED_USER_IDS", "")
        allowed_ids = [int(x.strip()) for x in user_ids_str.split(",") if x.strip()]

        return cls(
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            openrouter_api_key=os.environ["OPENROUTER_API_KEY"],
            webhook_url=os.getenv("WEBHOOK_URL", ""),
            allowed_user_ids=allowed_ids,
            data_dir=os.getenv("DATA_DIR", "/data"),
            chat_model=os.getenv("CHAT_MODEL", "anthropic/claude-sonnet-4-5"),
            synthesis_model=os.getenv("SYNTHESIS_MODEL", "anthropic/claude-haiku-4-5"),
            thinking_model=os.getenv("THINKING_MODEL", "anthropic/claude-haiku-4-5"),
            autonomy_interval_minutes=int(os.getenv("AUTONOMY_INTERVAL_MINUTES", "60")),
            quiet_hours_start=int(os.getenv("QUIET_HOURS_START", "23")),
            quiet_hours_end=int(os.getenv("QUIET_HOURS_END", "8")),
            proactive_cooldown_hours=int(os.getenv("PROACTIVE_COOLDOWN_HOURS", "2")),
            max_proactive_messages_per_day=int(os.getenv("MAX_PROACTIVE_MESSAGES_PER_DAY", "3")),
            session_timeout_minutes=int(os.getenv("SESSION_TIMEOUT_MINUTES", "30")),
            synthesis_message_threshold=int(os.getenv("SYNTHESIS_MESSAGE_THRESHOLD", "10")),
        )

    @property
    def memory_dir(self) -> str:
        return os.path.join(self.data_dir, "memory")

    @property
    def workspace_dir(self) -> str:
        return os.path.join(self.data_dir, "workspace")
