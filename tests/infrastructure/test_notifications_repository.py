from infrastructure.database.notifications_repository import NotificationsRepository
import infrastructure.database.notifications_repository as notifications_repo_module
import infrastructure.database.session_manager as session_manager_module


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
