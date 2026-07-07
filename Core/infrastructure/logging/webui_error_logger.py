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

from infrastructure.database import get_logs_repository, get_notifications_repository

try:
    from flask import g, has_request_context, request
except Exception:  # pragma: no cover - logger can be imported outside Flask runtime
    g = None  # type: ignore[assignment]
    request = None  # type: ignore[assignment]

    def has_request_context() -> bool:
        return False


def _safe_notification_session_id() -> str:
    if not has_request_context():
        return "system"
    try:
        sid = getattr(g, "session_id", None) if g is not None else None
        if sid:
            return str(sid)
        if request is not None:
            sid = request.args.get("session_id")
            if not sid and request.is_json:
                body = request.get_json(silent=True) or {}
                sid = body.get("session_id")
            if sid:
                return str(sid)
    except Exception:  # safe: session id extraction best-effort outside request
        pass
    return "system"


def _notification_title_from_source(source: str) -> str:
    s = (source or "backend").strip()
    return s if s else "backend"


class NotificationMirrorHandler(logging.Handler):
    """Mirror WebUI error records into persisted notification center rows."""

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return
        try:
            source = record.getMessage().strip() or "backend"
            error = record.exc_info[1] if record.exc_info and record.exc_info[1] else None
            if error is not None:
                message = str(error).strip() or type(error).__name__
                error_type = type(error).__name__
            else:
                message = source
                error_type = record.levelname
            session_id = _safe_notification_session_id()
            aggregation_key = f"backend-error|{source}|{error_type}|{message[:160]}"
            get_notifications_repository().add_notification(
                session_id=session_id,
                kind="error",
                source="logs",
                title=_notification_title_from_source(source),
                message=message[:8000],
                metadata={
                    "historyOnly": False,
                    "origin": "backend_logger",
                    "error_type": error_type,
                    "session_scope": session_id,
                },
                aggregation_key=aggregation_key,
                is_console_error=True,
            )
        except Exception:
            # Never let notification mirroring break the primary logger.
            pass


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
    logger.addHandler(NotificationMirrorHandler())
    logger.setLevel(logging.INFO)
    return logger


def log_webui_error(
    source: str,
    error: Exception,
    extra: Optional[Dict[str, Any]] = None,
    logger: Optional[logging.Logger] = None,
    use_json: Optional[bool] = None,
    is_console_error: bool = False,
) -> None:
    """
    Log an error at the WebUI boundary (HTTP/CLI) or console errors.

    - Writes to rotating file via `webui_errors` logger.
    - Additionally mirrors a simplified entry into the SQLite `logs` table
      with `session_id='system'` so that it is visible in WebUI logs.
    - If `is_console_error` is True, the error is treated as a console error
      and logged with high priority.

    `source` is a short string like "rag_routes.chat_completions" or "console".
    """
    use_json_fmt = use_json if use_json is not None else (os.getenv("LOG_FORMAT", "").lower() == "json")
    log = logger or get_webui_error_logger(use_json=use_json_fmt)

    # Prepare clean message once so we can reuse it for file + DB
    clean_msg = _clean_message(source, error, extra)

    # 1) File logging
    if use_json_fmt:
        msg = _json_message(source, error, extra, include_tb=True)
        log.error(msg)
    else:
        log.error(clean_msg, exc_info=True)

    # 2) Mirror into SQLite logs so it appears in WebUI (debug panel, Logs tab)
    try:
        logs_repo = get_logs_repository()

        # Detect high-level category for easier filtering on UI
        message_text = str(error).lower()
        category = None
        if "ollama" in message_text or "port=11434" in message_text or "11434" in message_text:
            category = "ollama"

        metadata: Dict[str, Any] = dict(extra or {})
        if category and "category" not in metadata:
            metadata["category"] = category
        if is_console_error:
            metadata["console_error"] = True

        # Use a global/system session so logs are shared across WebUI sessions
        logs_repo.add_log(
            session_id="system",
            level="ERROR",
            message=clean_msg,
            source=category or source,
            error_type=type(error).__name__,
            metadata=metadata or None,
        )
    except Exception:
        # Never let logging failures break the main flow
        log.debug("Failed to mirror WebUI error into SQLite logs", exc_info=True)


__all__ = ["get_webui_error_logger", "log_webui_error"]
