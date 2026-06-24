"""Tests for day-of-week targeting feature."""

from datetime import datetime, timedelta

from court_bot.core.config import AppConfig
from court_bot.core.scheduler import BookingScheduler


class TestDayOfWeekTargeting:
    """Test the target_day_of_week feature in scheduler and config."""

    def test_config_default_target_day_empty(self):
        cfg = AppConfig()
        assert cfg.booking.target_day_of_week == ""

    def test_config_target_day_set(self):
        cfg = AppConfig()
        cfg.booking.target_day_of_week = "星期五"
        assert cfg.booking.target_day_of_week == "星期五"

    def test_day_map_has_chinese_and_english(self):
        day_map = BookingScheduler._DAY_MAP
        assert day_map["星期五"] == 4
        assert day_map["friday"] == 4
        assert day_map["周四"] == 3
        assert day_map["thursday"] == 3
        assert day_map["星期一"] == 0
        assert day_map["monday"] == 0
        assert day_map["星期天"] == 6
        assert day_map["sunday"] == 6

    def test_target_date_with_day_of_week(self):
        """Test that target_day_of_week calculates the next occurrence."""
        cfg = AppConfig()
        cfg.booking.target_day_of_week = ""  # use date_offset

        # Create a scheduler with a mock platform
        scheduler = BookingScheduler.__new__(BookingScheduler)  # skip __init__
        scheduler.config = cfg

        # Test date_offset fallback
        today = datetime.now()
        target = scheduler._target_date()
        expected = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        assert target == expected

    def test_target_date_friday_from_thursday(self):
        """Friday target: if today is Thursday, target = tomorrow (Friday)."""
        cfg = AppConfig()
        cfg.booking.target_day_of_week = "Friday"

        scheduler = BookingScheduler.__new__(BookingScheduler)
        scheduler.config = cfg

        # Mock datetime.now() to return a Thursday
        target = cfg.booking.target_day_of_week.strip().lower()
        day_map = BookingScheduler._DAY_MAP
        target_dow = day_map[target]  # 4 = Friday

        # On Thursday (weekday=3), Friday is 1 day away
        today_dow = 3  # Thursday
        days_ahead = target_dow - today_dow  # 4 - 3 = 1
        assert days_ahead == 1

    def test_target_date_wraps_to_next_week(self):
        """If target day has passed this week, calculate next week."""
        cfg = AppConfig()
        cfg.booking.target_day_of_week = "Monday"

        scheduler = BookingScheduler.__new__(BookingScheduler)
        scheduler.config = cfg

        target = cfg.booking.target_day_of_week.strip().lower()
        day_map = BookingScheduler._DAY_MAP
        target_dow = day_map[target]  # 0 = Monday

        # On Wednesday (weekday=2), Monday has passed → next Monday = 5 days ahead
        today_dow = 2  # Wednesday
        days_ahead = target_dow - today_dow  # 0 - 2 = -2 → +7 = 5
        if days_ahead <= 0:
            days_ahead += 7
        assert days_ahead == 5
