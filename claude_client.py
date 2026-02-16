"""OpenRouter API wrapper for chat, synthesis, and thinking."""
import json
import logging

from openai import AsyncOpenAI

from config import Config
from prompts import (
    chat_system_prompt,
    synthesis_prompt,
    autonomy_thinking_prompt,
    proactive_message_prompt,
)

logger = logging.getLogger(__name__)


class ClaudeClient:
    def __init__(self, config: Config):
        self.config = config
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.openrouter_api_key,
        )

    async def chat(self, memory_context: str, messages: list[dict]) -> str:
        """User-facing conversation using Sonnet."""
        system_text = chat_system_prompt(memory_context)

        response = await self.client.chat.completions.create(
            model=self.config.chat_model,
            max_tokens=2048,
            messages=[
                {"role": "system", "content": system_text},
                *messages,
            ],
        )

        return response.choices[0].message.content

    async def synthesize(self, memory_context: str, conversation: str) -> dict:
        """Memory synthesis using cheap model. Returns dict of file updates."""
        prompt = synthesis_prompt(memory_context, conversation)

        response = await self.client.chat.completions.create(
            model=self.config.synthesis_model,
            max_tokens=4096,
            messages=[
                {"role": "user", "content": prompt},
            ],
        )

        text = response.choices[0].message.content
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        try:
            result = json.loads(text.strip())
            logger.info(f"Synthesis reasoning: {result.get('reasoning', 'none')}")
            return result.get("updates", {})
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse synthesis response: {e}\nText: {text[:500]}")
            return {}

    async def think(self, lightweight_context: str, current_time: str, hours_since_last_message: float) -> dict:
        """Autonomy thinking using cheap model. Returns decision dict."""
        prompt = autonomy_thinking_prompt(lightweight_context, current_time, hours_since_last_message)

        response = await self.client.chat.completions.create(
            model=self.config.thinking_model,
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt},
            ],
        )

        text = response.choices[0].message.content
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        try:
            result = json.loads(text.strip())
            logger.info(f"Autonomy thinking: {result.get('reasoning', 'none')}")
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse thinking response: {e}\nText: {text[:500]}")
            return {"should_message": False, "reasoning": "Parse error"}

    async def compose_proactive_message(self, full_context: str, trigger_reason: str, current_time: str) -> str:
        """Compose a proactive message using quality model."""
        prompt = proactive_message_prompt(full_context, trigger_reason, current_time)

        response = await self.client.chat.completions.create(
            model=self.config.chat_model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Write your proactive message now."},
            ],
        )

        return response.choices[0].message.content
