"""
telegram.py — Telegram Bot API client.

Handles sending messages, inline keyboards (HITL buttons),
and callback query acknowledgement.
"""

import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"


class TelegramClient:
    """Async Telegram Bot API wrapper."""

    def __init__(self, token: str):
        self.token = token
        self.base_url = TELEGRAM_API.format(token=token)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _call(self, method: str, **kwargs) -> dict:
        """Make a Telegram Bot API call."""
        client = await self._get_client()
        url = f"{self.base_url}/{method}"
        resp = await client.post(url, json=kwargs)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            logger.error(f"Telegram API error: {data}")
        return data

    # ── Messaging ─────────────────────────────────────────────

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: Optional[str] = "Markdown",
        reply_markup: Optional[dict] = None,
    ) -> dict:
        """Send a text message. Splits into chunks if > 4096 chars."""
        MAX_LEN = 4096
        if len(text) <= MAX_LEN:
            kwargs = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
            if reply_markup:
                kwargs["reply_markup"] = reply_markup
            try:
                return await self._call("sendMessage", **kwargs)
            except httpx.HTTPStatusError as e:
                if parse_mode and e.response.status_code == 400:
                    logger.warning(f"Markdown parse failed, retrying without parse_mode: {e}")
                    kwargs.pop("parse_mode", None)
                    return await self._call("sendMessage", **kwargs)
                raise

        # Split long messages
        chunks = [text[i : i + MAX_LEN] for i in range(0, len(text), MAX_LEN)]
        result = None
        for i, chunk in enumerate(chunks):
            kwargs = {"chat_id": chat_id, "text": chunk, "parse_mode": parse_mode}
            # Attach buttons only to last chunk
            if reply_markup and i == len(chunks) - 1:
                kwargs["reply_markup"] = reply_markup
            try:
                result = await self._call("sendMessage", **kwargs)
            except httpx.HTTPStatusError as e:
                if parse_mode and e.response.status_code == 400:
                    logger.warning(f"Markdown parse failed for chunk, retrying without parse_mode: {e}")
                    kwargs.pop("parse_mode", None)
                    result = await self._call("sendMessage", **kwargs)
                else:
                    raise
        return result

    async def send_typing_action(self, chat_id: int) -> dict:
        """Show 'typing...' indicator."""
        return await self._call("sendChatAction", chat_id=chat_id, action="typing")

    # ── HITL Approval Buttons ────────────────────────────────

    async def send_approval_buttons(
        self,
        chat_id: int,
        action_summary: str,
        thread_id: str,
    ) -> dict:
        """
        Send a message with Approve / Reject / Edit inline keyboard.
        callback_data encodes the thread_id so we can resume the right graph.
        """
        text = (
            f"🔐 **Action Requires Approval**\n\n"
            f"{action_summary}\n\n"
            f"Choose an action below:"
        )
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve", "callback_data": f"approve:{thread_id}"},
                    {"text": "❌ Reject", "callback_data": f"reject:{thread_id}"},
                ],
                [
                    {"text": "✏️ Edit", "callback_data": f"edit:{thread_id}"},
                ],
            ]
        }
        return await self.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    async def answer_callback_query(
        self, callback_query_id: str, text: str = ""
    ) -> dict:
        """Acknowledge a button press so the spinner goes away."""
        return await self._call(
            "answerCallbackQuery", callback_query_id=callback_query_id, text=text
        )

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: Optional[str] = "Markdown",
    ) -> dict:
        """Edit an existing message (e.g., to update after approval)."""
        return await self._call(
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=parse_mode,
        )

    # ── Polling (for local dev) ──────────────────────────────

    async def delete_webhook(self) -> dict:
        """Remove any existing webhook so polling works."""
        return await self._call("deleteWebhook")

    async def get_updates(self, offset: int = 0, timeout: int = 30) -> list[dict]:
        """
        Long-poll for updates from Telegram.
        Uses a longer httpx timeout since the Telegram long-poll itself takes `timeout` seconds.
        """
        try:
            client = await self._get_client()
            url = f"{self.base_url}/getUpdates"
            # httpx timeout must be longer than Telegram's long-poll timeout
            resp = await client.post(
                url,
                json={"offset": offset, "timeout": timeout},
                timeout=timeout + 10,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("result", [])
        except Exception as e:
            logger.error(f"Polling error: {e}")
            return []

