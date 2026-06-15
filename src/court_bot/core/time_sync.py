"""
Network Time Protocol (NTP) synchronization for precise scheduling.

Provides:
- Clock offset measurement against NTP servers
- Corrected current time
- Precise countdown to target timestamps
"""

import time
import logging
from datetime import datetime

import ntplib

logger = logging.getLogger(__name__)


class TimeSync:
    """
    NTP time synchronizer.

    Corrects local clock drift for sub-second booking precision.
    Falls back gracefully to local time if NTP is unavailable.

    Usage:
        ts = TimeSync()
        ts.sync()
        seconds_left = ts.time_until("20:00:00")
        now_str = ts.now_formatted()
    """

    def __init__(self, server: str = "ntp.aliyun.com"):
        self.server = server
        self.offset: float = 0.0
        self._synced: bool = False
        self._rtt: float = 0.0

    def sync(self) -> bool:
        """
        Synchronize with NTP server. Tries 3 times.

        Returns True on success, False if using local time fallback.
        """
        client = ntplib.NTPClient()
        for attempt in range(3):
            try:
                resp = client.request(self.server, version=3, timeout=2.0)
                ntp_time = resp.tx_time
                local_time = time.time()
                self.offset = ntp_time - local_time
                self._rtt = resp.delay
                self._synced = True
                logger.info(
                    "NTP synced to %s — offset: %+.1fms, RTT: %.0fms",
                    self.server,
                    self.offset * 1000,
                    self._rtt * 1000,
                )
                return True
            except Exception as exc:
                logger.warning("NTP attempt %d/3 failed: %s", attempt + 1, exc)
                time.sleep(0.5)

        logger.warning("NTP sync failed — using local system clock")
        self._synced = False
        return False

    # ── time accessors ────────────────────────────────────

    @property
    def now(self) -> float:
        """Corrected POSIX timestamp."""
        return time.time() + self.offset

    @property
    def now_dt(self) -> datetime:
        """Corrected datetime object."""
        return datetime.fromtimestamp(self.now)

    @property
    def now_formatted(self) -> str:
        """Corrected time as 'HH:MM:SS.mmm' string."""
        return self.now_dt.strftime("%H:%M:%S.%f")[:-3]

    # ── countdown helpers ─────────────────────────────────

    def time_until(self, target: str) -> float:
        """
        Seconds remaining until *target* (HH:MM:SS or HH:MM:SS.mmm) today.

        Returns a float (may be negative if the target has passed).
        """
        parts = target.split(":")
        hour, minute = int(parts[0]), int(parts[1])
        sec_float = float(parts[2]) if len(parts) > 2 else 0.0

        now = self.now_dt
        target_dt = now.replace(
            hour=hour,
            minute=minute,
            second=int(sec_float),
            microsecond=int((sec_float - int(sec_float)) * 1_000_000),
        )
        return (target_dt - now).total_seconds()

    # ── precision sleep ───────────────────────────────────

    @staticmethod
    def precise_sleep(seconds: float) -> None:
        """Sleep with high precision: time.sleep for bulk, busy-wait the final 0.3s."""
        if seconds <= 0:
            return
        if seconds > 0.5:
            time.sleep(seconds - 0.3)
        deadline = time.perf_counter() + 0.3
        while time.perf_counter() < deadline:
            pass
