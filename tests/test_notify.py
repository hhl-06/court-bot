"""Tests for notification channels (unit tests without real API calls)."""

from court_bot.core.config import NotifyConfig
from court_bot.notify.channels import Notifier


class TestNotifier:
    """Test notifier with various configs."""

    def test_empty_config_does_not_raise(self):
        cfg = NotifyConfig()
        n = Notifier(cfg)
        result = n.send("test", "body")
        assert result is True  # No channels = "success" (nothing to fail)

    def test_bark_not_configured_returns_none(self):
        cfg = NotifyConfig(bark_key="")
        n = Notifier(cfg)
        assert n._bark("test", "body") is None

    def test_dingtalk_not_configured_returns_none(self):
        cfg = NotifyConfig(dingtalk_webhook="")
        n = Notifier(cfg)
        assert n._dingtalk("test", "body") is None

    def test_serverchan_not_configured_returns_none(self):
        cfg = NotifyConfig(server_chan_key="")
        n = Notifier(cfg)
        assert n._serverchan("test", "body") is None

    def test_pushplus_not_configured_returns_none(self):
        cfg = NotifyConfig(pushplus_token="")
        n = Notifier(cfg)
        assert n._pushplus("test", "body") is None

    def test_telegram_not_configured_returns_none(self):
        cfg = NotifyConfig(telegram_bot_token="")
        n = Notifier(cfg)
        assert n._telegram("test", "body") is None

    def test_email_not_configured_returns_none(self):
        cfg = NotifyConfig(email_smtp_host="")
        n = Notifier(cfg)
        assert n._email("test", "body") is None
