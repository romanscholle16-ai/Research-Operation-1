from app.core.events import EventRecorder, EventType
from app.database.connection import Database


def test_record_event_persists_to_db(database: Database) -> None:
    recorder = EventRecorder(database)
    event = recorder.record(
        EventType.STRATEGY_DISCOVERED,
        category="research",
        message="new strategy found",
        payload={"strategy_id": "abc123", "source_system": "parameter_explorer"},
    )

    row = database.query_one("SELECT * FROM events WHERE id = ?", (event.id,))
    assert row is not None
    assert row["event_type"] == "strategy_discovered"
    assert row["category"] == "research"
    assert row["message"] == "new strategy found"


def test_list_recent_returns_events_in_order(database: Database) -> None:
    recorder = EventRecorder(database)
    recorder.record(EventType.APPLICATION_STARTED, category="application")
    recorder.record(EventType.WORKER_STARTED, category="application")
    recorder.record(EventType.WORKER_CRASHED, category="application")

    events = recorder.list_recent(limit=10)
    assert len(events) == 3
    assert events[0].event_type == "worker_crashed"  # most recent first


def test_event_payload_round_trips_as_json(database: Database) -> None:
    recorder = EventRecorder(database)
    payload = {"attempt": 2, "reason": "timeout", "nested": {"ok": True}}
    event = recorder.record(EventType.SUPERVISOR_ATTEMPTED_RECOVERY, category="supervisor", payload=payload)

    [stored] = [e for e in recorder.list_recent(limit=5) if e.id == event.id]
    assert stored.payload == payload
