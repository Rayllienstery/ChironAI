"""Worker process entrypoint for sandboxed extensions."""

from __future__ import annotations

import json
import sys
import traceback
from dataclasses import asdict, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from extensions_sandbox.serialization import to_jsonable
from llm_interactor.contracts import LLMRequest, ProviderHostContext
from llm_interactor.manifest import manifest_from_dict

_PROTOCOL_OUT = sys.stdout
sys.stdout = sys.stderr
_next_host_id = 0
_provider: Any = None


def _send(payload: dict[str, Any]) -> None:
    _PROTOCOL_OUT.write(json.dumps(to_jsonable(payload), ensure_ascii=False) + "\n")
    _PROTOCOL_OUT.flush()


def _read_message() -> dict[str, Any]:
    line = sys.stdin.readline()
    if not line:
        raise EOFError("host closed stdin")
    data = json.loads(line)
    if not isinstance(data, dict):
        raise ValueError("RPC message must be an object")
    return data


def _host_call(target: str, method: str, *args: Any, **kwargs: Any) -> Any:
    global _next_host_id
    _next_host_id += 1
    call_id = _next_host_id
    _send({"type": "host_call", "id": call_id, "target": target, "method": method, "args": args, "kwargs": kwargs})
    while True:
        msg = _read_message()
        if msg.get("type") != "host_response" or int(msg.get("id") or -1) != call_id:
            continue
        if msg.get("ok"):
            return msg.get("result")
        raise RuntimeError(str(msg.get("error") or "host call failed"))


_EXT_SETTINGS_PREFIX = "ext."


class _SettingsProxy:
    def get_app_setting(self, key: str) -> Any:
        return _host_call("settings", "get_app_setting", key)

    def set_app_setting(self, key: str, value: Any) -> None:
        # The host enforces the 'ext.' namespace for writes; validate here too
        # so extensions get a clear error before the round-trip to the host.
        if not str(key or "").startswith(_EXT_SETTINGS_PREFIX):
            raise PermissionError(
                f"extension settings writes must use the 'ext.' namespace prefix; "
                f"got key: {key!r}"
            )
        _host_call("settings", "set_app_setting", key, value)


class _DockerProxy:
    def ensure_container(self, spec: Any) -> dict[str, Any]:
        payload = asdict(spec) if is_dataclass(spec) else dict(getattr(spec, "__dict__", spec))
        return dict(_host_call("docker_runtime", "ensure_container", payload) or {})

    def stop_container(self, container: str) -> dict[str, Any]:
        return dict(_host_call("docker_runtime", "stop_container", container) or {})

    def inspect_container(self, container: str) -> Any:
        result = _host_call("docker_runtime", "inspect_container", container)
        return SimpleNamespace(**dict(result or {})) if isinstance(result, dict) else result

    def wait_http(self, url: str, **kwargs: Any) -> dict[str, Any]:
        return dict(_host_call("docker_runtime", "wait_http", url, **kwargs) or {})

    def check_image_update(self, image: str) -> dict[str, Any]:
        return dict(_host_call("docker_runtime", "check_image_update", image) or {})


class _ChatClientProxy:
    def __init__(self, attrs: dict[str, Any]) -> None:
        self._url = str(attrs.get("_url") or "")
        self._model = str(attrs.get("_model") or "")

    def chat(self, messages: list[dict[str, Any]], model: str, **kwargs: Any) -> str:
        return str(_host_call("chat_client", "chat", messages, model, **kwargs) or "")

    def chat_api(self, body: dict[str, Any]) -> dict[str, Any]:
        return dict(_host_call("chat_client", "chat_api", body) or {})

    def chat_api_stream_final(self, body: dict[str, Any]) -> dict[str, Any]:
        return dict(_host_call("chat_client", "chat_api_stream_final", body) or {})

    def iter_chat_api_stream_events(self, body: dict[str, Any]):
        for item in _host_call("chat_client", "iter_chat_api_stream_events", body) or []:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                yield (item[0], item[1])

    def iter_chat_api_stream_openai_parts(self, body: dict[str, Any]):
        for item in _host_call("chat_client", "iter_chat_api_stream_openai_parts", body) or []:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                yield (item[0], item[1])


def _metadata_proxy(keys: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in keys:
        name = str(key)

        def _fn(*args: Any, _name: str = name, **kwargs: Any) -> Any:
            return _host_call("metadata", _name, *args, **kwargs)

        out[name] = _fn
    return out


def _load_factory_from_entrypoint(source_dir: Path, entrypoint: str):
    from extensions_sandbox.loader import load_factory_from_entrypoint

    return load_factory_from_entrypoint(source_dir, entrypoint)


def _initialize(params: dict[str, Any]) -> dict[str, Any]:
    global _provider
    source_dir = Path(str(params.get("source_dir") or ""))
    manifest = manifest_from_dict(dict(params.get("manifest") or {}))
    host = ProviderHostContext(
        project_root=Path(str(params.get("project_root") or ".")),
        get_settings_repository=lambda: _SettingsProxy(),
        chat_client=_ChatClientProxy(dict(params.get("chat_client_attrs") or {})),
        docker_runtime=_DockerProxy() if bool(params.get("has_docker_runtime")) else None,
        metadata=_metadata_proxy(list(params.get("metadata_callables") or [])),
    )
    factory = _load_factory_from_entrypoint(source_dir, str(params.get("entrypoint") or ""))
    _provider = factory(host, manifest)
    return {"ok": True}


def _request_from_dict(data: dict[str, Any]) -> LLMRequest:
    return LLMRequest(**dict(data or {}))


def _call(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return _initialize(params)
    if method == "shutdown":
        raise SystemExit(0)
    if _provider is None:
        raise RuntimeError("provider is not initialized")
    if method == "describe":
        return _provider.describe()
    if method == "list_models":
        return _provider.list_models()
    if method == "health_check":
        fn = getattr(_provider, "health_check", None)
        if callable(fn):
            return fn()
        desc = _provider.describe()
        return {"provider_id": getattr(desc, "id", ""), "ok": True, "status": "unknown"}
    if method == "invoke":
        return _provider.invoke(_request_from_dict(dict(params.get("request") or {})))
    if method == "stream_invoke":
        return list(_provider.stream_invoke(_request_from_dict(dict(params.get("request") or {}))))
    if method == "get_tab_descriptor":
        fn = getattr(_provider, "get_tab_descriptor", None)
        return fn() if callable(fn) else {}
    if method == "get_tab_payload":
        fn = getattr(_provider, "get_tab_payload", None)
        return fn() if callable(fn) else {}
    if method == "run_action":
        fn = getattr(_provider, "run_action", None)
        if not callable(fn):
            raise ValueError("extension does not expose actions")
        return fn(str(params.get("action_id") or ""), dict(params.get("payload") or {}))
    raise AttributeError(f"unknown worker method: {method}")


def main() -> None:
    while True:
        try:
            msg = _read_message()
        except EOFError:
            # Host closed stdin — normal shutdown.
            break
        except (json.JSONDecodeError, ValueError) as exc:
            # Malformed message from host: log and keep running rather than
            # crashing the worker, which would make the extension disappear.
            print(f"worker: invalid message from host: {exc}", file=sys.stderr, flush=True)
            continue
        if msg.get("type") != "request":
            continue
        req_id = int(msg.get("id") or 0)
        try:
            result = _call(str(msg.get("method") or ""), dict(msg.get("params") or {}))
            _send({"type": "response", "id": req_id, "ok": True, "result": result})
        except SystemExit:
            _send({"type": "response", "id": req_id, "ok": True, "result": None})
            raise
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            _send({"type": "response", "id": req_id, "ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
