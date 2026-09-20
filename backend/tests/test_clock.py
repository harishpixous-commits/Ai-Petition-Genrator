"""The date on a petition is the date it was made, where it was made.

A container runs in UTC and Tamil Nadu is UTC+5:30, so for the five and a half
hours after local midnight the two disagree about what day it is. Everything
here is that disagreement, and what it did to a dated legal instrument.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from unittest import mock

import pytest

from app.config import Settings
from app.domain import clock
from app.domain.fields import validate_dob, validate_past_date
from app.domain.letter import build_letter_text, reference_number
from app.domain.templates import the_template

IST = timezone(timedelta(minutes=330))


def at(local: datetime):
    """Pretend the wall clock reads this local time."""
    return mock.patch.object(
        clock, "datetime",
        mock.Mock(now=mock.Mock(return_value=local.astimezone(UTC))))


class TestTheDayTheServiceThinksItIs:
    @pytest.mark.parametrize("hour,minute,expected", [
        (0, 1, date(2026, 9, 20)),     # one minute past local midnight
        (2, 0, date(2026, 9, 20)),
        (5, 29, date(2026, 9, 20)),    # the last minute UTC still says the 19th
        (5, 31, date(2026, 9, 20)),
        (23, 59, date(2026, 9, 20)),
    ])
    def test_it_is_the_local_day_not_the_servers(self, hour, minute, expected):
        local = datetime(2026, 9, 20, hour, minute, tzinfo=IST)

        with at(local):
            assert clock.today() == expected

    def test_and_the_server_really_would_have_disagreed(self):
        """Without this the test above proves nothing: it has to be a moment
        when UTC genuinely reads a different date."""
        local = datetime(2026, 9, 20, 0, 30, tzinfo=IST)

        assert local.astimezone(UTC).date() == date(2026, 9, 19)

    def test_the_offset_is_configurable(self):
        settings = Settings(_env_file=None, petition_utc_offset_minutes=0)

        assert clock.zone(settings).utcoffset(None) == timedelta(0)


class TestWhatItPutOnThePetition:
    @staticmethod
    def _fields():
        return {"applicant_name": "Harish", "age": 23, "mobile": "9876543210",
                "address": "12 Gandhi Street, Coimbatore", "aadhaar": "234567890124",
                "grievance": "The street light has not worked for three months."}

    def test_a_petition_filed_after_midnight_is_dated_today(self):
        """It printed yesterday's date. On a dated instrument that is not a
        cosmetic error: it is the date the petition says it was made."""
        local = datetime(2026, 9, 20, 0, 30, tzinfo=IST)

        with at(local):
            text = build_letter_text(
                template=the_template(), fields=self._fields(), language="en",
                composition=None, session_id="abc-123")

        assert "Date: 20-09-2026" in text
        assert "19-09-2026" not in text

    def test_the_reference_number_carries_the_right_year(self):
        """The worst instance: a petition filed in the small hours of the first
        of January was filed under the previous year."""
        local = datetime(2027, 1, 1, 3, 0, tzinfo=IST)

        with at(local):
            reference = reference_number("abcdef123456")

        assert reference.startswith("AP/2027/"), reference


class TestWhatItDidToTheCitizensOwnDates:
    def test_todays_date_is_not_in_the_future(self):
        """Typed at one in the morning, the date a citizen is living in was
        rejected as a future date — by a service that was a day behind them."""
        local = datetime(2026, 9, 20, 1, 0, tzinfo=IST)

        with at(local):
            result = validate_past_date("20-09-2026")

        assert result.ok, result.error

    def test_tomorrow_is_still_in_the_future(self):
        """The loosening must not reach further than the bug."""
        local = datetime(2026, 9, 20, 1, 0, tzinfo=IST)

        with at(local):
            assert not validate_past_date("21-09-2026").ok

    def test_an_age_is_counted_from_the_local_day(self):
        local = datetime(2026, 9, 20, 1, 0, tzinfo=IST)

        with at(local):
            assert validate_dob("20-09-2000").ok


class TestWhyAnOffsetAndNotAZoneName:
    def test_the_timezone_database_is_not_assumed_to_exist(self):
        """`zoneinfo` raises when the IANA database is absent, which is the
        normal state of a slim container and of Python on Windows without
        `tzdata`. India has never observed daylight saving, so a fixed offset
        is exact and needs nothing installed."""
        from pathlib import Path

        source = Path("app/domain/clock.py").read_text(encoding="utf-8")

        assert "zoneinfo" not in source.split('"""')[2], (
            "clock.py depends on a timezone database that production may lack")

    def test_it_is_exact_all_year(self):
        """No daylight saving means the same offset in January and in July."""
        january = datetime(2026, 1, 15, 12, 0, tzinfo=UTC).astimezone(clock.zone())
        july = datetime(2026, 7, 15, 12, 0, tzinfo=UTC).astimezone(clock.zone())

        assert january.utcoffset() == july.utcoffset() == timedelta(minutes=330)
