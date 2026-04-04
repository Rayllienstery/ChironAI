"""In-memory ring buffer of ClawCode request traces (shared with WebUI API on 8080)."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

_lock = threading.RLock()
_buffer: deque[dict[str, Any]] = deque(maxlen=80)


def configure(maxlen: int) -> None:
    global _buffer
    m = max(10, int(maxlen))
    with _lock:
        old = list(_buffer)
        _buffer = deque(old[-m:], maxlen=m)


def append(record: dict[str, Any]) -> None:
    with _lock:
        _buffer.append(record)


def recent(limit: int = 40) -> list[dict[str, Any]]:
    with _lock:
        items = list(_buffer)
    return items[-max(1, limit) :]


def clear() -> None:
    with _lock:
        _buffer.clear()


def now_ms() -> int:
    return int(time.time() * 1000)
