"""
WebUI error logger.

Dedicated logger for HTTP/CLI boundaries: file handler with rotation,
structured format (timestamp, level, source, stage, error_type, message).
Clean one-line format or JSON Lines via LOG_FORMAT=json.
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional


def _clean_message(source: str, error: Exception, extra: Optional[Dict[str, Any]] = None) -> str:
    """One-line user-friendly: source= stage= error_type= message=."""
    stage = (extra or {}).get("stage", "")
    err_type = type(error).__name__
    msg = str(error).replace("\n", " ").strip()
    parts = [f"source={source}"]
    if stage:
        parts.append(f"stage={stage}")
    parts.append(f"error_type={err_type}")
    parts.append(f"message={msg}")
    return " ".join(parts)


def _json_message(
    source: str, error: Exception, extra: Optional[Dict[str, Any]] = None, include_tb: bool = True
) -> str:
    """JSON Lines: one JSON object per line."""
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": "ERROR",
        "source": source,
        "stage": (extra or {}).get("stage", ""),
        "error_type": type(error).__name__,
        "message": str(error).replace("\n", " ").strip(),
    }
    if extra:
        payload["extra"] = {k: v for k, v in extra.items() if k != "stage"}
    if include_tb:
        payload["traceback"] = traceback.format_exc()
    return json.dumps(payload, ensure_ascii=False)


def get_webui_error_logger(
    log_dir: str = "logs",
    log_file: str = "webui_errors.log",
    max_bytes: int = 2 * 1024 * 1024,
    backup_count: int = 3,
    use_json: bool = False,
) -> logging.Logger:
    """
    Return a logger configured for WebUI errors: file handler with rotation.
    Format: clean one-line (source= stage= error_type= message=) or JSON Lines if use_json.
    """
    use_json = use_json or os.getenv("LOG_FORMAT", "").lower() == "json"
    logger = logging.getLogger("webui_errors")
    if logger.handlers:
        return logger
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, log_file)
    handler = RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    if use_json:
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        # Clean format: timestamp [LEVEL] source= ... stage= ... error_type= ... message= ...
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def log_webui_error(
    source: str,
    error: Exception,
    extra: Optional[Dict[str, Any]] = None,
    logger: Optional[logging.Logger] = None,
    use_json: Optional[bool] = None,
) -> None:
    """
    Log an error at the WebUI boundary (HTTP/CLI).
    source: e.g. "rag_routes.chat_completions"
    Writes clean one-line to file (or JSON Lines if LOG_FORMAT=json). Includes exc_info.
    """
    use_json_fmt = use_json if use_json is not None else (os.getenv("LOG_FORMAT", "").lower() == "json")
    log = logger or get_webui_error_logger(use_json=use_json_fmt)
    if use_json_fmt:
        msg = _json_message(source, error, extra, include_tb=True)
        log.error(msg)
    else:
        msg = _clean_message(source, error, extra)
        log.error(msg, exc_info=True)


__all__ = ["get_webui_error_logger", "log_webui_error"]
