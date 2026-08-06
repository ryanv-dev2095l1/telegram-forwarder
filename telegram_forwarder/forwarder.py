import asyncio
import collections
import logging
import time
from typing import Deque, Optional, Set, Tuple

import httpx
from telethon import TelegramClient, events

from telegram_forwarder.config import Config
from telegram_forwarder.metrics import Metrics
from telegram_forwarder.rules import evaluate_rules

log = logging.getLogger("tg_fwd.daemon")


class ForwarderDaemon:
    """Main runner listening to Telethon streams and fanning out matched messages."""

    def __init__(self, config: Config, metrics: Optional[Metrics] = None):
        self.cfg = config
        self.metrics = metrics or Metrics()
        self.client = TelegramClient(
            self.cfg.session_name,
            self.cfg.api_id,
            self.cfg.api_hash
        )
        self._http = httpx.AsyncClient(timeout=10.0)
        # Deduplicate forwards when channels mirror each other rapidly
        self._seen_history: Deque[Tuple[int, int]] = collections.deque(maxlen=1000)
        self._seen_set: Set[Tuple[int, int]] = set()

    def _is_duplicate(self, chat_id: int, msg_id: int) -> bool:
        key = (chat_id, msg_id)
        if key in self._seen_set:
            return True
        if len(self._seen_history) >= 1000:
            evicted = self._seen_history.popleft()
            self._seen_set.discard(evicted)
        self._seen_history.append(key)
        self._seen_set.add(key)
        return False

    async def start(self) -> None:
        await self.client.start(phone=self.cfg.phone)
        me = await self.client.get_me()
        log.info("logged in as %s (@%s)", me.first_name, me.username or "none")

        watched = self.cfg.watched_channel_ids
        log.info("registering message listener for %d channel(s)", len(watched))

        @self.client.on(events.NewMessage(chats=watched))
        async def _on_message(event: events.NewMessage.Event) -> None:
            await self.process_event(event)

        await self.client.run_until_disconnected()

    # FIXME: grouped media (albums) arrive as separate events with same grouped_id
    # Need to buffer by grouped_id for ~500ms if we want to forward clean media sets.
    async def process_event(self, event: events.NewMessage.Event) -> None:
        t0 = time.monotonic()
        chat = await event.get_chat()
        chat_id = getattr(chat, "id", 0)
        str_chat_id = str(chat_id)
        self.metrics.received.labels(channel_id=str_chat_id).inc()

        msg_id = getattr(event.message, "id", 0)
        if self._is_duplicate(chat_id, msg_id):
            self.metrics.dropped.labels(channel_id=str_chat_id, reason="duplicate").inc()
            return

        raw_text = event.raw_text or ""
        # Pure link messages sometimes have text only in the web preview
        if not raw_text.strip() and event.message.media:
            web = getattr(event.message.media, "webpage", None)
            if web:
                raw_text = getattr(web, "description", "") or getattr(web, "title", "") or ""

        if not raw_text.strip():
            self.metrics.dropped.labels(channel_id=str_chat_id, reason="empty").inc()
            return

        # print(f"DEBUG: msg from {chat_id}: {raw_text[:40]}")

        matches = evaluate_rules(self.cfg.rules, raw_text, chat_id)
        if not matches:
            self.metrics.dropped.labels(channel_id=str_chat_id, reason="no_rule_match").inc()
            return

        for rule in matches:
            for target_chat in rule.target_chats:
                try:
                    await self.client.send_message(target_chat, event.message)
                    self.metrics.forwarded.labels(channel_id=str_chat_id, target=str(target_chat)).inc()
                except Exception as ex:
                    log.error("failed sending to tg chat %s: %s", target_chat, ex)

            for url in rule.webhook_urls:
                payload = {
                    "source_chat_id": chat_id,
                    "source_chat_title": getattr(chat, "title", ""),
                    "message_id": msg_id,
                    "text": raw_text,
                    "date": event.message.date.isoformat() if event.message.date else None,
                    "rule_name": rule.name,
                }
                await self._post_webhook_with_retry(url, payload, str_chat_id)

        self.metrics.latency.observe(time.monotonic() - t0)

    async def _post_webhook_with_retry(self, url: str, payload: dict, str_chat_id: str) -> None:
        for attempt in range(3):
            try:
                resp = await self._http.post(url, json=payload)
                if resp.status_code < 400:
                    self.metrics.forwarded.labels(channel_id=str_chat_id, target=url).inc()
                    return
                self.metrics.webhook_errors.labels(endpoint=url, status_code=str(resp.status_code)).inc()
                if resp.status_code in (429, 502, 503, 504):
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                log.warning("webhook rejected by %s HTTP %d", url, resp.status_code)
                break
            except httpx.RequestError as ex:
                self.metrics.webhook_errors.labels(endpoint=url, status_code="network_error").inc()
                if attempt == 2:
                    log.error("webhook unreachable after 3 attempts %s: %s", url, ex)
                await asyncio.sleep(0.5 * (attempt + 1))

    async def close(self) -> None:
        await self._http.aclose()
        await self.client.disconnect()
