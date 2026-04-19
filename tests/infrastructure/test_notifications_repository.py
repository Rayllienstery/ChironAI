from infrastructure.database.notifications_repository import NotificationsRepository
import infrastructure.database.notifications_repository as notifications_repo_module
import infrastructure.database.session_manager as session_manager_module
import sqlite3


def _make_repo(tmp_path):
    db_path = tmp_path / "webui.db"
    notifications_repo_module._notifications_repository = None
    session_manager_module._session_manager = None
    session_manager_module.SessionManager(db_path)
    return NotificationsRepository(db_path)


def test_add_notification_aggregates_by_key(tmp_path):
    repo = _make_repo(tmp_path)
    session_id = "s1"

    first_id = repo.add_notification(
        session_id=session_id,
        kind="error",
        source="rag",
        title="Qdrant / RAG unavailable",
        message="connect timeout",
        aggregation_key="infrastructure:rag-unavailable",
    )
    second_id = repo.add_notification(
        session_id=session_id,
        kind="error",
        source="rag",
        title="Qdrant / RAG unavailable",
        message="connect timeout again",
        aggregation_key="infrastructure:rag-unavailable",
    )

    items = repo.list_notifications(session_id, include_dismissed=True)

    assert second_id == first_id
    assert len(items) == 1
    assert items[0]["id"] == first_id
    assert items[0]["occurrence_count"] == 2
    assert items[0]["message"] == "connect timeout again"
    assert items[0]["aggregation_key"] == "infrastructure:rag-unavailable"


def test_dismissed_aggregate_starts_new_row(tmp_path):
    repo = _make_repo(tmp_path)
    session_id = "s1"

    first_id = repo.add_notification(
        session_id=session_id,
        kind="error",
        source="rag",
        title="Qdrant / RAG unavailable",
        message="connect timeout",
        aggregation_key="infrastructure:rag-unavailable",
    )
    assert repo.dismiss(session_id, first_id) is True

    second_id = repo.add_notification(
        session_id=session_id,
        kind="error",
        source="rag",
        title="Qdrant / RAG unavailable",
        message="new outage",
        aggregation_key="infrastructure:rag-unavailable",
    )

    items = repo.list_notifications(session_id, include_dismissed=True)

    assert second_id != first_id
    assert len(items) == 2
    active = [item for item in items if item["dismissed_at"] is None]
    assert len(active) == 1
    assert active[0]["id"] == second_id
    assert active[0]["occurrence_count"] == 1


def test_add_notification_migrates_legacy_table_without_last_occurrence_at(tmp_path):
    db_path = tmp_path / "webui.db"
    notifications_repo_module._notifications_repository = None
    session_manager_module._session_manager = None
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE coreui_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                metadata TEXT,
                is_console_error INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                dismissed_at TIMESTAMP
            )
            """
        )
        conn.commit()

    repo = NotificationsRepository(db_path)
    nid = repo.add_notification(
        session_id="s1",
        kind="error",
        source="logs",
        title="legacy schema",
        message="still works",
        aggregation_key="legacy:test",
    )
    items = repo.list_notifications("s1", include_dismissed=True)
    assert nid > 0
    assert len(items) == 1
    assert items[0]["occurrence_count"] == 1
    assert items[0]["last_occurrence_at"] is not None
