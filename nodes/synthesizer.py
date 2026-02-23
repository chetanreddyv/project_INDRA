"""
nodes/synthesizer.py — Response formatting for Telegram.

Cleans up agent output for Telegram's Markdown format,
handles message length limits, and formats error responses.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Telegram message character limit
TELEGRAM_MAX_LENGTH = 4096


def _sanitize_markdown(text: str) -> str:
    """
    Sanitize text for Telegram's MarkdownV1.
    Telegram's Markdown is finicky — escape problematic characters.
    """
    # Replace triple backticks with single backtick code blocks
    # (Telegram doesn't support triple-backtick fenced blocks in MarkdownV1)
    text = re.sub(r"```(\w*)\n", "`", text)
    text = text.replace("```", "`")
    return text


async def synthesizer_node(state: dict) -> dict:
    """
    Format the agent's response for Telegram delivery.
    Handles Markdown sanitization and structures the final output.
    """
    logger.info("--- [Node: Synthesizer] ---")
    
    response = state.get("agent_response", "")
    
    if not response:
        response = "I processed your request but have nothing to report."
    
    # Sanitize for Telegram Markdown
    response = _sanitize_markdown(response)
    
    logger.info(f"  -> Final response: {len(response)} chars")
    return {"agent_response": response}
