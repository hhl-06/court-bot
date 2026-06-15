"""Tests for platform base classes and registry."""

import pytest

from court_bot.core.config import AppConfig
from court_bot.platforms import (
    get_platform,
    PLATFORM_REGISTRY,
    BasePlatform,
    WechatMiniAppPlatform,
    WebPortalPlatform,
    CustomAPIPlatform,
)
from court_bot.platforms.base import CourtInfo, SlotInfo, Candidate, BookingResult


class TestPlatformRegistry:
    """Test platform registration and lookup."""

    def test_all_platforms_registered(self):
        assert "wechat_miniapp" in PLATFORM_REGISTRY
        assert "web_portal" in PLATFORM_REGISTRY
        assert "custom_api" in PLATFORM_REGISTRY

    def test_get_platform_returns_class(self):
        cls = get_platform("wechat_miniapp")
        assert issubclass(cls, BasePlatform)

    def test_get_platform_raises_on_unknown(self):
        with pytest.raises(KeyError, match="Unknown platform"):
            get_platform("nonexistent_platform")


class TestDataModels:
    """Test base data models."""

    def test_court_info_creation(self):
        c = CourtInfo(court_id="1", court_name="Court 1", court_number=1)
        assert c.court_id == "1"
        assert c.court_number == 1

    def test_slot_info_label(self):
        s = SlotInfo(slot_id="s1", start_time="09:00", end_time="10:00")
        assert s.label == "09:00-10:00"

    def test_candidate_repr(self):
        c = Candidate(
            court_id="1", court_name="Court 1", court_number=1,
            slot_id="s1", slot_label="09:00-10:00",
            start_time="09:00", end_time="10:00",
        )
        assert "Court 1" in repr(c)
        assert "09:00-10:00" in repr(c)

    def test_booking_result_defaults(self):
        r = BookingResult(success=False)
        assert r.booking_id == ""
        assert not r.success


class TestBasePlatform:
    """Test find_candidates logic (without real API calls)."""

    class MockPlatform(BasePlatform):
        """Minimal mock for testing candidate sorting."""

        def __init__(self):
            super().__init__(AppConfig())

        def authenticate(self) -> bool:
            return True

        def fetch_courts(self, court_type: str = ""):
            return [
                CourtInfo(court_id="1", court_name="Court 1", court_number=1),
                CourtInfo(court_id="2", court_name="Court 2", court_number=2),
                CourtInfo(court_id="3", court_name="Court 3", court_number=3),
            ]

        def fetch_slots(self, date: str, court_id: str = ""):
            return [
                SlotInfo(slot_id="s1", start_time="09:00", end_time="10:00", available=True),
                SlotInfo(slot_id="s2", start_time="10:00", end_time="11:00", available=True),
            ]

        def submit_booking(self, candidate, date):
            return BookingResult(success=True, booking_id="test-001")

    def test_find_candidates_returns_all(self):
        platform = self.MockPlatform()
        candidates = platform.find_candidates("2025-06-20")
        # 3 courts × 2 slots = 6 candidates
        assert len(candidates) == 6

    def test_find_candidates_preference_sorting(self):
        platform = self.MockPlatform()
        candidates = platform.find_candidates(
            "2025-06-20",
            preferred_courts=[2],       # Prefer court 2
            preferred_times=["10:00-11:00"],  # Prefer 10-11
        )
        # First candidate should be court 2, 10:00-11:00
        assert candidates[0].court_number == 2
        assert candidates[0].slot_label == "10:00-11:00"

    def test_find_candidates_max_limit(self):
        platform = self.MockPlatform()
        candidates = platform.find_candidates("2025-06-20", max_candidates=2)
        assert len(candidates) == 2

    def test_find_candidates_fallback_off(self):
        platform = self.MockPlatform()
        candidates = platform.find_candidates(
            "2025-06-20",
            preferred_courts=[1],
            preferred_times=["09:00-10:00"],
            fallback_to_any=False,
        )
        # Only court 1 with exactly 09:00-10:00
        for c in candidates:
            assert c.court_number == 1
            assert c.slot_label == "09:00-10:00"
