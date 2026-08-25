"""Runtime state shared across a config entry's platforms."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.config_entries import ConfigEntry


@dataclass
class FilterTrackerData:
    """Per-entry state resolved once at setup and shared by every platform.

    Before this existed, each platform loaded the install datetime from disk
    independently during setup, racing the others through a code path that could
    also write. Resolving it once, up front, is what makes the platforms and the
    calendar pure readers.
    """

    install_datetime: datetime


type FilterTrackerConfigEntry = ConfigEntry[FilterTrackerData]
