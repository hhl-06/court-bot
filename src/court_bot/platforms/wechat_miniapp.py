"""
WeChat Mini Program (微信小程序) platform adapter.

This is the most common platform for Chinese university court booking.

**IMPORTANT — Before using this adapter, you MUST:**
1. Install mitmproxy and capture the API calls from the mini program
2. Fill in the actual endpoint URLs, headers, and request/response formats
3. Search for "YOUR_" placeholders below and replace with real values

See the project README for detailed packet-capture instructions.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from court_bot.core.config import AppConfig
from court_bot.platforms.base import (
    BasePlatform, CourtInfo, SlotInfo, Candidate, BookingResult,
)
from court_bot.utils.http import SessionManager

logger = logging.getLogger(__name__)


class WechatMiniAppPlatform(BasePlatform):
    """
    Adapter for WeChat Mini Program booking systems.

    Steps to customize:
      1. Set BASE_URL to your school's API host
      2. Fill in endpoint paths in each method
      3. Adjust JSON field mappings to match actual responses
      4. Set authentication headers via the session manager
    """

    # ──────────────────────────────────────────────────────
    # CONFIGURATION — replace these with real values from
    # your mitmproxy capture session
    # ──────────────────────────────────────────────────────
    BASE_URL = "https://your-school-api.example.com"   # ← CHANGE ME

    # API endpoint paths
    ENDPOINT_LOGIN: str = "/api/login"                  # ← CHANGE ME
    ENDPOINT_COURTS: str = "/api/court/list"            # ← CHANGE ME
    ENDPOINT_SLOTS: str = "/api/timeslot/query"         # ← CHANGE ME
    ENDPOINT_BOOK: str = "/api/booking/submit"          # ← CHANGE ME
    ENDPOINT_MY_BOOKINGS: str = "/api/booking/my"       # ← CHANGE ME
    ENDPOINT_CANCEL: str = "/api/booking/cancel"        # ← CHANGE ME

    # Authentication header name (common variants: Authorization, token, X-Auth-Token)
    AUTH_HEADER_NAME: str = "Authorization"             # ← CHANGE ME
    AUTH_HEADER_FORMAT: str = "Bearer {token}"          # ← CHANGE ME

    def __init__(self, config: AppConfig):
        super().__init__(config)
        self.session = SessionManager(
            base_url=self.BASE_URL,
            timeout=config.advanced.request_timeout,
            max_retries=config.advanced.retry_count,
            rate_limit=config.advanced.rate_limit,
        )
        self._token: str = ""
        self._user_info: dict[str, Any] = {}

    # ── Authentication ───────────────────────────────────

    def authenticate(self) -> bool:
        """
        Log into the booking system.

        Supports multiple strategies (choose based on what your system uses):
        - Direct username+password
        - Pre-obtained token
        - WeChat code exchange
        """
        auth_cfg = self.config.auth

        # Strategy 1: Pre-obtained token (fastest, set in config)
        if auth_cfg.token:
            logger.info("Using pre-obtained token")
            self._token = auth_cfg.token
            self._apply_token()
            self._authenticated = True
            return True

        # Strategy 2: WeChat code exchange
        if auth_cfg.login_type == "wechat" and auth_cfg.wechat_code:
            return self._login_via_wechat_code(auth_cfg.wechat_code)

        # Strategy 3: Direct username + password (most common)
        return self._login_via_password()

    def _login_via_password(self) -> bool:
        """Username + password login."""
        auth_cfg = self.config.auth
        logger.info("Logging in as %s...", auth_cfg.student_id)

        resp = self.session.post(
            self.ENDPOINT_LOGIN,
            json={
                "username": auth_cfg.student_id,
                "password": auth_cfg.password,
            },
        )
        if not resp:
            return False

        data = resp.json()
        logger.debug("Login response: %s", data)

        # ── Parse token from response ─────────────────────
        # Adjust these field names to match your actual API:
        code = data.get("code", -1)
        if code != 0:  # ← CHANGE ME: success indicator
            msg = data.get("message", data.get("msg", "Unknown error"))
            logger.error("Login rejected: %s", msg)
            return False

        self._token = data.get("data", {}).get("token", "")  # ← CHANGE ME
        if not self._token:
            # Try alternate locations
            self._token = data.get("token", data.get("accessToken", ""))

        if not self._token:
            logger.error("Could not extract token from login response")
            return False

        self._apply_token()
        self._authenticated = True
        logger.info("Login successful")
        return True

    def _login_via_wechat_code(self, code: str) -> bool:
        """Exchange wx.login() code for session token."""
        logger.info("Exchanging WeChat code for token...")
        resp = self.session.post(
            self.ENDPOINT_LOGIN,
            json={"code": code},
        )
        if not resp:
            return False
        data = resp.json()
        self._token = data.get("data", {}).get("token", "")  # ← CHANGE ME
        if not self._token:
            self._token = data.get("token", "")
        self._apply_token()
        self._authenticated = bool(self._token)
        return self._authenticated

    def _apply_token(self) -> None:
        """Attach the auth token to the session headers."""
        header_value = self.AUTH_HEADER_FORMAT.format(token=self._token)
        self.session.headers[self.AUTH_HEADER_NAME] = header_value

    # ── Court / Slot fetching ────────────────────────────

    def fetch_courts(self, court_type: str = "") -> list[CourtInfo]:
        """Fetch list of bookable courts."""
        resp = self.session.get(self.ENDPOINT_COURTS)
        if not resp:
            return []

        data = resp.json()
        logger.debug("Courts response: %s", data)

        # ── Parse courts ──────────────────────────────────
        # Adjust field paths to match your actual API response:
        items = data.get("data", [])  # ← CHANGE ME
        if isinstance(items, dict):
            items = items.get("list", items.get("courts", []))

        courts = []
        for item in items:
            courts.append(CourtInfo(
                court_id=str(item.get("id", item.get("courtId", ""))),  # ← CHANGE ME
                court_name=item.get("name", item.get("courtName", "")),  # ← CHANGE ME
                court_number=item.get("number", item.get("courtNumber", 0)),
                location=item.get("location", item.get("address", "")),
                extra=item,
            ))

        logger.info("Fetched %d court(s)", len(courts))
        return courts

    def fetch_slots(self, date: str, court_id: str = "") -> list[SlotInfo]:
        """Fetch available time slots for a date (and optional court)."""
        params: dict[str, str] = {"date": date}
        if court_id:
            params["courtId"] = court_id  # ← CHANGE ME param name

        resp = self.session.get(self.ENDPOINT_SLOTS, params=params)
        if not resp:
            return []

        data = resp.json()
        logger.debug("Slots response (%s): %s", court_id or "all", data)

        # ── Parse slots ───────────────────────────────────
        items = data.get("data", [])  # ← CHANGE ME
        if isinstance(items, dict):
            items = items.get("list", items.get("slots", []))

        slots = []
        for item in items:
            slots.append(SlotInfo(
                slot_id=str(item.get("id", item.get("slotId", ""))),  # ← CHANGE ME
                start_time=item.get("startTime", item.get("start", "")),  # ← CHANGE ME
                end_time=item.get("endTime", item.get("end", "")),  # ← CHANGE ME
                available=item.get("available", item.get("status", 1) == 1),  # ← CHANGE ME
                price=float(item.get("price", 0)),
                extra=item,
            ))

        available_count = sum(1 for s in slots if s.available)
        logger.info("Fetched %d slot(s) (%d available) for %s court=%s",
                    len(slots), available_count, date, court_id or "all")
        return slots

    # ── Booking ──────────────────────────────────────────

    def submit_booking(self, candidate: Candidate, date: str) -> BookingResult:
        """Submit a booking request."""
        payload = {
            "courtId": candidate.court_id,       # ← CHANGE ME field names
            "date": date,
            "slotId": candidate.slot_id,
            "startTime": candidate.start_time,
            "endTime": candidate.end_time,
            # Add any extra fields your API requires (sport type, category, etc.)
            # "type": self.config.booking.court_type,
        }

        start = time.monotonic()
        resp = self.session.post(self.ENDPOINT_BOOK, json=payload)
        elapsed = time.monotonic() - start

        if not resp:
            return BookingResult(
                success=False, message="Network error",
                court_name=candidate.court_name, slot_label=candidate.slot_label,
            )

        data = resp.json()
        logger.debug("Book response (%.2fs): %s", elapsed, data)

        # ── Interpret response ────────────────────────────
        code = data.get("code", -1)  # ← CHANGE ME: success indicator
        success = (code == 0)  # ← CHANGE ME

        booking_id = ""
        if success:
            booking_id = data.get("data", {}).get("bookingId", "")  # ← CHANGE ME
            if not booking_id:
                booking_id = data.get("bookingId", data.get("orderId", ""))

        message = data.get("message", data.get("msg", ""))  # ← CHANGE ME

        return BookingResult(
            success=success,
            booking_id=str(booking_id),
            message=str(message),
            court_name=candidate.court_name,
            slot_label=candidate.slot_label,
            raw_response=data,
        )

    # ── Utilities ────────────────────────────────────────

    def get_my_bookings(self) -> list[dict]:
        """Fetch existing reservations for the current user."""
        resp = self.session.get(self.ENDPOINT_MY_BOOKINGS)
        if not resp:
            return []
        data = resp.json()
        items = data.get("data", [])  # ← CHANGE ME
        if isinstance(items, dict):
            items = items.get("list", items.get("bookings", []))
        return items

    def cancel_booking(self, booking_id: str) -> bool:
        """Cancel an existing reservation."""
        resp = self.session.post(
            self.ENDPOINT_CANCEL,
            json={"bookingId": booking_id},  # ← CHANGE ME
        )
        if not resp:
            return False
        data = resp.json()
        return data.get("code", -1) == 0  # ← CHANGE ME

    def close(self) -> None:
        """Release HTTP resources."""
        self.session.close()
