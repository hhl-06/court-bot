"""
Booking scheduler — the central orchestration engine.

Orchestrates the full booking workflow:
  1. Wait for network (campus WiFi may drop overnight)
  2. Sync network time
  3. Authenticate
  4. Pre-fetch court / slot data just before opening
  5. Fire booking requests with sub-second precision
  6. Retry on failure, fallback through candidates
  7. Notify result
"""

import time
import logging
from datetime import datetime, timedelta

from court_bot.core.config import AppConfig
from court_bot.core.time_sync import TimeSync
from court_bot.platforms.base import BasePlatform, BookingResult
from court_bot.notify.channels import Notifier

logger = logging.getLogger(__name__)


class BookingScheduler:
    """
    High-precision booking orchestrator.

    Usage:
        platform = WechatMiniAppPlatform(config)
        scheduler = BookingScheduler(config, platform)
        result = scheduler.run()
    """

    def __init__(self, config: AppConfig, platform: BasePlatform):
        self.config = config
        self.platform = platform
        self.time_sync = TimeSync(config.advanced.ntp_server)
        self.notifier = Notifier(config.notify)

    # ── public API ────────────────────────────────────────

    def run(self, fire_immediately: bool = False) -> BookingResult | None:
        """Execute the full booking workflow. Returns the result or None."""

        logger.info("=" * 60)
        logger.info("  Court Bot — Automated Booking Scheduler")
        logger.info("  Platform: %s", self.config.platform)
        logger.info("=" * 60)

        # 1. Wait for network (campus network may drop overnight)
        self._wait_for_network()

        # 2. Time sync
        if self.config.advanced.time_sync:
            self.time_sync.sync()

        # 3. Authenticate
        logger.info("Authenticating...")
        if not self.platform.authenticate():
            logger.error("Authentication failed — aborting")
            self.notifier.send("❌ Court Bot — Auth Failed", "Could not log in.")
            return None
        logger.info("Authenticated ✓")

        # 3. Target date
        target_date = self._target_date()
        logger.info("Target date: %s", target_date)

        # 4. Wait for the right moment
        if not fire_immediately:
            self._wait_until_opening()
        else:
            logger.info("Immediate mode — skipping countdown")

        # 5. Pre-fetch available slots
        logger.info("Fetching available slots...")
        candidates = self.platform.find_candidates(
            date=target_date,
            court_type=self.config.booking.court_type,
            preferred_courts=self.config.booking.preferred_courts,
            preferred_times=self.config.booking.preferred_times,
            fallback_to_any=self.config.booking.fallback_to_any,
            max_candidates=self.config.booking.max_candidates,
        )

        if not candidates:
            logger.error("No available slots found")
            self.notifier.send("❌ Court Bot — No Slots", f"No slots for {target_date}")
            return None

        logger.info("Found %d candidate(s):", len(candidates))
        for i, c in enumerate(candidates[:10]):
            logger.info("  %2d. %s | %s", i + 1, c.court_name, c.slot_label)

        # 6. Fire booking requests
        logger.info("🚀 FIRING booking requests at %s", self.time_sync.now_formatted)

        if self.config.advanced.dry_run:
            logger.info("[DRY RUN] Would book: %s", candidates[0])
            return BookingResult(success=True, booking_id="DRY_RUN",
                                 court_name=candidates[0].court_name,
                                 slot_label=candidates[0].slot_label)

        result = self._try_candidates(candidates, target_date)

        # 7. Notify
        if result and result.success:
            logger.info("✅ BOOKED: %s | %s | %s", result.court_name, result.slot_label, result.booking_id)
            self.notifier.send(
                "✅ Court Booked!",
                f"Court: {result.court_name}\nSlot: {result.slot_label}\nDate: {target_date}\nID: {result.booking_id}",
            )
        else:
            logger.error("❌ All candidates exhausted — booking failed")
            self.notifier.send(
                "❌ Booking Failed",
                f"Date: {target_date}\nTried {len(candidates)} candidates",
            )

        return result

    def _wait_for_network(self, timeout: int = 300) -> None:
        """
        Keep retrying until the API server is reachable.

        Campus networks often disconnect overnight. This waits up to
        *timeout* seconds for connectivity before proceeding.
        """
        import socket
        deadline = time.time() + timeout
        host = "gym.njucm.edu.cn"
        port = 443

        while time.time() < deadline:
            try:
                sock = socket.create_connection((host, port), timeout=5)
                sock.close()
                logger.info("Network reachable ✓")
                return
            except OSError:
                remaining = int(deadline - time.time())
                logger.warning(
                    "Network unreachable — retrying (timeout in %ds)...", remaining,
                )
                time.sleep(5)

        logger.error("Network still unreachable after %ds — proceeding anyway", timeout)

    # ── internals ─────────────────────────────────────────

    def _target_date(self) -> str:
        offset = self.config.booking.date_offset
        target = datetime.now() + timedelta(days=offset)
        return target.strftime("%Y-%m-%d")

    def _wait_until_opening(self) -> None:
        """Sleep until (open_time - pre_fetch_seconds), then pre-fetch, then fire."""
        open_time = self.config.schedule.open_time
        pre_fetch = self.config.schedule.pre_fetch_seconds
        fire_early = self.config.schedule.fire_early_ms / 1000.0

        # Phase 1: wait until pre-fetch moment
        wait = self.time_sync.time_until(open_time) - pre_fetch
        if wait > 0:
            logger.info(
                "Waiting %.1fs until pre-fetch (opens at %s, pre-fetch %ss early)...",
                wait, open_time, pre_fetch,
            )
            self.time_sync.precise_sleep(wait)

        # Phase 2: wait until fire moment (with early-offset)
        wait = max(0, self.time_sync.time_until(open_time) - fire_early)
        if wait > 0:
            logger.info("Waiting %.3fs until fire time (early offset %dms)...",
                        wait, self.config.schedule.fire_early_ms)
            self.time_sync.precise_sleep(wait)

    def _try_candidates(
        self,
        candidates: list,
        target_date: str,
    ) -> BookingResult | None:
        """Try each candidate in priority order, retrying on failure."""
        retries = self.config.advanced.retry_count
        interval = self.config.advanced.retry_interval

        for i, candidate in enumerate(candidates):
            logger.info("Candidate %d/%d: %s | %s", i + 1, len(candidates),
                        candidate.court_name, candidate.slot_label)

            for attempt in range(retries):
                if attempt > 0:
                    logger.info("  Retry %d/%d...", attempt, retries)
                    time.sleep(interval)

                result = self.platform.book(candidate, target_date)

                if result.success:
                    return result

                logger.warning("  Failed: %s", result.message or "(no message)")

            logger.info("  Exhausted retries for this candidate")

        return BookingResult(success=False, message="All candidates failed")
