"""Build Sunshine apps.json with Cursor and host-control tiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MANAGED_NAMES = (
    "Cursor",
    "Cursor Agents",
    "Playnite",
    "YouTube",
    "Brave",
    "Sleep",
    "Restart Docker",
    "Restart ChironAI",
    "Restart PC",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge Moonlight quick-menu apps into Sunshine apps.json")
    parser.add_argument("--existing", required=True, help="Current Sunshine apps.json")
    parser.add_argument("--out", required=True, help="Where to write the merged JSON")
    parser.add_argument("--host-ps1", required=True, help="Path to moonlight-host.ps1")
    parser.add_argument("--working-dir", required=True, help="Working directory for host scripts")
    parser.add_argument("--cursor-cover", required=True)
    parser.add_argument("--agents-cover", required=True)
    parser.add_argument("--sleep-cover", required=True)
    parser.add_argument("--docker-cover", required=True)
    parser.add_argument("--chiron-cover", required=True)
    parser.add_argument("--reboot-cover", required=True)
    parser.add_argument("--playnite-cover", default="", help="Playnite cover; omit to skip the tile")
    parser.add_argument("--playnite-exe", default="", help="Playnite.FullscreenApp.exe path")
    parser.add_argument("--youtube-cover", default="", help="YouTube cover; omit to skip the tile")
    parser.add_argument("--brave-cover", default="", help="Brave cover; omit to skip the tile")
    return parser.parse_args()


def host_cmd(host_ps1: str, action: str) -> str:
    return (
        "powershell.exe -NoProfile -ExecutionPolicy Bypass -File "
        f'"{host_ps1}" -Action {action}'
    )


def session_app(name: str, action: str, close_action: str, cover: str, host_ps1: str, working_dir: str) -> dict[str, object]:
    # Launch in prep `do` (may exit immediately). Undo runs when the Moonlight stream ends.
    # Do not put a short-lived PowerShell launcher in `cmd`: Sunshine treats that as
    # "app exited" and can fire undo immediately, killing the just-started window.
    # Keep global prep so HD Switch streams flip to the dongle.
    return {
        "name": name,
        "working-dir": working_dir,
        "auto-detach": True,
        "wait-all": False,
        "elevated": False,
        "exclude-global-prep-cmd": False,
        "prep-cmd": [
            {
                "do": host_cmd(host_ps1, action),
                "undo": host_cmd(host_ps1, close_action),
            }
        ],
        "image-path": cover,
    }


def playnite_app(cover: str, host_ps1: str, exe: str) -> dict[str, object]:
    exe_path = Path(exe)
    return {
        "name": "Playnite",
        "cmd": f"{exe_path} --hidesplashscreen",
        "working-dir": str(exe_path.parent),
        "auto-detach": False,
        "wait-all": True,
        "elevated": False,
        "exclude-global-prep-cmd": False,
        "prep-cmd": [
            {
                "do": "",
                "undo": host_cmd(host_ps1, "playnite-close"),
            }
        ],
        "image-path": cover,
    }


def host_app(
    name: str,
    action: str,
    cover: str,
    host_ps1: str,
    working_dir: str,
    *,
    auto_detach: bool,
    elevated: bool,
    exclude_global_prep: bool = True,
) -> dict[str, object]:
    return {
        "name": name,
        "cmd": host_cmd(host_ps1, action),
        "working-dir": working_dir,
        "auto-detach": auto_detach,
        "wait-all": True,
        "elevated": elevated,
        "exclude-global-prep-cmd": exclude_global_prep,
        "image-path": cover,
    }


def main() -> int:
    args = parse_args()
    existing_path = Path(args.existing)
    payload: dict[str, object] = {"env": {}, "apps": []}
    if existing_path.is_file():
        raw = json.loads(existing_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            payload["env"] = raw.get("env") if isinstance(raw.get("env"), dict) else {}
            apps = raw.get("apps")
            if isinstance(apps, list):
                payload["apps"] = apps

    kept: list[object] = []
    for app in payload["apps"]:
        if not isinstance(app, dict):
            continue
        name = str(app.get("name") or "").strip()
        if name not in MANAGED_NAMES:
            kept.append(app)

    ps1 = args.host_ps1
    work = args.working_dir
    kept.extend(
        [
            host_app(
                "Cursor",
                "cursor",
                str(Path(args.cursor_cover)),
                ps1,
                work,
                auto_detach=True,
                elevated=False,
                exclude_global_prep=False,
            ),
            host_app(
                "Cursor Agents",
                "cursor-agents",
                str(Path(args.agents_cover)),
                ps1,
                work,
                auto_detach=True,
                elevated=False,
                exclude_global_prep=False,
            ),
        ]
    )
    if str(args.playnite_cover).strip() and str(args.playnite_exe).strip():
        kept.append(playnite_app(str(Path(args.playnite_cover)), ps1, str(Path(args.playnite_exe))))
    if str(args.youtube_cover).strip():
        kept.append(session_app("YouTube", "youtube", "youtube-close", str(Path(args.youtube_cover)), ps1, work))
    if str(args.brave_cover).strip():
        kept.append(session_app("Brave", "brave", "brave-close", str(Path(args.brave_cover)), ps1, work))
    kept.extend(
        [
            host_app("Sleep", "sleep", str(Path(args.sleep_cover)), ps1, work, auto_detach=False, elevated=False),
            host_app(
                "Restart Docker",
                "restart-docker",
                str(Path(args.docker_cover)),
                ps1,
                work,
                auto_detach=True,
                elevated=False,
            ),
            host_app(
                "Restart ChironAI",
                "restart-chironai",
                str(Path(args.chiron_cover)),
                ps1,
                work,
                auto_detach=True,
                elevated=False,
            ),
            host_app(
                "Restart PC",
                "restart-pc",
                str(Path(args.reboot_cover)),
                ps1,
                work,
                auto_detach=False,
                elevated=True,
            ),
        ]
    )
    out = {"env": payload["env"], "apps": kept}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Prepared {len(kept)} Sunshine apps at {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
