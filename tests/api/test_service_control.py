from __future__ import annotations

from api.http import service_control


class _Cfg:
    qdrant_container_name = "qdrant-test"


class _Runtime:
    cfg = _Cfg()

    def start_qdrant(self) -> tuple[bool, str]:
        return True, "started"

    def stop_qdrant(self) -> tuple[bool, str]:
        return True, "stopped"


def test_qdrant_actions_use_rag_runtime_container_name(monkeypatch) -> None:
    monkeypatch.setattr(service_control, "get_rag_runtime", lambda: _Runtime())

    assert service_control.start_qdrant() == (True, "started", "qdrant-test")
    assert service_control.stop_qdrant() == (True, "stopped", "qdrant-test")
