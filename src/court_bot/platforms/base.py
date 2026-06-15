"""
Abstract base class for all booking platforms.

Every platform must implement:
  - authenticate()        → login / obtain session
  - fetch_courts()        → list available courts
  - fetch_slots()         → list available time slots for a date
  - submit_booking()      → place a reservation
  - find_candidates()     → build priority-ordered slot list
  - book()                → convenience: submit + parse result
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from court_bot.core.config import AppConfig

logger = logging.getLogger(__name__)


# ── Data models ──────────────────────────────────────────

@dataclass
class CourtInfo:
    """A physical court."""
    court_id: str
    court_name: str
    court_number: int = 0
    location: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class SlotInfo:
    """A reservable time slot."""
    slot_id: str
    start_time: str          # "09:00"
    end_time: str            # "10:00"
    available: bool = True
    price: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.start_time}-{self.end_time}"


@dataclass
class Candidate:
    """A bookable combination of court + time slot."""
    court_id: str
    court_name: str
    court_number: int
    slot_id: str
    slot_label: str
    start_time: str
    end_time: str
    raw_court: dict = field(default_factory=dict)
    raw_slot: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Candidate({self.court_name}, {self.slot_label})"


@dataclass
class BookingResult:
    """Outcome of a booking attempt."""
    success: bool
    booking_id: str = ""
    message: str = ""
    court_name: str = ""
    slot_label: str = ""
    raw_response: dict = field(default_factory=dict)


# ── Base platform ────────────────────────────────────────

class BasePlatform(ABC):
    """
    Abstract booking platform.

    Subclass this and implement the abstract methods for your target system.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self._authenticated = False

    # ── abstract: must implement ─────────────────────────

    @abstractmethod
    def authenticate(self) -> bool:
        """Log in and obtain a valid session/token. Return True on success."""
        ...

    @abstractmethod
    def fetch_courts(self, court_type: str = "") -> list[CourtInfo]:
        """Retrieve the list of bookable courts."""
        ...

    @abstractmethod
    def fetch_slots(self, date: str, court_id: str = "") -> list[SlotInfo]:
        """Retrieve available time slots for a given date (and optional court)."""
        ...

    @abstractmethod
    def submit_booking(self, candidate: Candidate, date: str) -> BookingResult:
        """Post a booking request. Called by book()."""
        ...

    # ── concrete: convenience methods ────────────────────

    def find_candidates(
        self,
        date: str,
        court_type: str = "",
        preferred_courts: list[int] | None = None,
        preferred_times: list[str] | None = None,
        fallback_to_any: bool = True,
        max_candidates: int = 20,
    ) -> list[Candidate]:
        """
        Build a prioritized list of (court × slot) candidates.

        Calls fetch_courts() and fetch_slots() internally.
        Sorting: better court-rank first, then better time-rank.
        """
        preferred_courts = preferred_courts or []
        preferred_times = preferred_times or []

        all_courts = self.fetch_courts(court_type)
        if not all_courts:
            logger.warning("No courts returned from platform")
            return []

        raw_candidates: list[tuple[int, int, Candidate]] = []

        for court in all_courts:
            slots = self.fetch_slots(date, court.court_id)
            for slot in slots:
                if not slot.available:
                    continue

                # compute preference rank (lower = better)
                court_rank = (
                    preferred_courts.index(court.court_number)
                    if court.court_number in preferred_courts
                    else len(preferred_courts)
                )
                time_rank = (
                    preferred_times.index(slot.label)
                    if slot.label in preferred_times
                    else len(preferred_times)
                )

                c = Candidate(
                    court_id=court.court_id,
                    court_name=court.court_name,
                    court_number=court.court_number,
                    slot_id=slot.slot_id,
                    slot_label=slot.label,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    raw_court={"id": court.court_id, "name": court.court_name},
                    raw_slot={"id": slot.slot_id, "start": slot.start_time, "end": slot.end_time},
                )
                raw_candidates.append((court_rank, time_rank, c))

        # Sort by (court_rank, time_rank)
        raw_candidates.sort(key=lambda x: (x[0], x[1]))

        # Apply fallback filter
        if not fallback_to_any:
            raw_candidates = [
                (cr, tr, c) for cr, tr, c in raw_candidates
                if cr < len(preferred_courts) and tr < len(preferred_times)
            ]

        candidates = [c for _, _, c in raw_candidates[:max_candidates]]
        logger.info("Built %d candidate(s) for %s", len(candidates), date)
        return candidates

    def book(self, candidate: Candidate, date: str) -> BookingResult:
        """
        Submit a booking for a single candidate.

        Default implementation calls submit_booking().
        Platforms with special pre/post-processing can override.
        """
        return self.submit_booking(candidate, date)
