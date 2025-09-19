#!/usr/bin/python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional

@dataclass(frozen=True)
class DatesConfig:
    # Local date format string used across the project (for parsing min_date, etc.)
    date_format: str = "%Y-%m-%d"
    # Earliest date to scan messages from (as a string formatted by date_format)
    # Default matches Wordle historical start so catchup doesn’t scan forever.
    min_date: str = "2024-06-19"
    # The epoch local date that maps to base_number (default aligns with Wordle)
    epoch_date: date = date(2021, 6, 19)
    # The puzzle number at the epoch_date (Wordle starts at 0)
    base_number: int = 0

class GameDates:
    """
    Interface with default behavior aligned to Wordle:
    - Maps a timestamp to a daily puzzle number: base_number + days_since(epoch_date)
    - Exposes date_format and min_date for history catch-up.
    You can subclass or instantiate with a different DatesConfig to override behavior.
    """
    def __init__(self, config: DatesConfig | None = None):
        self.config = config or DatesConfig()

    @property
    def date_format(self) -> str:
        return self.config.date_format

    @property
    def min_date(self) -> str:
        return self.config.min_date

    def _to_local_date(self, ts: Optional[datetime] = None) -> date:
        """
        Convert a timestamp to the local date (naive date used for daily numbering).
        If ts is None, use now() in local timezone.
        """
        if ts is None:
            # Use local time for “today”
            return datetime.now().astimezone().date()
        # If timestamp is timezone-aware, convert to local timezone first
        if ts.tzinfo is not None:
            return ts.astimezone().date()
        # If naive, assume it’s local
        return ts.date()

    async def date_to_num(self, ts: Optional[datetime] = None) -> int:
        """
        Map a timestamp (or now if None) to a puzzle number.
        Default behavior: days since epoch_date plus base_number.
        """
        d = self._to_local_date(ts)
        delta_days = (d - self.config.epoch_date).days
        return self.config.base_number + max(0, delta_days)

    async def today_num(self) -> int:
        """Convenience: today’s puzzle number."""
        return await self.date_to_num(None)

# -----------------------------------------------------------------------------
# Module-level default and compatibility shims
# -----------------------------------------------------------------------------
_DEFAULT_GAME_DATE: GameDates = GameDates()

def get_game_date() -> GameDates:
    return _DEFAULT_GAME_DATE

def set_game_date(game_date: GameDates) -> None:
    global _DEFAULT_GAME_DATE, date_format, min_date
    _DEFAULT_GAME_DATE = game_date
    date_format = game_date.date_format
    min_date = game_date.min_date

# Expose module-level constants for backward compatibility
date_format: str = _DEFAULT_GAME_DATE.date_format
min_date: str = _DEFAULT_GAME_DATE.min_date

# Back-compat function used throughout the project
async def date_to_num(ts: Optional[datetime] = None) -> int:
    return await _DEFAULT_GAME_DATE.date_to_num(ts)
