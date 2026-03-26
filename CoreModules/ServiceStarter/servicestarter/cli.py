"""CLI for ServiceStarter."""

from __future__ import annotations

import argparse
import json
import sys

from servicestarter.engine import ServiceStarter


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(prog="servicestarter", description="Install/start local services")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Print JSON status")

    p_install_docker = sub.add_parser("ensure-docker", help="Install Docker Desktop (Windows) + wait for engine")
    p_install_docker.add_argument("--install-only", action="store_true")

    sub.add_parser("ensure-ollama", help="Install Ollama (Windows) if missing")

    sub.add_parser("start-ollama", help="Start ollama serve (OLLAMA_HOST from config)")
    sub.add_parser("stop-ollama", help="Stop Ollama process")

    sub.add_parser("start-qdrant", help="Pull/start Qdrant container")
    sub.add_parser("stop-qdrant", help="Stop Qdrant container")

    sub.add_parser("start-open-webui", help="Pull/start Open WebUI container")
    sub.add_parser("stop-open-webui", help="Stop Open WebUI container")

    p_all = sub.add_parser("start-all", help="Run ensure/start for listed services")
    p_all.add_argument(
        "--services",
        default="docker,qdrant",
        help="Comma-separated: docker,ollama,qdrant,open-webui",
    )

    args = p.parse_args(argv)
    ss = ServiceStarter()

    if args.command == "status":
        print(json.dumps(ss.status(), indent=2))
        return 0

    if args.command == "ensure-docker":
        ok_i, msg_i = ss.ensure_docker_installed()
        print(json.dumps({"install": {"ok": ok_i, "message": msg_i}}))
        if not ok_i:
            return 1
        if getattr(args, "install_only", False):
            return 0
        ok, msg = ss.ensure_docker_running()
        print(json.dumps({"engine": {"ok": ok, "message": msg}}))
        return 0 if ok else 1

    if args.command == "ensure-ollama":
        ok, msg = ss.ensure_ollama_installed()
        print(json.dumps({"ok": ok, "message": msg}))
        return 0 if ok else 1

    if args.command == "start-ollama":
        ok, msg = ss.start_ollama()
        print(json.dumps({"ok": ok, "message": msg}))
        return 0 if ok else 1

    if args.command == "stop-ollama":
        ok, msg = ss.stop_ollama()
        print(json.dumps({"ok": ok, "message": msg}))
        return 0 if ok else 1

    if args.command == "start-qdrant":
        ok, msg = ss.start_qdrant()
        print(json.dumps({"ok": ok, "message": msg}))
        return 0 if ok else 1

    if args.command == "stop-qdrant":
        ok, msg = ss.stop_qdrant()
        print(json.dumps({"ok": ok, "message": msg}))
        return 0 if ok else 1

    if args.command == "start-open-webui":
        ok, msg = ss.start_open_webui()
        print(json.dumps({"ok": ok, "message": msg}))
        return 0 if ok else 1

    if args.command == "stop-open-webui":
        ok, msg = ss.stop_open_webui()
        print(json.dumps({"ok": ok, "message": msg}))
        return 0 if ok else 1

    if args.command == "start-all":
        parts = [s.strip() for s in args.services.split(",") if s.strip()]
        out = ss.start_all(parts)
        print(json.dumps(out, indent=2, default=str))
        bad = False
        for _key, v in out.items():
            if _key == "status":
                continue
            if isinstance(v, tuple) and len(v) >= 1 and v[0] is False:
                bad = True
        return 1 if bad else 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
