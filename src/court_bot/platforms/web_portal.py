"""
Generic web-portal platform adapter (Selenium-based fallback).

Use this when the booking system is a traditional website rather than
a mini program, OR when you cannot intercept the mini-program API.

Requires: pip install court-bot[webui] (brings in selenium-wire)
"""

from __future__ import annotations

import logging
import time

from court_bot.core.config import AppConfig
from court_bot.platforms.base import (
    BasePlatform, CourtInfo, SlotInfo, Candidate, BookingResult,
)

logger = logging.getLogger(__name__)


class WebPortalPlatform(BasePlatform):
    """
    Selenium-based adapter for web booking portals.

    This is a skeleton — fill in element selectors based on your target website.

    Setup:
        pip install selenium-wire
        # Download matching ChromeDriver
    """

    PORTAL_URL: str = "https://your-school-portal.example.com"  # ← CHANGE ME

    def __init__(self, config: AppConfig):
        super().__init__(config)
        self._driver = None

    def _get_driver(self):
        """Lazy-init Selenium WebDriver."""
        if self._driver is not None:
            return self._driver

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
        except ImportError:
            raise ImportError(
                "Selenium is required for WebPortalPlatform. "
                "Install with: pip install selenium"
            )

        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")

        self._driver = webdriver.Chrome(options=opts)
        return self._driver

    # ── Authentication ───────────────────────────────────

    def authenticate(self) -> bool:
        """Navigate to portal, fill login form, submit."""
        driver = self._get_driver()
        auth = self.config.auth

        try:
            driver.get(f"{self.PORTAL_URL}/login")  # ← CHANGE ME URL

            # ── Fill login form ──────────────────────────
            username_input = driver.find_element("id", "username")  # ← CHANGE ME
            password_input = driver.find_element("id", "password")  # ← CHANGE ME
            submit_btn = driver.find_element("css selector", "button[type=submit]")  # ← CHANGE ME

            username_input.send_keys(auth.student_id)
            password_input.send_keys(auth.password)
            submit_btn.click()

            time.sleep(2)  # wait for redirect

            # ── Verify login ──────────────────────────────
            if "login" in driver.current_url.lower():
                logger.error("Login failed — still on login page")
                return False

            self._authenticated = True
            logger.info("Web portal login successful")
            return True

        except Exception as e:
            logger.error("Web portal login error: %s", e)
            return False

    # ── Court / Slot fetching ────────────────────────────

    def fetch_courts(self, court_type: str = "") -> list[CourtInfo]:
        """Scrape court list from the portal."""
        driver = self._get_driver()
        driver.get(f"{self.PORTAL_URL}/booking")  # ← CHANGE ME URL

        # ── Parse court elements ─────────────────────────
        court_elements = driver.find_elements("css selector", ".court-item")  # ← CHANGE ME
        courts = []
        for el in court_elements:
            courts.append(CourtInfo(
                court_id=el.get_attribute("data-id") or "",
                court_name=el.text or "",
            ))
        return courts

    def fetch_slots(self, date: str, court_id: str = "") -> list[SlotInfo]:
        """Scrape time slots from the portal."""
        driver = self._get_driver()

        # ── Select date (if needed) ──────────────────────
        # date_picker = driver.find_element("css selector", ".date-picker")
        # date_picker.clear()
        # date_picker.send_keys(date)

        slot_elements = driver.find_elements("css selector", ".slot-item.available")  # ← CHANGE ME
        slots = []
        for el in slot_elements:
            slots.append(SlotInfo(
                slot_id=el.get_attribute("data-slot-id") or "",
                start_time=el.get_attribute("data-start") or "",
                end_time=el.get_attribute("data-end") or "",
                available=True,
            ))
        return slots

    # ── Booking ──────────────────────────────────────────

    def submit_booking(self, candidate: Candidate, date: str) -> BookingResult:
        """Click through the booking flow."""
        driver = self._get_driver()

        try:
            # ── Select court ─────────────────────────────
            court_el = driver.find_element(
                "css selector", f"[data-id='{candidate.court_id}']"  # ← CHANGE ME
            )
            court_el.click()

            # ── Select slot ──────────────────────────────
            slot_el = driver.find_element(
                "css selector", f"[data-slot-id='{candidate.slot_id}']"  # ← CHANGE ME
            )
            slot_el.click()

            # ── Submit ───────────────────────────────────
            submit_btn = driver.find_element("css selector", ".btn-submit")  # ← CHANGE ME
            submit_btn.click()

            time.sleep(1)

            # ── Check result ─────────────────────────────
            success_msg = driver.find_elements("css selector", ".success-message")  # ← CHANGE ME
            success = len(success_msg) > 0

            return BookingResult(
                success=success,
                message="Booked via web portal" if success else "Booking failed",
                court_name=candidate.court_name,
                slot_label=candidate.slot_label,
            )

        except Exception as e:
            logger.error("Web booking error: %s", e)
            return BookingResult(
                success=False, message=str(e),
                court_name=candidate.court_name, slot_label=candidate.slot_label,
            )

    def close(self) -> None:
        """Quit the browser driver."""
        if self._driver:
            self._driver.quit()
            self._driver = None
