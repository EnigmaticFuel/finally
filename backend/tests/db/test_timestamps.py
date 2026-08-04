"""Every *_at value the layer returns is an ISO 8601 UTC string."""

import re
from datetime import UTC, datetime

from app.db import add_chat_message, record_snapshot, record_trade, upsert_position
from app.db.repository import utc_now

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def test_utc_now_matches_the_iso_utc_shape():
    assert ISO_UTC.match(utc_now())


def test_utc_now_is_parseable_and_in_utc():
    parsed = datetime.fromisoformat(utc_now().replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert abs((datetime.now(UTC) - parsed).total_seconds()) < 5


def test_utc_now_is_monotonic_as_a_string():
    assert utc_now() <= utc_now()


def test_every_write_stamps_an_iso_utc_timestamp(db):
    from app.db import get_position

    upsert_position("AAPL", 1.0, 190.0)

    stamps = [
        get_position("AAPL")["updated_at"],
        record_trade("AAPL", "buy", 1.0, 190.0)["executed_at"],
        record_snapshot(10000.0)["recorded_at"],
        add_chat_message("user", "hello")["created_at"],
    ]
    assert all(ISO_UTC.match(stamp) for stamp in stamps)
