from __future__ import annotations

import json
from subprocess import CompletedProcess
from unittest.mock import patch

from docker_manager import DockerContainerSpec, DockerManager


def _proc(args: list[str], code: int = 0, out: str = "", err: str = "") -> CompletedProcess[str]:
    return CompletedProcess(args=args, returncode=code, stdout=out, stderr=err)


def test_status_reports_missing_cli() -> None:
    with patch("docker_manager.manager.subprocess.run", side_effect=FileNotFoundError()):
        status = DockerManager(docker_exe="missing-docker").status()

    assert status["ok"] is True
    assert status["cli_available"] is False
    assert status["engine_ready"] is False
    assert "not found" in status["error"].lower()


def test_status_reports_engine_ready_versions() -> None:
    version = json.dumps({"Client": {"Version": "27.0.1"}, "Server": {"Version": "27.0.2"}})

    def fake_run(args: list[str], **_: object) -> CompletedProcess[str]:
        if args[1:3] == ["version", "--format"]:
            return _proc(args, out=version)
        if args[1:] == ["info"]:
            return _proc(args, out="ok")
        raise AssertionError(args)

    with patch("docker_manager.manager.subprocess.run", side_effect=fake_run):
        status = DockerManager(docker_exe="docker").status()

    assert status["cli_available"] is True
    assert status["engine_ready"] is True
    assert status["cli_version"] == "27.0.1"
    assert status["server_version"] == "27.0.2"


def test_wait_engine_ready_returns_tuple() -> None:
    version = json.dumps({"Client": {"Version": "27.0.1"}, "Server": {"Version": "27.0.2"}})

    def fake_run(args: list[str], **_: object) -> CompletedProcess[str]:
        if args[1:3] == ["version", "--format"]:
            return _proc(args, out=version)
        if args[1:] == ["info"]:
            return _proc(args, out="ok")
        raise AssertionError(args)

    with patch("docker_manager.manager.subprocess.run", side_effect=fake_run):
        ok, msg = DockerManager(docker_exe="docker").wait_engine_tuple(timeout=0.1, interval=0.01)

    assert ok is True
    assert msg == "docker engine ready"


def test_wait_engine_starts_docker_desktop_on_windows() -> None:
    version = json.dumps({"Client": {"Version": "27.0.1"}, "Server": {"Version": "27.0.2"}})
    info_calls = 0

    def fake_run(args: list[str], **_: object) -> CompletedProcess[str]:
        nonlocal info_calls
        if args[1:3] == ["version", "--format"]:
            return _proc(args, out=version)
        if args[1:] == ["info"]:
            info_calls += 1
            if info_calls == 1:
                return _proc(args, code=1, err="not ready")
            return _proc(args, out="ready")
        raise AssertionError(args)

    with (
        patch("docker_manager.manager.subprocess.run", side_effect=fake_run),
        patch("docker_manager.manager.subprocess.Popen") as popen,
        patch("docker_manager.manager.sys.platform", "win32"),
    ):
        result = DockerManager(docker_exe="docker").wait_engine(
            docker_desktop_exe=r"C:\Docker\Docker Desktop.exe",
            timeout=0.1,
            interval=0.01,
            start_desktop_on_windows=True,
        )

    assert result["ok"] is True
    assert result["message"] == "docker engine became ready"
    popen.assert_called_once()


def test_containers_parse_json_lines() -> None:
    line = json.dumps(
        {
            "ID": "abc123",
            "Names": "qdrant",
            "Image": "qdrant/qdrant:latest",
            "Status": "Up 2 minutes",
            "Ports": "0.0.0.0:6333->6333/tcp",
            "CreatedAt": "2026-05-08 10:00:00 +0000 UTC",
        }
    )

    with patch("docker_manager.manager.subprocess.run", return_value=_proc(["docker"], out=line)):
        result = DockerManager(docker_exe="docker").containers()

    assert result["ok"] is True
    assert result["containers"][0]["name"] == "qdrant"
    assert result["containers"][0]["running"] is True


def test_container_public_state_helpers() -> None:
    spec = DockerContainerSpec(name="svc", image="example/service:latest")

    with patch(
        "docker_manager.manager.subprocess.run",
        return_value=_proc(["docker"], out=_inspect_payload(spec, running=True)),
    ):
        manager = DockerManager(docker_exe="docker")
        assert manager.container_exists("svc") is True
        assert manager.container_running("svc") is True


def test_images_parse_json_lines() -> None:
    line = json.dumps(
        {
            "Repository": "ollama/ollama",
            "Tag": "latest",
            "ID": "sha256:abc",
            "Size": "1GB",
            "CreatedAt": "2026-05-08 10:00:00 +0000 UTC",
        }
    )

    with patch("docker_manager.manager.subprocess.run", return_value=_proc(["docker"], out=line)):
        result = DockerManager(docker_exe="docker").images()

    assert result["ok"] is True
    assert result["images"][0]["image"] == "ollama/ollama:latest"


def test_pull_success_and_failure() -> None:
    with patch("docker_manager.manager.subprocess.run", return_value=_proc(["docker"], out="pulled")):
        ok = DockerManager(docker_exe="docker").pull_image("ollama/ollama:latest")
    with patch("docker_manager.manager.subprocess.run", return_value=_proc(["docker"], code=1, err="denied")):
        bad = DockerManager(docker_exe="docker").pull_image("private/image:latest")

    assert ok["ok"] is True
    assert bad["ok"] is False
    assert "denied" in bad["details"]


def test_start_stop_remove_container() -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_: object) -> CompletedProcess[str]:
        calls.append(args[1:])
        if args[1:4] == ["inspect", "-f", "{{.State.Running}}"]:
            return _proc(args, out="false")
        return _proc(args, out=args[1])

    with patch("docker_manager.manager.subprocess.run", side_effect=fake_run):
        manager = DockerManager(docker_exe="docker")
        start = manager.start_container("abc")
        stop = manager.stop_container("abc")
        remove = manager.remove_container("abc")

    assert start["ok"] is True
    assert stop["ok"] is True
    assert remove["ok"] is True
    assert ["start", "abc"] in calls
    assert ["stop", "abc"] in calls
    assert ["rm", "abc"] in calls


def test_remove_container_blocks_running_without_force() -> None:
    with patch("docker_manager.manager.subprocess.run", return_value=_proc(["docker"], out="true")):
        result = DockerManager(docker_exe="docker").remove_container("abc")

    assert result["ok"] is False
    assert result["error"] == "Container is running"


def test_check_image_update_up_to_date_and_available() -> None:
    local = json.dumps(
        {
            "Id": "sha256:local",
            "RepoDigests": ["ollama/ollama@sha256:aaa"],
            "Config": {"Labels": {"org.opencontainers.image.version": "24.04"}},
        }
    )
    remote_same = json.dumps({"Descriptor": {"digest": "sha256:aaa"}})
    remote_new = json.dumps({"Descriptor": {"digest": "sha256:bbb"}})
    remote_meta = json.dumps(
        {
            "image": {
                "linux/amd64": {
                    "config": {"Labels": {"org.opencontainers.image.version": "24.05"}},
                }
            }
        }
    )

    def fake_same(args: list[str], **_: object) -> CompletedProcess[str]:
        if args[1:3] == ["image", "inspect"]:
            return _proc(args, out=local)
        if args[1:3] == ["manifest", "inspect"]:
            return _proc(args, out=remote_same)
        raise AssertionError(args)

    def fake_new(args: list[str], **_: object) -> CompletedProcess[str]:
        if args[1:3] == ["image", "inspect"]:
            return _proc(args, out=local)
        if args[1:3] == ["manifest", "inspect"]:
            return _proc(args, out=remote_new)
        if args[1:4] == ["buildx", "imagetools", "inspect"]:
            return _proc(args, out=remote_meta)
        raise AssertionError(args)

    with patch("docker_manager.manager.subprocess.run", side_effect=fake_same):
        same = DockerManager(docker_exe="docker").check_image_update("ollama/ollama:latest")
    with patch("docker_manager.manager.subprocess.run", side_effect=fake_new):
        new = DockerManager(docker_exe="docker").check_image_update("ollama/ollama:latest")

    assert same["status"] == "up_to_date"
    assert same["current_version"] == "24.04"
    assert same["update_version"] == "24.04"
    assert new["status"] == "update_available"
    assert new["current_version"] == "24.04"
    assert new["update_version"] == "24.05"


def test_check_image_update_skips_remote_version_lookup_when_digest_matches() -> None:
    local = json.dumps(
        {
            "Id": "sha256:local",
            "RepoDigests": ["ollama/ollama@sha256:aaa"],
            "Config": {"Labels": {"org.opencontainers.image.version": "24.04"}},
        }
    )
    remote_same = json.dumps({"Descriptor": {"digest": "sha256:aaa"}})
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_: object) -> CompletedProcess[str]:
        calls.append(args)
        if args[1:3] == ["image", "inspect"]:
            return _proc(args, out=local)
        if args[1:3] == ["manifest", "inspect"]:
            return _proc(args, out=remote_same)
        raise AssertionError(args)

    with patch("docker_manager.manager.subprocess.run", side_effect=fake_run):
        result = DockerManager(docker_exe="docker").check_image_update("ollama/ollama:latest")

    assert result["status"] == "up_to_date"
    assert not any(args[1:4] == ["buildx", "imagetools", "inspect"] for args in calls)


def test_check_image_update_unknown_and_not_local() -> None:
    local = json.dumps(
        {
            "Id": "sha256:abcdef0123456789",
            "RepoDigests": [],
            "Config": {"Labels": {}},
        }
    )
    remote_meta = json.dumps(
        {
            "image": {
                "linux/amd64": {
                    "config": {"Labels": {"org.opencontainers.image.version": "9.9"}},
                }
            }
        }
    )

    def fake_unknown(args: list[str], **_: object) -> CompletedProcess[str]:
        if args[1:3] == ["image", "inspect"]:
            return _proc(args, out=local)
        if args[1:3] == ["manifest", "inspect"]:
            return _proc(args, code=1, err="manifest unavailable")
        raise AssertionError(args)

    def fake_not_local(args: list[str], **_: object) -> CompletedProcess[str]:
        if args[1:3] == ["image", "inspect"]:
            return _proc(args, code=1, err="missing")
        if args[1:3] == ["manifest", "inspect"]:
            return _proc(args, out=json.dumps({"Descriptor": {"digest": "sha256:remote"}}))
        if args[1:4] == ["buildx", "imagetools", "inspect"]:
            return _proc(args, out=remote_meta)
        raise AssertionError(args)

    with patch("docker_manager.manager.subprocess.run", side_effect=fake_unknown):
        unknown = DockerManager(docker_exe="docker").check_image_update("local/image:latest")
    with patch("docker_manager.manager.subprocess.run", side_effect=fake_not_local):
        not_local = DockerManager(docker_exe="docker").check_image_update("missing/image:latest")

    assert unknown["status"] == "unknown"
    assert unknown["current_version"] == "abcdef012345"
    assert unknown["update_version"] == ""
    assert not_local["status"] == "not_local"
    assert not_local["update_version"] == "9.9"


def _inspect_payload(spec: DockerContainerSpec, *, running: bool, spec_hash: str | None = None) -> str:
    labels = {"chironai.docker_manager.spec_hash": spec_hash or DockerManager._spec_hash(spec)}
    return json.dumps(
        {
            "Name": f"/{spec.name}",
            "Config": {
                "Image": spec.image,
                "Env": [f"{k}={v}" for k, v in spec.env.items()],
                "Labels": labels,
            },
            "State": {"Running": running},
            "HostConfig": {"PortBindings": {"11434/tcp": [{"HostPort": "11434"}]}},
            "Mounts": [{"Name": "ollama_models", "Destination": "/root/.ollama"}],
        }
    )


def test_ensure_container_creates_missing_container() -> None:
    spec = DockerContainerSpec(
        name="chironai-ollama",
        image="ollama/ollama:latest",
        ports=["11434:11434"],
        env={"OLLAMA_HOST": "0.0.0.0:11434"},
        volumes=["ollama_models:/root/.ollama"],
    )
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_: object) -> CompletedProcess[str]:
        calls.append(args[1:])
        if args[1:3] == ["version", "--format"]:
            return _proc(args, out=json.dumps({"Client": {"Version": "1"}, "Server": {"Version": "1"}}))
        if args[1:] == ["info"]:
            return _proc(args, out="ready")
        if args[1:3] == ["pull", spec.image]:
            return _proc(args, out="pulled")
        if args[1:4] == ["image", "inspect", spec.image]:
            return _proc(args, code=1, err="No such image")
        if args[1:3] == ["inspect", spec.name]:
            return _proc(args, code=1, err="No such object")
        if args[1:3] == ["run", "-d"]:
            return _proc(args, out="container-id")
        raise AssertionError(args)

    with patch("docker_manager.manager.subprocess.run", side_effect=fake_run):
        result = DockerManager(docker_exe="docker").ensure_container(spec)

    run_args = next(call for call in calls if call[:2] == ["run", "-d"])
    assert result["ok"] is True
    assert result["action"] == "created"
    assert ["pull", spec.image] in calls
    assert "-p" in run_args and "11434:11434" in run_args
    assert "-e" in run_args and "OLLAMA_HOST=0.0.0.0:11434" in run_args
    assert "-v" in run_args and "ollama_models:/root/.ollama" in run_args


def test_ensure_container_starts_existing_stopped_compatible_container() -> None:
    spec = DockerContainerSpec(name="svc", image="example/service:latest")
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_: object) -> CompletedProcess[str]:
        calls.append(args[1:])
        if args[1:3] == ["version", "--format"]:
            return _proc(args, out=json.dumps({"Client": {"Version": "1"}, "Server": {"Version": "1"}}))
        if args[1:] == ["info"]:
            return _proc(args)
        if args[1:3] == ["pull", spec.image]:
            return _proc(args)
        if args[1:4] == ["image", "inspect", spec.image]:
            return _proc(args, out=json.dumps({"Id": "local"}))
        if args[1:3] == ["inspect", spec.name]:
            return _proc(args, out=_inspect_payload(spec, running=False))
        if args[1:3] == ["start", spec.name]:
            return _proc(args, out=spec.name)
        raise AssertionError(args)

    with patch("docker_manager.manager.subprocess.run", side_effect=fake_run):
        result = DockerManager(docker_exe="docker").ensure_container(spec)

    assert result["ok"] is True
    assert result["action"] == "started"
    assert ["start", spec.name] in calls
    assert not any(call[:2] == ["rm", "-f"] for call in calls)


def test_ensure_container_keeps_existing_running_compatible_container() -> None:
    spec = DockerContainerSpec(name="svc", image="example/service:latest")
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_: object) -> CompletedProcess[str]:
        calls.append(args[1:])
        if args[1:3] == ["version", "--format"]:
            return _proc(args, out=json.dumps({"Client": {"Version": "1"}, "Server": {"Version": "1"}}))
        if args[1:] == ["info"]:
            return _proc(args)
        if args[1:3] == ["pull", spec.image]:
            return _proc(args)
        if args[1:4] == ["image", "inspect", spec.image]:
            return _proc(args, out=json.dumps({"Id": "local"}))
        if args[1:3] == ["inspect", spec.name]:
            return _proc(args, out=_inspect_payload(spec, running=True))
        raise AssertionError(args)

    with patch("docker_manager.manager.subprocess.run", side_effect=fake_run):
        result = DockerManager(docker_exe="docker").ensure_container(spec)

    assert result["ok"] is True
    assert result["action"] == "already_running"
    assert ["pull", spec.image] not in calls
    assert not any(call[0] in {"start", "rm", "run"} for call in calls)


def test_ensure_container_uses_local_image_when_pull_would_not_be_needed() -> None:
    spec = DockerContainerSpec(name="svc", image="example/service:latest")
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_: object) -> CompletedProcess[str]:
        calls.append(args[1:])
        if args[1:3] == ["version", "--format"]:
            return _proc(args, out=json.dumps({"Client": {"Version": "1"}, "Server": {"Version": "1"}}))
        if args[1:] == ["info"]:
            return _proc(args)
        if args[1:4] == ["image", "inspect", spec.image]:
            return _proc(args, out=json.dumps({"Id": "local"}))
        if args[1:3] == ["inspect", spec.name]:
            return _proc(args, code=1, err="No such object")
        if args[1:3] == ["run", "-d"]:
            return _proc(args, out="container-id")
        if args[1:3] == ["pull", spec.image]:
            raise AssertionError("pull should be skipped for a local image")
        raise AssertionError(args)

    with patch("docker_manager.manager.subprocess.run", side_effect=fake_run):
        result = DockerManager(docker_exe="docker").ensure_container(spec)

    assert result["ok"] is True
    assert result["action"] == "created"
    assert ["pull", spec.image] not in calls


def test_ensure_container_recreates_incompatible_container() -> None:
    spec = DockerContainerSpec(name="svc", image="example/service:latest", env={"A": "B"})
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_: object) -> CompletedProcess[str]:
        calls.append(args[1:])
        if args[1:3] == ["version", "--format"]:
            return _proc(args, out=json.dumps({"Client": {"Version": "1"}, "Server": {"Version": "1"}}))
        if args[1:] == ["info"]:
            return _proc(args)
        if args[1:3] == ["pull", spec.image]:
            return _proc(args)
        if args[1:4] == ["image", "inspect", spec.image]:
            return _proc(args, out=json.dumps({"Id": "local"}))
        if args[1:3] == ["inspect", spec.name]:
            return _proc(args, out=_inspect_payload(spec, running=True, spec_hash="old"))
        if args[1:4] == ["inspect", "-f", "{{.State.Running}}"]:
            return _proc(args, out="true")
        if args[1:4] == ["rm", "-f", spec.name]:
            return _proc(args, out=spec.name)
        if args[1:3] == ["run", "-d"]:
            return _proc(args, out="new-id")
        raise AssertionError(args)

    with patch("docker_manager.manager.subprocess.run", side_effect=fake_run):
        result = DockerManager(docker_exe="docker").ensure_container(spec)

    assert result["ok"] is True
    assert result["action"] == "recreated"
    assert ["rm", "-f", spec.name] in calls
    assert any(call[:2] == ["run", "-d"] for call in calls)


def test_wait_http_success_and_timeout() -> None:
    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    with patch("docker_manager.manager.urlopen", return_value=_Resp()):
        ok = DockerManager(docker_exe="docker").wait_http("http://localhost:11434", path="/api/tags", timeout=0.1)
    with patch("docker_manager.manager.urlopen", side_effect=OSError("nope")):
        bad = DockerManager(docker_exe="docker").wait_http("http://localhost:11434", path="/api/tags", timeout=0.1, interval=0.01)

    assert ok["ok"] is True
    assert ok["status_code"] == 200
    assert bad["ok"] is False


def test_logs_returns_tail_or_error() -> None:
    with patch("docker_manager.manager.subprocess.run", return_value=_proc(["docker"], out="hello")):
        ok = DockerManager(docker_exe="docker").logs("svc", tail=5)
    with patch("docker_manager.manager.subprocess.run", return_value=_proc(["docker"], code=1, err="missing")):
        bad = DockerManager(docker_exe="docker").logs("svc", tail=5)

    assert ok["ok"] is True
    assert ok["logs"] == "hello"
    assert bad["ok"] is False


def test_events_stream_parses_json_and_terminates_process() -> None:
    class _Popen:
        stdout = [
            '{"Type":"container","Action":"start","Actor":{"Attributes":{"name":"qdrant"}}}\n',
            'not-json\n',
        ]
        stderr = []
        terminated = False

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            self.terminated = True

    proc = _Popen()

    with patch("docker_manager.manager.subprocess.Popen", return_value=proc) as popen:
        events = list(DockerManager(docker_exe="docker").events(event_types=["container", "image"]))

    args = popen.call_args.args[0]
    assert args[:3] == ["docker", "events", "--format"]
    assert "--filter" in args
    assert events[0]["Type"] == "container"
    assert events[0]["Action"] == "start"
    assert events[0]["ok"] is True
    assert events[1]["ok"] is False
    assert proc.terminated is True
