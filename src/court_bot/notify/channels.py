"""
Multi-channel notification dispatcher.

Supported channels:
  - Bark (iOS push)
  - DingTalk (钉钉) bot
  - Server酱 (WeChat push via WeChat Official Account)
  - PushPlus (微信公众号推送)
  - Telegram bot
  - Email (SMTP)

Configure at least one channel in config.yaml → notify section.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

import httpx

from court_bot.core.config import NotifyConfig

logger = logging.getLogger(__name__)


class Notifier:
    """Send booking result notifications through all configured channels."""

    def __init__(self, config: NotifyConfig):
        self.cfg = config

    # ── Public API ───────────────────────────────────────

    def send(self, title: str, body: str = "") -> bool:
        """
        Send notification through ALL configured channels.

        Returns True if at least one channel succeeded.
        """
        channels = [
            ("Bark", self._bark),
            ("DingTalk", self._dingtalk),
            ("ServerChan", self._serverchan),
            ("PushPlus", self._pushplus),
            ("Telegram", self._telegram),
            ("Email", self._email),
        ]

        any_ok = False
        any_configured = False

        for name, fn in channels:
            try:
                ok = fn(title, body)
                if ok:
                    logger.info("Notification sent via %s", name)
                    any_ok = True
                elif ok is not None:  # None = not configured, False = failed
                    any_configured = True
                    logger.warning("Notification failed via %s", name)
            except Exception as exc:
                logger.warning("Notification exception via %s: %s", name, exc)

        if not any_configured and not any_ok:
            logger.info("No notification channels configured — skipping push")
        return any_ok or not any_configured

    # ── Channel implementations ──────────────────────────

    def _bark(self, title: str, body: str) -> bool | None:
        """Bark (iOS) — https://bark.day.app"""
        key = self.cfg.bark_key
        if not key:
            return None
        try:
            url = f"https://api.day.app/{key}/{title}"
            resp = httpx.get(url, params={
                "body": body,
                "group": "CourtBot",
                "sound": "birdsong",
            }, timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    def _dingtalk(self, title: str, body: str) -> bool | None:
        """DingTalk bot webhook."""
        url = self.cfg.dingtalk_webhook
        if not url:
            return None
        try:
            resp = httpx.post(url, json={
                "msgtype": "text",
                "text": {"content": f"{title}\n{body}"},
            }, timeout=10)
            return resp.json().get("errcode") == 0
        except Exception:
            return False

    def _serverchan(self, title: str, body: str) -> bool | None:
        """Server酱 — https://sct.ftqq.com"""
        key = self.cfg.server_chan_key
        if not key:
            return None
        try:
            resp = httpx.post(
                f"https://sctapi.ftqq.com/{key}.send",
                data={"title": title, "desp": body},
                timeout=10,
            )
            return resp.json().get("code") == 0
        except Exception:
            return False

    def _pushplus(self, title: str, body: str) -> bool | None:
        """PushPlus — https://www.pushplus.plus"""
        token = self.cfg.pushplus_token
        if not token:
            return None
        try:
            resp = httpx.post("https://www.pushplus.plus/send", json={
                "token": token,
                "title": title,
                "content": body,
                "template": "txt",
            }, timeout=10)
            return resp.json().get("code") == 200
        except Exception:
            return False

    def _telegram(self, title: str, body: str) -> bool | None:
        """Telegram Bot API."""
        token = self.cfg.telegram_bot_token
        chat_id = self.cfg.telegram_chat_id
        if not token or not chat_id:
            return None
        try:
            text = f"*{title}*\n{body}"
            resp = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            return resp.json().get("ok", False)
        except Exception:
            return False

    def _email(self, title: str, body: str) -> bool | None:
        """SMTP email notification."""
        smtp_host = self.cfg.email_smtp_host
        sender = self.cfg.email_sender
        password = self.cfg.email_password
        receiver = self.cfg.email_receiver

        if not smtp_host or not sender or not receiver:
            return None

        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = title
            msg["From"] = sender
            msg["To"] = receiver

            port = self.cfg.email_smtp_port or 465
            with smtplib.SMTP_SSL(smtp_host, port, timeout=10) as server:
                server.login(sender, password)
                server.send_message(msg)
            return True
        except Exception:
            return False
