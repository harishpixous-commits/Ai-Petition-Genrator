"""What day it is where the citizen is standing.

A container runs in UTC. Tamil Nadu is UTC+5:30. Between midnight and half past
five in the morning, local time, those are different DATES — so a petition
filed at one in the morning printed yesterday's date on it, the reference
number carried yesterday's year on the first of January, and a citizen who
typed today's date into a date field was told it was in the future.

None of that is a formatting preference. A petition is a dated instrument: the
date on it is the date it was made, and an office reading one filed at 00:30 on
the 20th should not see the 19th.

Why an offset rather than a zone name: India has never observed daylight
saving, so +05:30 is exact all year, and it needs no timezone database — which
a slim container does not ship and which `zoneinfo` raises on when it is
missing. A deployment somewhere that does observe daylight saving should add
`tzdata` and read a zone name here instead; that is a real change, and it
should be made deliberately rather than inherited from an offset that silently
stopped being right in March.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from ..config import Settings, get_settings


def zone(settings: Settings | None = None) -> timezone:
    """The deployment's own offset from UTC."""
    s = settings or get_settings()
    return timezone(timedelta(minutes=s.petition_utc_offset_minutes))


def now(settings: Settings | None = None) -> datetime:
    """The current moment, as the citizen's clock shows it."""
    return datetime.now(UTC).astimezone(zone(settings))


def today(settings: Settings | None = None) -> date:
    """The current DATE where the service is used.

    Every date a citizen sees or is judged against goes through here: the date
    printed on the petition, the year in its reference number, and the "is this
    in the future?" check on a date they typed.
    """
    return now(settings).date()
