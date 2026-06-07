from __future__ import annotations

from types import SimpleNamespace

from extensions_backend.docker_updates import enrich_installed_with_docker


class _Docker:
    def __init__(self) -> None:
        self.containers_calls = 0
        self.check_calls = 0

    def containers(self) -> dict[str, object]:
        self.containers_calls += 1
        return {"ok": True, "containers": [{"name": "chironai-ollama", "image": "ollama/ollama:latest"}]}

    def inspect_container(self, _name: str) -> object:
        return SimpleNamespace(
            exists=True,
            running=True,
            name="chironai-ollama",
            image="ollama/ollama:latest",
            labels={"chironai.extension": "ollama-provider"},
            volumes=["ollama_models:/root/.ollama"],
        )

    def check_image_update(self, _image: str) -> dict[str, object]:
        self.check_calls += 1
        return {"status": "up_to_date", "current_version": "sha256:local"}


def test_enrich_installed_with_docker_skips_docker_when_no_installed_extensions() -> None:
    docker = _Docker()

    rows = enrich_installed_with_docker([], docker)

    assert rows == []
    assert docker.containers_calls == 0
    assert docker.check_calls == 0


def test_enrich_installed_with_docker_can_skip_remote_version_check() -> None:
    docker = _Docker()

    rows = enrich_installed_with_docker(
        [{"id": "ollama-provider", "title": "Ollama"}],
        docker,
        include_version_check=False,
    )

    assert rows[0]["docker"]["container_name"] == "chironai-ollama"
    assert rows[0]["docker"]["image"] == "ollama/ollama:latest"
    assert rows[0]["docker"]["update_status"] == "not_checked"
    assert rows[0]["docker"]["update_available"] is False
    assert docker.containers_calls == 1
    assert docker.check_calls == 0
