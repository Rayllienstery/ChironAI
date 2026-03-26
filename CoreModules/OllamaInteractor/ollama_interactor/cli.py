"""CLI entry: subcommands map to Ollama REST. Payloads via stdin JSON where noted."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests

from ollama_interactor import ollama_http


def _eprint(obj: dict[str, Any]) -> None:
    print(json.dumps(obj), file=sys.stderr)


def _read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("stdin JSON required")
    return json.loads(raw)


def _default_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")


def cmd_tags(args: argparse.Namespace) -> int:
    try:
        data = ollama_http.get_tags(args.base_url, timeout=args.timeout)
        print(json.dumps(data))
        return 0
    except requests.exceptions.HTTPError as e:
        _eprint(ollama_http.format_http_error(e))
        return 1
    except requests.exceptions.RequestException as e:
        _eprint({"error": str(e)})
        return 1


def cmd_ping(args: argparse.Namespace) -> int:
    try:
        data = ollama_http.ping(args.base_url, timeout=args.timeout)
        print(json.dumps(data))
        return 0
    except requests.exceptions.HTTPError as e:
        _eprint({**ollama_http.format_http_error(e), "ok": False})
        return 1
    except requests.exceptions.RequestException as e:
        _eprint({"error": str(e), "ok": False})
        return 1


def cmd_embed(args: argparse.Namespace) -> int:
    try:
        req = _read_stdin_json()
        url = req.get("url")
        if not url:
            raise ValueError("stdin JSON must include 'url' (full /api/embed URL)")
        body = req.get("json") or req.get("body")
        if body is None:
            raise ValueError("stdin JSON must include 'json' or 'body' (Ollama embed payload)")
        timeout = float(req.get("timeout", args.timeout))
        out = ollama_http.post_json_return_dict(url, body, timeout=timeout)
        print(json.dumps(out))
        return 0
    except (ValueError, json.JSONDecodeError, KeyError) as e:
        _eprint({"error": str(e)})
        return 1
    except requests.exceptions.HTTPError as e:
        _eprint(ollama_http.format_http_error(e))
        return 1
    except requests.exceptions.RequestException as e:
        _eprint({"error": str(e)})
        return 1


def cmd_chat(args: argparse.Namespace) -> int:
    try:
        req = _read_stdin_json()
        url = req.get("url")
        if not url:
            raise ValueError("stdin JSON must include 'url' (full /api/chat URL)")
        body = req.get("json") or req.get("body")
        if body is None:
            raise ValueError("stdin JSON must include 'json' or 'body'")
        timeout = float(req.get("timeout", args.timeout))
        if body.get("stream"):
            _eprint({"error": "use chat-stream subcommand for stream=True"})
            return 1
        out = ollama_http.post_json_return_dict(url, body, timeout=timeout)
        print(json.dumps(out))
        return 0
    except (ValueError, json.JSONDecodeError) as e:
        _eprint({"error": str(e)})
        return 1
    except requests.exceptions.HTTPError as e:
        _eprint(ollama_http.format_http_error(e))
        return 1
    except requests.exceptions.RequestException as e:
        _eprint({"error": str(e)})
        return 1


def cmd_chat_stream(args: argparse.Namespace) -> int:
    try:
        req = _read_stdin_json()
        url = req.get("url")
        if not url:
            raise ValueError("stdin JSON must include 'url'")
        body = req.get("json") or req.get("body")
        if body is None:
            raise ValueError("stdin JSON must include 'json' or 'body'")
        body = {**body, "stream": True}
        timeout = float(req.get("timeout", args.timeout))
        for line in ollama_http.stream_chat_lines(url, body, timeout=timeout):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = obj.get("message") or {}
            content = msg.get("content", "") if isinstance(msg, dict) else ""
            if content:
                print(json.dumps({"content": content}), flush=True)
        return 0
    except (ValueError, json.JSONDecodeError) as e:
        _eprint({"error": str(e)})
        return 1
    except requests.exceptions.HTTPError as e:
        _eprint(ollama_http.format_http_error(e))
        return 1
    except requests.exceptions.RequestException as e:
        _eprint({"error": str(e)})
        return 1


def cmd_generate(args: argparse.Namespace) -> int:
    try:
        req = _read_stdin_json()
        url = req.get("url")
        if not url:
            raise ValueError("stdin JSON must include 'url' (full /api/generate URL)")
        body = req.get("json") or req.get("body")
        if body is None:
            raise ValueError("stdin JSON must include 'json' or 'body'")
        timeout = float(req.get("timeout", args.timeout))
        out = ollama_http.post_json_return_dict(url, body, timeout=timeout)
        print(json.dumps(out))
        return 0
    except (ValueError, json.JSONDecodeError) as e:
        _eprint({"error": str(e)})
        return 1
    except requests.exceptions.HTTPError as e:
        _eprint(ollama_http.format_http_error(e))
        return 1
    except requests.exceptions.RequestException as e:
        _eprint({"error": str(e)})
        return 1


def cmd_rerank(args: argparse.Namespace) -> int:
    try:
        req = _read_stdin_json()
        url = req.get("url")
        if not url:
            raise ValueError("stdin JSON must include 'url' (full /api/rerank URL)")
        body = req.get("json") or req.get("body")
        if body is None:
            raise ValueError("stdin JSON must include 'json' or 'body'")
        timeout = float(req.get("timeout", args.timeout))
        out = ollama_http.post_json_return_dict(url, body, timeout=timeout)
        print(json.dumps(out))
        return 0
    except (ValueError, json.JSONDecodeError) as e:
        _eprint({"error": str(e)})
        return 1
    except requests.exceptions.HTTPError as e:
        _eprint(ollama_http.format_http_error(e))
        return 1
    except requests.exceptions.RequestException as e:
        _eprint({"error": str(e)})
        return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ollama-interactor", description="Ollama HTTP API via CLI (JSON I/O)")
    p.add_argument("-v", "--verbose", action="store_true", help="log more to stderr")

    sub = p.add_subparsers(dest="command", required=True)

    t = sub.add_parser("tags", help="GET /api/tags")
    t.add_argument("--base-url", default=_default_base_url(), help="Ollama base URL (default: OLLAMA_BASE_URL or localhost:11434)")
    t.add_argument("--timeout", type=float, default=30.0)
    t.set_defaults(func=cmd_tags)

    pg = sub.add_parser("ping", help="Lightweight GET /api/tags for reachability")
    pg.add_argument("--base-url", default=_default_base_url())
    pg.add_argument("--timeout", type=float, default=5.0)
    pg.set_defaults(func=cmd_ping)

    e = sub.add_parser("embed", help="POST /api/embed; stdin JSON {url, json|body, timeout?}")
    e.add_argument("--timeout", type=float, default=120.0)
    e.set_defaults(func=cmd_embed)

    c = sub.add_parser("chat", help="POST /api/chat non-stream; stdin JSON {url, json|body, timeout?}")
    c.add_argument("--timeout", type=float, default=600.0)
    c.set_defaults(func=cmd_chat)

    cs = sub.add_parser("chat-stream", help="POST /api/chat stream=True; stdout NDJSON lines {content}")
    cs.add_argument("--timeout", type=float, default=600.0)
    cs.set_defaults(func=cmd_chat_stream)

    g = sub.add_parser("generate", help="POST /api/generate; stdin JSON {url, json|body, timeout?}")
    g.add_argument("--timeout", type=float, default=120.0)
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("rerank", help="POST /api/rerank; stdin JSON {url, json|body, timeout?}")
    r.add_argument("--timeout", type=float, default=120.0)
    r.set_defaults(func=cmd_rerank)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.verbose:
        print(f"[ollama-interactor] command={args.command}", file=sys.stderr)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
