"""Portfolio value snapshots for the P&L chart."""

from app.db import get_latest_snapshot_value, get_snapshots, record_snapshot


def test_record_returns_value_and_timestamp(db):
    snapshot = record_snapshot(10120.75)
    assert set(snapshot) == {"total_value", "recorded_at"}
    assert snapshot["total_value"] == 10120.75
    assert snapshot["recorded_at"].endswith("Z")


def test_snapshots_are_newest_first(db):
    for value in (10100.0, 10200.0, 10300.0):
        record_snapshot(value)

    values = [s["total_value"] for s in get_snapshots()]
    assert values[:3] == [10300.0, 10200.0, 10100.0]


def test_limit_caps_the_result(db):
    for value in (10100.0, 10200.0, 10300.0):
        record_snapshot(value)

    assert len(get_snapshots(limit=2)) == 2


def test_limit_takes_the_newest(db):
    for value in (10100.0, 10200.0, 10300.0):
        record_snapshot(value)

    assert get_snapshots(limit=1)[0]["total_value"] == 10300.0


def test_since_excludes_everything_up_to_that_timestamp(db):
    cutoff = record_snapshot(10100.0)["recorded_at"]
    record_snapshot(10200.0)

    later = get_snapshots(since=cutoff)
    assert [s["total_value"] for s in later] == [10200.0]


def test_since_in_the_future_returns_nothing(db):
    record_snapshot(10100.0)
    assert get_snapshots(since="2999-01-01T00:00:00.000Z") == []


def test_latest_value_is_the_seeded_opening_point(db):
    assert get_latest_snapshot_value() == 10000.0


def test_latest_value_follows_the_newest_write(db):
    record_snapshot(10250.0)
    assert get_latest_snapshot_value() == 10250.0


def test_latest_value_is_none_when_empty(db):
    assert get_latest_snapshot_value(user_id="other") is None


def test_snapshots_are_scoped_by_user(db):
    record_snapshot(500.0, user_id="other")
    assert [s["total_value"] for s in get_snapshots(user_id="other")] == [500.0]
