"""Small Docker CLI adapter used by the CoreUI Docker tab."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator
from urllib.error import URLError
from urllib.request import Request, urlopen

SPEC_HASH_LABEL = "chironai.docker_manager.spec_hash"
MANAGED_LABEL = "chironai.docker_manager.managed"


@dataclass(frozen=True)
class DockerCommandResult:
    code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def message(self) -> str:
        return (self.stderr or self.stdout or f"docker exited with {self.code}").strip()


@dataclass(frozen=True)
class DockerContainerSpec:
    """Declarative container spec for extensions.

    ports, volumes, extra_hosts, and command intentionally use Docker CLI-compatible
    strings to keep the contract small and predictable:
    - ports: ["11434:11434"]
    - volumes: ["ollama_models:/root/.ollama"]
    - extra_hosts: ["host.docker.internal:host-gateway"]
    """

    name: str
    image: str
    ports: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    volumes: list[str] = field(default_factory=list)
    restart: str = "unless-stopped"
    extra_hosts: list[str] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DockerContainerState:
    exists: bool
    running: bool = False
    name: str = ""
    image: str = ""
    env: dict[str, str] = field(default_factory=dict)
    ports: dict[str, Any] = field(default_factory=dict)
    volumes: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)


def _docker_executable() -> str:
    env = (os.getenv("DOCKER_EXE") or "").strip()
    if env:
        return env
    found = shutil.which("docker")
    if found:
        return found
    if sys.platform == "win32":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidate = os.path.join(pf, "Docker", "Docker", "resources", "bin", "docker.exe")
        if os.path.isfile(candidate):
            return candidate
    return "docker"


def _compact_error(value: str, *, max_len: int = 600) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    return f"{text[:max_len - 3]}..."


def _json_lines(raw: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def _first_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        rows = _json_lines(text)
        return rows[0] if rows else {}
    return data if isinstance(data, dict) else {}


class DockerManager:
    """Docker operations exposed to WebUI.

    The class intentionally stays close to Docker CLI semantics so it can be tested with
    subprocess mocks and does not require a Python Docker SDK dependency.
    """

    def __init__(self, docker_exe: str | None = None) -> None:
        self._docker_exe = docker_exe or _docker_executable()

    def run(self, args: list[str], *, timeout: float = 30.0) -> DockerCommandResult:
        try:
            proc = subprocess.run(
                [self._docker_exe, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return DockerCommandResult(
                int(proc.returncode),
                (proc.stdout or "").strip(),
                (proc.stderr or "").strip(),
            )
        except FileNotFoundError:
            return DockerCommandResult(127, "", f"Docker CLI not found: {self._docker_exe}")
        except PermissionError as e:
            return DockerCommandResult(126, "", f"Docker CLI permission denied: {self._docker_exe}: {e}")
        except subprocess.TimeoutExpired as e:
            return DockerCommandResult(124, e.stdout or "", e.stderr or "Docker command timed out")

    def status(self) -> dict[str, Any]:
        version = self.run(["version", "--format", "{{json .}}"], timeout=15.0)
        version_data = _first_json(version.stdout) if version.ok else {}
        cli_available = version.code not in {126, 127}

        cli_version = ""
        server_version = ""
        if isinstance(version_data.get("Client"), dict):
            cli_version = str(version_data["Client"].get("Version") or "")
        if isinstance(version_data.get("Server"), dict):
            server_version = str(version_data["Server"].get("Version") or "")

        if not cli_version:
            simple = self.run(["--version"], timeout=10.0)
            cli_available = simple.code not in {126, 127}
            cli_version = simple.stdout if simple.ok else ""

        info = self.run(["info"], timeout=15.0) if cli_available else DockerCommandResult(127, "", version.stderr)
        return {
            "ok": True,
            "cli_available": bool(cli_available),
            "engine_ready": bool(cli_available and info.ok),
            "docker_exe": self._docker_exe,
            "cli_version": cli_version,
            "server_version": server_version,
            "error": "" if cli_available and info.ok else _compact_error(info.message if cli_available else version.message),
        }

    def engine_info(self) -> tuple[bool, str]:
        status = self.status()
        if bool(status.get("engine_ready")):
            return True, ""
        return False, str(status.get("error") or "Docker Engine is not ready")

    def wait_engine(
        self,
        *,
        docker_desktop_exe: str = r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
        timeout: float = 120.0,
        interval: float = 5.0,
        start_desktop_on_windows: bool = True,
    ) -> dict[str, Any]:
        ready, detail = self.engine_info()
        if ready:
            return {"ok": True, "message": "docker engine ready", "status": self.status()}

        if start_desktop_on_windows and sys.platform == "win32":
            try:
                subprocess.Popen(
                    [docker_desktop_exe],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as e:
                return {"ok": False, "message": f"failed to start Docker Desktop: {e}", "status": self.status()}

        deadline = time.monotonic() + float(timeout)
        last_err = detail or "docker not ready"
        while time.monotonic() < deadline:
            ready, detail = self.engine_info()
            if ready:
                return {"ok": True, "message": "docker engine became ready", "status": self.status()}
            time.sleep(max(0.1, float(interval)))
            if detail:
                last_err = f"timeout waiting for docker info: {detail}"
            else:
                last_err = "timeout waiting for docker info"

        return {"ok": False, "message": last_err, "status": self.status()}

    def wait_engine_tuple(
        self,
        *,
        docker_desktop_exe: str = r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
        timeout: float = 120.0,
        interval: float = 5.0,
        start_desktop_on_windows: bool = True,
    ) -> tuple[bool, str]:
        result = self.wait_engine(
            docker_desktop_exe=docker_desktop_exe,
            timeout=timeout,
            interval=interval,
            start_desktop_on_windows=start_desktop_on_windows,
        )
        return bool(result.get("ok")), str(result.get("message") or "")

    def containers(self) -> dict[str, Any]:
        result = self.run(["ps", "-a", "--format", "{{json .}}"], timeout=20.0)
        if not result.ok:
            return {"ok": False, "error": "Failed to list Docker containers", "details": _compact_error(result.message)}
        rows = []
        for item in _json_lines(result.stdout):
            status = str(item.get("Status") or "")
            rows.append(
                {
                    "id": str(item.get("ID") or ""),
                    "name": str(item.get("Names") or ""),
                    "image": str(item.get("Image") or ""),
                    "status": status,
                    "ports": str(item.get("Ports") or ""),
                    "created": str(item.get("CreatedAt") or item.get("RunningFor") or ""),
                    "running": status.lower().startswith("up"),
                }
            )
        return {"ok": True, "containers": rows}

    def images(self) -> dict[str, Any]:
        result = self.run(["images", "--format", "{{json .}}"], timeout=20.0)
        if not result.ok:
            return {"ok": False, "error": "Failed to list Docker images", "details": _compact_error(result.message)}
        rows = []
        for item in _json_lines(result.stdout):
            repository = str(item.get("Repository") or "")
            tag = str(item.get("Tag") or "")
            image = repository if not tag or tag == "<none>" else f"{repository}:{tag}"
            rows.append(
                {
                    "repository": repository,
                    "tag": tag,
                    "image": image,
                    "id": str(item.get("ID") or ""),
                    "size": str(item.get("Size") or ""),
                    "created": str(item.get("CreatedAt") or item.get("CreatedSince") or ""),
                }
            )
        return {"ok": True, "images": rows}

    def pull_image(self, image: str) -> dict[str, Any]:
        image = self._require_value(image, "image")
        result = self.run(["pull", image], timeout=1800.0)
        if not result.ok:
            return {"ok": False, "error": f"Failed to pull {image}", "details": _compact_error(result.message)}
        return {"ok": True, "image": image, "message": result.stdout or "pulled"}

    def inspect_container(self, container: str) -> DockerContainerState:
        container = self._require_value(container, "container")
        result = self.run(["inspect", container, "--format", "{{json .}}"], timeout=20.0)
        if not result.ok:
            return DockerContainerState(exists=False, name=container)
        data = _first_json(result.stdout)
        if not data:
            return DockerContainerState(exists=False, name=container)
        cfg = data.get("Config") if isinstance(data.get("Config"), dict) else {}
        state = data.get("State") if isinstance(data.get("State"), dict) else {}
        host_cfg = data.get("HostConfig") if isinstance(data.get("HostConfig"), dict) else {}
        labels = cfg.get("Labels") if isinstance(cfg.get("Labels"), dict) else {}
        env = self._env_list_to_dict(cfg.get("Env") if isinstance(cfg.get("Env"), list) else [])
        mounts = data.get("Mounts") if isinstance(data.get("Mounts"), list) else []
        volumes: list[str] = []
        for mount in mounts:
            if not isinstance(mount, dict):
                continue
            source = str(mount.get("Name") or mount.get("Source") or "").strip()
            dest = str(mount.get("Destination") or "").strip()
            if source and dest:
                volumes.append(f"{source}:{dest}")
        return DockerContainerState(
            exists=True,
            running=bool(state.get("Running")),
            name=str(data.get("Name") or container).lstrip("/"),
            image=str(cfg.get("Image") or ""),
            env=env,
            ports=dict(host_cfg.get("PortBindings") or {}),
            volumes=volumes,
            labels={str(k): str(v) for k, v in labels.items()},
        )

    def container_env(self, container: str, key: str | None = None) -> str | dict[str, str]:
        env = self.inspect_container(container).env
        if key is None:
            return env
        return env.get(str(key), "")

    def container_exists(self, container: str) -> bool:
        return self.inspect_container(container).exists

    def container_running(self, container: str) -> bool:
        return self.inspect_container(container).running

    def ensure_container(self, spec: DockerContainerSpec) -> dict[str, Any]:
        spec = self._normalize_spec(spec)
        status = self.status()
        if not status.get("engine_ready"):
            return {
                "ok": False,
                "error": "Docker Engine is not ready",
                "details": str(status.get("error") or "Docker CLI/Engine unavailable"),
            }

        desired_hash = self._spec_hash(spec)
        state = self.inspect_container(spec.name)
        if self._image_inspect(spec.image) is None:
            pulled = self.pull_image(spec.image)
            if not pulled.get("ok"):
                return pulled
        if not state.exists:
            created = self._run_container(spec, desired_hash)
            if not created.get("ok"):
                return created
            return {**created, "action": "created", "recreated": False}

        current_hash = state.labels.get(SPEC_HASH_LABEL, "")
        if current_hash != desired_hash:
            removed = self.remove_container(spec.name, force=True)
            if not removed.get("ok"):
                return removed
            created = self._run_container(spec, desired_hash)
            if not created.get("ok"):
                return created
            return {**created, "action": "recreated", "recreated": True}

        if state.running:
            return {
                "ok": True,
                "container": spec.name,
                "image": spec.image,
                "action": "already_running",
                "message": "already running",
                "recreated": False,
            }

        started = self.start_container(spec.name)
        if not started.get("ok"):
            return started
        return {**started, "image": spec.image, "action": "started", "recreated": False}

    def start_container(self, container: str) -> dict[str, Any]:
        container = self._require_value(container, "container")
        result = self.run(["start", container], timeout=60.0)
        if not result.ok:
            return {"ok": False, "error": f"Failed to start {container}", "details": _compact_error(result.message)}
        return {"ok": True, "container": container, "message": result.stdout or "started"}

    def stop_container(self, container: str) -> dict[str, Any]:
        container = self._require_value(container, "container")
        result = self.run(["stop", container], timeout=120.0)
        if not result.ok:
            return {"ok": False, "error": f"Failed to stop {container}", "details": _compact_error(result.message)}
        return {"ok": True, "container": container, "message": result.stdout or "stopped"}

    def remove_container(self, container: str, *, force: bool = False) -> dict[str, Any]:
        container = self._require_value(container, "container")
        if not force and self._container_running(container):
            return {
                "ok": False,
                "error": "Container is running",
                "details": "Stop the container first, or retry with force=true.",
            }
        args = ["rm"]
        if force:
            args.append("-f")
        args.append(container)
        result = self.run(args, timeout=120.0)
        if not result.ok:
            return {"ok": False, "error": f"Failed to remove {container}", "details": _compact_error(result.message)}
        return {"ok": True, "container": container, "message": result.stdout or "removed"}

    def remove_image(self, image: str, *, force: bool = False) -> dict[str, Any]:
        image = self._require_value(image, "image")
        args = ["rmi"]
        if force:
            args.append("-f")
        args.append(image)
        result = self.run(args, timeout=180.0)
        if not result.ok:
            return {"ok": False, "error": f"Failed to remove image {image}", "details": _compact_error(result.message)}
        return {"ok": True, "image": image, "message": result.stdout or "removed"}

    def wait_http(
        self,
        url: str,
        *,
        path: str = "/",
        timeout: float = 60.0,
        interval: float = 1.0,
        ok_status: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        base = str(url or "").rstrip("/")
        if not base:
            raise ValueError("url is required")
        suffix = str(path or "/")
        full_url = f"{base}{suffix if suffix.startswith('/') else '/' + suffix}"
        deadline = time.monotonic() + float(timeout)
        last_error = ""
        while time.monotonic() < deadline:
            try:
                req = Request(full_url, method="GET")
                with urlopen(req, timeout=min(3.0, max(0.5, float(interval)))) as resp:
                    status = int(getattr(resp, "status", 200))
                    if status in ok_status:
                        return {"ok": True, "url": full_url, "status_code": status}
                    last_error = f"http {status}"
            except URLError as e:
                last_error = str(e.reason)
            except Exception as e:
                last_error = str(e)
            time.sleep(max(0.1, float(interval)))
        return {"ok": False, "url": full_url, "error": _compact_error(last_error or "timeout")}

    def logs(self, container: str, *, tail: int = 120) -> dict[str, Any]:
        container = self._require_value(container, "container")
        result = self.run(["logs", "--tail", str(max(1, int(tail))), container], timeout=30.0)
        if not result.ok:
            return {"ok": False, "container": container, "error": "Failed to read container logs", "details": _compact_error(result.message)}
        return {"ok": True, "container": container, "logs": result.stdout}

    def events(self, *, event_types: list[str] | None = None) -> Iterator[dict[str, Any]]:
        """Yield Docker event objects from a single long-lived CLI process."""
        args = ["events", "--format", "{{json .}}"]
        for event_type in event_types or ["container"]:
            value = str(event_type or "").strip()
            if value:
                args.extend(["--filter", f"type={value}"])

        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(
                [self._docker_exe, *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if proc.stdout is None:
                yield {"ok": False, "error": "Docker events stdout is unavailable"}
                return
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    yield {"ok": False, "error": "Invalid Docker event payload", "raw": line[:500]}
                    continue
                if isinstance(item, dict):
                    item.setdefault("ok", True)
                    yield item
        except FileNotFoundError:
            yield {"ok": False, "error": f"Docker CLI not found: {self._docker_exe}"}
        except PermissionError as e:
            yield {"ok": False, "error": f"Docker CLI permission denied: {self._docker_exe}: {e}"}
        finally:
            if proc is not None and proc.poll() is None:
                proc.terminate()

    def check_image_update(self, image: str) -> dict[str, Any]:
        image = self._require_value(image, "image")
        local = self._image_inspect(image)
        remote = self._remote_manifest_digest(image)
        if local is None:
            remote_version = self._remote_image_version(image, remote_digest=remote) if remote else ""
            return {
                "ok": True,
                "image": image,
                "status": "not_local",
                "message": "Image is not present locally",
                "current_version": "",
                "update_version": remote_version or self._short_digest(remote),
            }

        current_version = self._image_version_from_inspect(local, image)
        local_digests = [str(x) for x in local.get("RepoDigests") or [] if str(x).strip()]
        if not remote:
            return {
                "ok": True,
                "image": image,
                "status": "unknown",
                "message": "Could not determine remote manifest digest",
                "local_digests": local_digests,
                "current_version": current_version,
                "update_version": "",
            }

        digest_match = any(item.endswith(f"@{remote}") or item == remote for item in local_digests)
        status = "up_to_date" if digest_match else "update_available"
        if status == "up_to_date":
            update_version = current_version
        else:
            remote_version = self._remote_image_version(image, remote_digest=remote)
            update_version = remote_version or self._short_digest(remote)
            if update_version and current_version and update_version == current_version:
                update_version = self._short_digest(remote) or update_version
        return {
            "ok": True,
            "image": image,
            "status": status,
            "remote_digest": remote,
            "local_digests": local_digests,
            "current_version": current_version,
            "update_version": update_version,
            "message": "Image is up to date" if digest_match else "Remote image digest differs from local image",
        }

    def update_image(self, image: str) -> dict[str, Any]:
        image = self._require_value(image, "image")
        before = self._image_id(image)
        pulled = self.pull_image(image)
        if not pulled.get("ok"):
            return pulled
        after = self._image_id(image)
        return {
            "ok": True,
            "image": image,
            "changed": bool(after and before != after),
            "before_id": before,
            "after_id": after,
            "message": pulled.get("message") or "updated",
        }

    def _container_running(self, container: str) -> bool:
        result = self.run(["inspect", "-f", "{{.State.Running}}", container], timeout=15.0)
        return result.ok and result.stdout.strip().lower() == "true"

    def _run_container(self, spec: DockerContainerSpec, spec_hash: str) -> dict[str, Any]:
        args = ["run", "-d", "--name", spec.name]
        for port in spec.ports:
            args.extend(["-p", port])
        for key, value in sorted(spec.env.items()):
            args.extend(["-e", f"{key}={value}"])
        for volume in spec.volumes:
            args.extend(["-v", volume])
        if spec.restart:
            args.extend(["--restart", spec.restart])
        for host in spec.extra_hosts:
            args.extend(["--add-host", host])
        labels = {
            **spec.labels,
            MANAGED_LABEL: "true",
            SPEC_HASH_LABEL: spec_hash,
        }
        for key, value in sorted(labels.items()):
            args.extend(["--label", f"{key}={value}"])
        args.append(spec.image)
        args.extend(spec.command)
        result = self.run(args, timeout=180.0)
        if not result.ok:
            return {"ok": False, "error": f"Failed to create {spec.name}", "details": _compact_error(result.message)}
        return {"ok": True, "container": spec.name, "image": spec.image, "message": result.stdout or "created"}

    @staticmethod
    def _normalize_spec(spec: DockerContainerSpec) -> DockerContainerSpec:
        if not isinstance(spec, DockerContainerSpec):
            raise TypeError("spec must be a DockerContainerSpec")
        name = DockerManager._require_value(spec.name, "name")
        image = DockerManager._require_value(spec.image, "image")
        return DockerContainerSpec(
            name=name,
            image=image,
            ports=[str(x).strip() for x in spec.ports if str(x).strip()],
            env={str(k).strip(): str(v) for k, v in spec.env.items() if str(k).strip()},
            volumes=[str(x).strip() for x in spec.volumes if str(x).strip()],
            restart=str(spec.restart or "").strip(),
            extra_hosts=[str(x).strip() for x in spec.extra_hosts if str(x).strip()],
            command=[str(x) for x in spec.command],
            labels={str(k).strip(): str(v) for k, v in spec.labels.items() if str(k).strip()},
        )

    @staticmethod
    def _spec_hash(spec: DockerContainerSpec) -> str:
        payload = asdict(spec)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _env_list_to_dict(items: list[Any]) -> dict[str, str]:
        out: dict[str, str] = {}
        for item in items:
            key, sep, value = str(item).partition("=")
            if sep and key:
                out[key] = value
        return out

    def _image_inspect(self, image: str) -> dict[str, Any] | None:
        result = self.run(["image", "inspect", image, "--format", "{{json .}}"], timeout=20.0)
        if not result.ok:
            return None
        data = _first_json(result.stdout)
        return data or None

    def _image_id(self, image: str) -> str:
        data = self._image_inspect(image)
        return str((data or {}).get("Id") or "")

    def _remote_manifest_digest(self, image: str) -> str:
        result = self.run(["manifest", "inspect", image], timeout=60.0)
        if not result.ok:
            return ""
        data = _first_json(result.stdout)
        descriptor = data.get("Descriptor") if isinstance(data.get("Descriptor"), dict) else {}
        digest = str(descriptor.get("digest") or "").strip()
        if digest:
            return digest
        manifests = data.get("manifests")
        if isinstance(manifests, list):
            platform = self._host_platform()
            for item in manifests:
                if not isinstance(item, dict):
                    continue
                item_platform = item.get("platform") if isinstance(item.get("platform"), dict) else {}
                arch = str(item_platform.get("architecture") or "").strip()
                os_name = str(item_platform.get("os") or "").strip()
                if f"{os_name}/{arch}" == platform or (not platform and item.get("digest")):
                    digest = str(item.get("digest") or "").strip()
                    if digest:
                        return digest
            for item in manifests:
                if isinstance(item, dict):
                    digest = str(item.get("digest") or "").strip()
                    if digest:
                        return digest
        return ""

    def _remote_image_version(self, image: str, *, remote_digest: str = "") -> str:
        platform = self._host_platform()
        result = self.run(
            ["buildx", "imagetools", "inspect", image, "--format", "{{json .}}"],
            timeout=60.0,
        )
        if result.ok:
            data = _first_json(result.stdout)
            image_data = data.get("image") if isinstance(data.get("image"), dict) else {}
            plat_entry = image_data.get(platform) if isinstance(image_data, dict) else None
            if not isinstance(plat_entry, dict) and isinstance(image_data, dict):
                for entry in image_data.values():
                    if isinstance(entry, dict):
                        plat_entry = entry
                        break
            config = plat_entry.get("config") if isinstance(plat_entry, dict) else {}
            labels = config.get("Labels") if isinstance(config, dict) else {}
            version = str((labels or {}).get("org.opencontainers.image.version") or "").strip()
            if version:
                return version
        return self._short_digest(remote_digest)

    @staticmethod
    def _image_version_from_inspect(data: dict[str, Any], image_ref: str) -> str:
        config = data.get("Config") if isinstance(data.get("Config"), dict) else {}
        labels = config.get("Labels") if isinstance(config, dict) else {}
        version = str((labels or {}).get("org.opencontainers.image.version") or "").strip()
        if version:
            return version
        ref = str(image_ref or "").strip()
        if ref and "@" not in ref:
            tag = ref.rsplit(":", 1)[-1].strip() if ":" in ref else ""
            if tag and tag.lower() != "latest":
                return tag
        image_id = str(data.get("Id") or "").strip()
        short = DockerManager._short_digest(image_id)
        if short:
            return short
        for item in data.get("RepoDigests") or []:
            short = DockerManager._short_digest(str(item).split("@", 1)[-1])
            if short:
                return short
        return ""

    @staticmethod
    def _short_digest(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if text.startswith("sha256:"):
            text = text[7:]
        return text[:12] if len(text) >= 12 else text

    @staticmethod
    def _host_platform() -> str:
        machine = platform.machine().lower()
        if machine in {"x86_64", "amd64"}:
            arch = "amd64"
        elif machine in {"aarch64", "arm64"}:
            arch = "arm64"
        else:
            arch = machine or "amd64"
        return f"linux/{arch}"

    @staticmethod
    def _require_value(value: str, field: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{field} is required")
        return text
