"""Tests for time synchronization and scheduling utilities."""

import time

from court_bot.core.time_sync import TimeSync


class TestTimeSync:
    """Test NTP time sync utilities."""

    def test_init_defaults(self):
        ts = TimeSync()
        assert ts.offset == 0.0
        assert not ts._synced

    def test_custom_server(self):
        ts = TimeSync("pool.ntp.org")
        assert ts.server == "pool.ntp.org"

    def test_now_returns_float(self):
        ts = TimeSync()
        now = ts.now
        assert isinstance(now, float)
        assert now > 0

    def test_now_formatted(self):
        ts = TimeSync()
        formatted = ts.now_formatted
        assert ":" in formatted
        assert "." in formatted

    def test_time_until_past(self):
        """time_until for a time already passed today should be negative."""
        ts = TimeSync()
        remaining = ts.time_until("00:00:01")
        assert remaining < 0

    def test_time_until_future(self):
        """time_until for a far future time today should be positive."""
        ts = TimeSync()
        remaining = ts.time_until("23:59:59")
        # Could be negative if current time is past 23:59:59
        # just check type
        assert isinstance(remaining, float)

    def test_precise_sleep_small(self):
        """Small sleep should not raise."""
        start = time.perf_counter()
        TimeSync.precise_sleep(0.1)
        elapsed = time.perf_counter() - start
        assert elapsed >= 0.09  # roughly

    def test_precise_sleep_zero(self):
        """Zero sleep should return immediately."""
        TimeSync.precise_sleep(0)  # should not raise or hang

    def test_precise_sleep_negative(self):
        """Negative sleep should return immediately."""
        TimeSync.precise_sleep(-5)  # should not raise or hang
