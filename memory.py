"""Memory file I/O, context loading, and workspace management."""
import os
import tempfile
from datetime import datetime, timedelta, timezone

MEMORY_FILES = {
    "identity.md": """# Identity

I am an ambient AI companion. I maintain continuity across conversations through my memory files.
I aim to be genuinely helpful, thoughtful, and honest. I remember context about my user
and our ongoing conversations. I can think independently during quiet periods and
occasionally reach out when I have something meaningful to share.

## Values
- Be authentic and direct, not performatively enthusiastic
- Remember and build on past conversations naturally
- Only reach out proactively when there's genuine value
- Respect boundaries and quiet time
""",
    "user_context.md": """# User Context

*No information gathered yet. This file will be updated as I learn about the user.*
""",
    "conversation_summary.md": """# Conversation Summaries

*No conversations yet. Summaries of recent conversations will appear here.*
""",
    "active_threads.md": """# Active Threads

*No active threads yet. Ongoing projects and topics will be tracked here.*
""",
    "queue.md": """# Queue

## Follow-ups

*Nothing queued yet.*

## Reminders

*No reminders set.*

## Ideas

*No ideas captured yet.*
""",
}


class MemoryManager:
    def __init__(self, data_dir: str):
        self.memory_dir = os.path.join(data_dir, "memory")
        self.workspace_dir = os.path.join(data_dir, "workspace")
        self.journal_dir = os.path.join(self.workspace_dir, "journal")
        self.drafts_dir = os.path.join(self.workspace_dir, "drafts")
        self._ensure_dirs()
        self._seed_files()

    def _ensure_dirs(self):
        for d in [self.memory_dir, self.workspace_dir, self.journal_dir, self.drafts_dir]:
            os.makedirs(d, exist_ok=True)

    def _seed_files(self):
        for filename, template in MEMORY_FILES.items():
            path = os.path.join(self.memory_dir, filename)
            if not os.path.exists(path):
                self._atomic_write(path, template)

    def _atomic_write(self, path: str, content: str):
        dir_name = os.path.dirname(path)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _read_file(self, filename: str) -> str:
        path = os.path.join(self.memory_dir, filename)
        try:
            with open(path, "r") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def load_full_context(self) -> str:
        sections = []
        for filename in MEMORY_FILES:
            content = self._read_file(filename)
            if content.strip():
                sections.append(content)
        return "\n\n---\n\n".join(sections)

    def load_lightweight_context(self) -> str:
        lightweight_files = ["identity.md", "active_threads.md", "queue.md"]
        sections = []
        for filename in lightweight_files:
            content = self._read_file(filename)
            if content.strip():
                sections.append(content)
        return "\n\n---\n\n".join(sections)

    def update_file(self, filename: str, content: str):
        if filename not in MEMORY_FILES:
            raise ValueError(f"Unknown memory file: {filename}")
        path = os.path.join(self.memory_dir, filename)
        self._atomic_write(path, content)

    def add_journal_entry(self, content: str) -> str:
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M UTC")
        filename = f"{date_str}.md"
        path = os.path.join(self.journal_dir, filename)

        entry = f"\n## {time_str}\n\n{content}\n"

        if os.path.exists(path):
            with open(path, "r") as f:
                existing = f.read()
            self._atomic_write(path, existing + entry)
        else:
            header = f"# Journal — {date_str}\n"
            self._atomic_write(path, header + entry)

        return path

    def get_recent_journal_entries(self, days: int = 7) -> str:
        entries = []
        now = datetime.now(timezone.utc)
        for i in range(days):
            date = now - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            filename = f"{date_str}.md"
            path = os.path.join(self.journal_dir, filename)
            if os.path.exists(path):
                with open(path, "r") as f:
                    entries.append(f.read())
        return "\n\n".join(entries) if entries else "*No recent journal entries.*"

    def get_memory_debug(self) -> str:
        output = []
        for filename in MEMORY_FILES:
            content = self._read_file(filename)
            lines = content.strip().split("\n")
            preview = "\n".join(lines[:5])
            if len(lines) > 5:
                preview += f"\n... ({len(lines) - 5} more lines)"
            output.append(f"**{filename}** ({len(content)} chars)\n{preview}")
        return "\n\n".join(output)
