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

from court_bot.core.campus_net import campus_network_login
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

        # 1. Campus network login (always, not just when network appears down)
        self._ensure_campus_network()

        # 2. Wait for network (campus network may drop overnight)
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

        # 4. Wait for the pre-fetch moment (only in timed mode)
        if not fire_immediately:
            self._wait_until_prefetch()
        else:
            logger.info("Immediate mode — skipping countdown")

        # 5. Pre-fetch available slots (before booking opens → slots don't change)
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

        # 5.5. Pre-warm the booking pipeline (user info + goodsId) so the
        #      create request fires the instant the opening moment arrives.
        if not fire_immediately:
            self._prewarm(candidates, target_date)

        # 5.6. Wait for the exact fire moment
        if not fire_immediately:
            self._wait_until_fire()

        # 6. Fire booking requests
        logger.info("🚀 FIRING booking requests at %s", self.time_sync.now_formatted)

        consecutive = max(1, self.config.booking.consecutive_slots)

        if self.config.advanced.dry_run:
            slots_desc = candidates[0].slot_label
            if consecutive > 1:
                follow = self._get_consecutive_slots(candidates[0])
                slots_desc = " + ".join(s.slot_label for s in [candidates[0]] + follow[:consecutive-1])
            logger.info("[DRY RUN] Would book: %s | %s (x%d)", candidates[0].court_name, slots_desc, consecutive)
            return BookingResult(success=True, booking_id="DRY_RUN",
                                 court_name=candidates[0].court_name,
                                 slot_label=slots_desc)

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

    def _ensure_campus_network(self) -> None:
        """
        主动登录校园网（每次运行都尝试）。

        Dr.COM 认证系统允许重复登录 (reply_code=255 = 已在线)。
        这样不管是刚断线还是没认证，都能保证网络可用。
        """
        from court_bot.core.campus_net import campus_network_login
        auth_cfg = self.config.auth
        if auth_cfg.student_id and auth_cfg.password:
            logger.info("正在确保校园网已认证...")
            campus_network_login(
                username=auth_cfg.student_id,
                password=auth_cfg.password,
            )

    def _wait_for_network(self, timeout: int = 300) -> None:
        """
        Keep retrying until the API server is reachable.

        If campus network requires login (portal auth), auto-login first.
        Waits up to *timeout* seconds for connectivity before proceeding.
        """
        import socket
        deadline = time.time() + timeout
        host = "gym.njucm.edu.cn"
        port = 443
        tried_portal = False

        while time.time() < deadline:
            try:
                sock = socket.create_connection((host, port), timeout=5)
                sock.close()
                logger.info("Network reachable ✓")
                return
            except OSError:
                remaining = int(deadline - time.time())

                # Try campus portal login if we haven't yet
                if not tried_portal:
                    auth_cfg = self.config.auth
                    if auth_cfg.student_id and auth_cfg.password:
                        logger.info("Network down, trying campus portal login...")
                        campus_network_login(
                            username=auth_cfg.student_id,
                            password=auth_cfg.password,
                        )
                        tried_portal = True
                        time.sleep(3)
                        continue

                logger.warning(
                    "Network unreachable — retrying (timeout in %ds)...", remaining,
                )
                time.sleep(5)

        logger.error("Network still unreachable after %ds — proceeding anyway", timeout)

    # ── internals ─────────────────────────────────────────

    # Day-of-week mapping: supports English & Chinese
    _DAY_MAP: dict[str, int] = {
        "monday": 0, "mon": 0, "星期一": 0, "周一": 0,
        "tuesday": 1, "tue": 1, "星期二": 1, "周二": 1,
        "wednesday": 2, "wed": 2, "星期三": 2, "周三": 2,
        "thursday": 3, "thu": 3, "星期四": 3, "周四": 3,
        "friday": 4, "fri": 4, "星期五": 4, "周五": 4,
        "saturday": 5, "sat": 5, "星期六": 5, "周六": 5,
        "sunday": 6, "sun": 6, "星期日": 6, "周日": 6, "星期天": 6,
    }

    def _target_date(self) -> str:
        """Calculate the target booking date.

        Priority:
        1. target_day_of_week (e.g. "Friday") — next occurrence
        2. date_offset (e.g. 1 = tomorrow)
        """
        day_of_week = self.config.booking.target_day_of_week.strip().lower()
        if day_of_week and day_of_week in self._DAY_MAP:
            target_dow = self._DAY_MAP[day_of_week]
            today = datetime.now()
            today_dow = today.weekday()  # Monday=0, Sunday=6
            days_ahead = target_dow - today_dow
            if days_ahead <= 0:
                days_ahead += 7
            target = today + timedelta(days=days_ahead)
            logger.info(
                "Target: next %s (%s), %d day(s) from now",
                self.config.booking.target_day_of_week,
                target.strftime("%Y-%m-%d"),
                days_ahead,
            )
            return target.strftime("%Y-%m-%d")

        offset = self.config.booking.date_offset
        target = datetime.now() + timedelta(days=offset)
        return target.strftime("%Y-%m-%d")

    def _wait_until_prefetch(self) -> None:
        """Sleep until the pre-fetch moment (open_time - pre_fetch_seconds)."""
        open_time = self.config.schedule.open_time
        pre_fetch = self.config.schedule.pre_fetch_seconds

        wait = self.time_sync.time_until(open_time) - pre_fetch
        if wait > 0:
            logger.info(
                "Waiting %.1fs until pre-fetch (opens at %s, pre-fetch %ss early)...",
                wait, open_time, pre_fetch,
            )
            self.time_sync.precise_sleep(wait)

    def _wait_until_fire(self) -> None:
        """Sleep until the fire moment (open_time - fire_early_ms)."""
        open_time = self.config.schedule.open_time
        fire_early = self.config.schedule.fire_early_ms / 1000.0

        wait = max(0, self.time_sync.time_until(open_time) - fire_early)
        if wait > 0:
            logger.info("Waiting %.3fs until fire time (early offset %dms)...",
                        wait, self.config.schedule.fire_early_ms)
            self.time_sync.precise_sleep(wait)

    def _prewarm(self, candidates: list, target_date: str) -> None:
        """Pre-warm platform caches (user info, goodsId, ...) for the top candidates.

        This guarantees the booking request itself goes out the instant the
        fire moment arrives, with no extra network round-trips in the way.
        """
        prewarm = getattr(self.platform, "prewarm", None)
        if callable(prewarm):
            try:
                prewarm(candidates[:5], target_date)
            except Exception as e:
                logger.debug("Pre-warm failed (non-fatal): %s", e)

    def _get_consecutive_slots(self, candidate, count: int = 1):
        """
        Find consecutive follow-up slots on the same court.

        Given a candidate (e.g., 18:30-19:30 on Court 6),
        find the next available slot(s) (e.g., 19:30-20:30 on Court 6).

        Uses time arithmetic: next slot starts when current slot ends.
        """
        # Parse candidate's end time as minutes
        end_h, end_m = candidate.end_time.split(":")
        next_start_min = int(end_h) * 60 + int(end_m)

        results = []
        current_start_min = next_start_min

        for _ in range(count):
            next_start = f"{current_start_min // 60:02d}:{current_start_min % 60:02d}"
            next_end_min = current_start_min + 60  # NJUCM slots are 60 min each
            next_end = f"{next_end_min // 60:02d}:{next_end_min % 60:02d}"

            # Build a matching candidate
            from court_bot.platforms.base import Candidate
            fs = Candidate(
                court_id=candidate.court_id,
                court_name=candidate.court_name,
                court_number=candidate.court_number,
                slot_id=f"{candidate.raw_slot.get('area_id', '')}_{next_start}_{next_end}",
                slot_label=f"{next_start}-{next_end}",
                start_time=next_start,
                end_time=next_end,
                raw_court=dict(candidate.raw_court),
                raw_slot={**candidate.raw_slot, "start_time": next_start, "end_time": next_end},
            )
            results.append(fs)
            current_start_min = next_end_min

        return results

    def _try_candidates(
        self,
        candidates: list,
        target_date: str,
    ) -> BookingResult | None:
        """Try each candidate in priority order, retrying on failure.

        When consecutive_slots > 1, also books follow-up slots on the same court.
        """
        retries = self.config.advanced.retry_count
        interval = self.config.advanced.retry_interval
        consecutive = max(1, self.config.booking.consecutive_slots)

        for i, candidate in enumerate(candidates):
            logger.info("Candidate %d/%d: %s | %s", i + 1, len(candidates),
                        candidate.court_name, candidate.slot_label)

            # Skip candidates that don't have enough consecutive slots available
            if consecutive > 1:
                follow_slots = self._get_consecutive_slots(candidate, count=consecutive - 1)
                if len(follow_slots) < consecutive - 1:
                    logger.info("  Skipped: need %d consecutive slots, only %d follow-ups available",
                                consecutive, len(follow_slots))
                    continue
                logger.info("  + %d consecutive follow-up(s): %s",
                            len(follow_slots),
                            ", ".join(s.slot_label for s in follow_slots))

            for attempt in range(retries):
                if attempt > 0:
                    logger.info("  Retry %d/%d...", attempt, retries)
                    time.sleep(interval)

                result = self.platform.book(candidate, target_date)

                if not result.success:
                    logger.warning("  Failed: %s", result.message or "(no message)")
                    continue

                # Book consecutive follow-up slots
                booked_ids = [result.booking_id]
                booked_labels = [candidate.slot_label]
                follow_results = []

                for fs in follow_slots[:consecutive - 1]:
                    logger.info("  Booking follow-up: %s", fs.slot_label)
                    fr = self.platform.book(fs, target_date)
                    if fr.success:
                        booked_ids.append(fr.booking_id)
                        booked_labels.append(fs.slot_label)
                        follow_results.append(fr)
                        logger.info("  Follow-up booked: %s | %s", fs.slot_label, fr.booking_id)
                    else:
                        logger.warning("  Follow-up failed: %s — partial booking!", fr.message)
                        result = BookingResult(
                            success=True,
                            booking_id=", ".join(booked_ids),
                            message=f"部分成功: {', '.join(booked_labels)} (后续时段失败: {fr.message})",
                            court_name=candidate.court_name,
                            slot_label=" + ".join(booked_labels),
                        )
                        return result

                # All slots booked successfully
                result.booking_id = ", ".join(booked_ids)
                result.slot_label = " + ".join(booked_labels)
                return result

            logger.info("  Exhausted retries for this candidate")

        return BookingResult(success=False, message="All candidates failed")
