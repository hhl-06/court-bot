"""
Custom API platform adapter — for systems with a documented REST API.

Use this when your school provides an OpenAPI spec or you've fully
reverse-engineered a clean REST API that doesn't need WeChat-specific headers.

Configuration is done entirely via config.yaml's `custom` section.
No code changes needed — just fill in the endpoints and field mappings.
"""

from __future__ import annotations

import logging

from court_bot.core.config import AppConfig
from court_bot.platforms.base import (
    BasePlatform, CourtInfo, SlotInfo, Candidate, BookingResult,
)
from court_bot.utils.http import SessionManager

logger = logging.getLogger(__name__)


class CustomAPIPlatform(BasePlatform):
    """
    Fully configurable API platform.

    All endpoint URLs and JSON field mappings are driven by the `custom`
    section in config.yaml.  See config/config.example.yaml for all options.

    Example custom config:
        custom:
          base_url: "https://api.school.edu/v1"
          endpoints:
            login: "/auth/login"
            courts: "/courts"
            slots: "/courts/{court_id}/slots"
            book: "/bookings"
            my_bookings: "/bookings/mine"
          auth_header: "Authorization"
          auth_format: "Bearer {token}"
          field_mappings:
            login_success: "code == 0"
            token_path: "data.token"
            court_list_path: "data.courts"
            court_id: "id"
            court_name: "name"
            slot_list_path: "data"
            slot_id: "id"
            slot_start: "startTime"
            slot_end: "endTime"
            slot_available: "status == 1"
            book_success: "code == 0"
            booking_id_path: "data.bookingId"
            message_path: "message"
    """

    def __init__(self, config: AppConfig):
        super().__init__(config)
        custom = config.custom

        base_url = custom.get("base_url", "http://localhost")
        endpoints = custom.get("endpoints", {})
        mappings = custom.get("field_mappings", {})

        self._ep = endpoints
        self._map = mappings
        self._auth_header = custom.get("auth_header", "Authorization")
        self._auth_format = custom.get("auth_format", "{token}")

        self.session = SessionManager(
            base_url=base_url,
            timeout=config.advanced.request_timeout,
            max_retries=config.advanced.retry_count,
            rate_limit=config.advanced.rate_limit,
        )
        self._token: str = ""

    # ── Authentication ───────────────────────────────────

    def authenticate(self) -> bool:
        auth = self.config.auth

        if auth.token:
            self._token = auth.token
            self._apply_token()
            self._authenticated = True
            return True

        url = self._ep.get("login", "/auth/login")
        resp = self.session.post(url, json={
            "username": auth.student_id,
            "password": auth.password,
        })
        if not resp:
            return False

        data = resp.json()

        # Evaluate success check expression
        success_check = self._map.get("login_success", "code == 0")
        if not self._eval_expr(success_check, data):
            msg_path = self._map.get("message_path", "message")
            logger.error("Login failed: %s", self._get_nested(data, msg_path))
            return False

        token_path = self._map.get("token_path", "data.token")
        self._token = self._get_nested(data, token_path) or ""
        self._apply_token()
        self._authenticated = bool(self._token)
        return self._authenticated

    def _apply_token(self) -> None:
        if self._token:
            val = self._auth_format.format(token=self._token)
            self.session.headers[self._auth_header] = val

    # ── Court / Slot fetching ────────────────────────────

    def fetch_courts(self, court_type: str = "") -> list[CourtInfo]:
        url = self._ep.get("courts", "/courts")
        if court_type:
            url = f"{url}?type={court_type}"

        resp = self.session.get(url)
        if not resp:
            return []

        data = resp.json()
        items = self._get_nested(data, self._map.get("court_list_path", "data")) or []

        id_field = self._map.get("court_id", "id")
        name_field = self._map.get("court_name", "name")

        return [
            CourtInfo(
                court_id=str(item.get(id_field, "")),
                court_name=str(item.get(name_field, "")),
                court_number=item.get("number", 0),
                extra=item,
            )
            for item in items
        ]

    def fetch_slots(self, date: str, court_id: str = "") -> list[SlotInfo]:
        url_tpl = self._ep.get("slots", "/courts/{court_id}/slots")
        url = url_tpl.format(court_id=court_id) + f"?date={date}"

        resp = self.session.get(url)
        if not resp:
            return []

        data = resp.json()
        items = self._get_nested(data, self._map.get("slot_list_path", "data")) or []

        id_f = self._map.get("slot_id", "id")
        start_f = self._map.get("slot_start", "startTime")
        end_f = self._map.get("slot_end", "endTime")
        avail_expr = self._map.get("slot_available", "available == True")

        slots = []
        for item in items:
            avail = self._eval_expr(avail_expr, item)
            slots.append(SlotInfo(
                slot_id=str(item.get(id_f, "")),
                start_time=str(item.get(start_f, "")),
                end_time=str(item.get(end_f, "")),
                available=bool(avail),
                extra=item,
            ))
        return slots

    # ── Booking ──────────────────────────────────────────

    def submit_booking(self, candidate: Candidate, date: str) -> BookingResult:
        url = self._ep.get("book", "/bookings")

        resp = self.session.post(url, json={
            "courtId": candidate.court_id,
            "date": date,
            "slotId": candidate.slot_id,
        })
        if not resp:
            return BookingResult(success=False, message="Network error",
                                 court_name=candidate.court_name,
                                 slot_label=candidate.slot_label)

        data = resp.json()
        success = bool(self._eval_expr(
            self._map.get("book_success", "code == 0"), data,
        ))
        bid = self._get_nested(data, self._map.get("booking_id_path", "data.bookingId")) or ""
        msg = self._get_nested(data, self._map.get("message_path", "message")) or ""

        return BookingResult(
            success=success,
            booking_id=str(bid),
            message=str(msg),
            court_name=candidate.court_name,
            slot_label=candidate.slot_label,
            raw_response=data,
        )

    # ── Helpers ──────────────────────────────────────────

    @staticmethod
    def _get_nested(data: dict, path: str) -> object:
        """Get a nested dict value by dotted path, e.g. 'data.token'."""
        for key in path.split("."):
            if isinstance(data, dict):
                data = data.get(key, {})
            else:
                return None
        return data if data != {} else None

    @staticmethod
    def _eval_expr(expr: str, ctx: dict) -> object:
        """
        Safely evaluate a simple expression like 'code == 0' against a dict.

        This is intentionally limited — no imports, no builtins access.
        Only simple comparisons against dict items are supported.
        """
        try:
            return eval(expr, {"__builtins__": {}}, ctx)
        except Exception:
            return False

    def close(self) -> None:
        self.session.close()
