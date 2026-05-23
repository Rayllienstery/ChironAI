"""Print the WebUI URL for batch launch scripts."""

from __future__ import annotations

from config import get_server_port


def main() -> None:
    print(f"http://localhost:{get_server_port()}/webui")


if __name__ == "__main__":
    main()
