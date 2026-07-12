"""Observability routes for the WebUI blueprint."""

from __future__ import annotations

import time
from typing import Any

from error_manager.http import error_response as _error_response
from flask import Blueprint, jsonify, request

from api.http.proxy_status import get_proxy_status_label
from api.http.proxy_trace import (
    annotate_proxy_trace_for_ui,
    clear_proxy_trace_buffer,
    get_active_traces,
    get_current_trace,
    get_current_trace_updated_at,
    recent_proxy_traces,
)
from api.http.webui_trusted_client import check_remote_reveal_pin
from infrastructure.database import get_logs_repository, get_notifications_repository, get_settings_repository


def _require_remote_reveal_pin_for_logs() -> Any | None:
    """Gate sensitive log reads/writes from non-loopback clients."""
    return check_remote_reveal_pin(request, get_settings_repository())


def _parse_since_id_query(raw: str | None) -> int | None:
    """Parse ``since_id`` query param; ``None`` if absent or empty. ``0`` is valid."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _log_webui_logs_read_duration(
    logs_repo: Any,
    *,
    endpoint: str,
    limit: int,
    since_id: int | None,
    duration_ms: float,
) -> None:
    """Append timing row to system logs. Skip fast incremental polls (anti-spam)."""
    try:
        incremental = since_id is not None
        if incremental and duration_ms < 250.0:
            return
        # Proxy list polls often omit since_id with a date window; avoid a row every few seconds.
        if not incremental and "proxy-logs" in endpoint and duration_ms < 250.0:
            return
        msg = (
            f"{endpoint} limit={limit} since_id={since_id if since_id is not None else 'none'} "
            f"duration_ms={duration_ms:.1f}"
        )
        logs_repo.add_log(
            "system",
            "INFO",
            msg,
            source="webui_api",
            error_type=None,
            metadata={
                "endpoint": endpoint,
                "limit": limit,
                "since_id": since_id,
                "duration_ms": round(duration_ms, 2),
            },
        )
    except Exception:  # safe: observability logging must not break requests
        pass


def register_observability_routes(bp: Blueprint, *, error_log: Any) -> None:
    @bp.route("/logs", methods=["GET"])
    def get_logs() -> Any:
        """Return recent log entries from database."""
        try:
            denied = _require_remote_reveal_pin_for_logs()
            if denied is not None:
                return denied
            session_id = request.args.get("session_id")
            limit = int(request.args.get("limit", 100))
            level = request.args.get("level", "").upper() or None
            source = request.args.get("source") or None
            since_id_val = _parse_since_id_query(request.args.get("since_id"))

            if not session_id:
                return _error_response("session_id is required", 400)

            logs_repo = get_logs_repository()
            t0 = time.perf_counter()
            logs = logs_repo.get_logs(
                session_id=session_id,
                level=level,
                limit=limit,
                since_id=since_id_val,
                source=source,
            )
            duration_ms = (time.perf_counter() - t0) * 1000.0
            _log_webui_logs_read_duration(
                logs_repo,
                endpoint="GET /api/webui/logs",
                limit=limit,
                since_id=since_id_val,
                duration_ms=duration_ms,
            )

            return jsonify({"logs": logs})
        except Exception as e:
            error_log.error("webui_observability_routes.get_logs", exc_info=True)
            return _error_response(e)

    @bp.route("/notifications", methods=["GET"])
    def get_coreui_notifications() -> Any:
        """List CoreUI notification center entries for a session."""
        try:
            session_id = request.args.get("session_id")
            if not session_id:
                return _error_response("session_id is required", 400)
            limit = min(500, max(1, int(request.args.get("limit", 200))))
            include_raw = (request.args.get("include_dismissed") or "true").strip().lower()
            include_dismissed = include_raw in ("1", "true", "yes")
            repo = get_notifications_repository()
            items = repo.list_notifications(
                session_id=session_id,
                limit=limit,
                include_dismissed=include_dismissed,
            )
            if session_id != "system":
                system_items = repo.list_notifications(
                    session_id="system",
                    limit=limit,
                    include_dismissed=include_dismissed,
                )
                items.extend(system_items)
                items.sort(
                    key=lambda n: (
                        str(n.get("last_occurrence_at") or n.get("created_at") or ""),
                        int(n.get("id") or 0),
                    ),
                    reverse=True,
                )
                items = items[:limit]
            return jsonify({"notifications": items})
        except Exception as e:
            error_log.error("webui_observability_routes.get_coreui_notifications", exc_info=True)
            return _error_response(e)

    @bp.route("/notifications", methods=["POST"])
    def create_coreui_notification() -> Any:
        """Create a persisted notification (error or event)."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            session_id = body.get("session_id")
            kind = (body.get("kind") or "event").strip().lower()
            source = (body.get("source") or "").strip()
            title = (body.get("title") or "").strip()
            message = body.get("message") or ""
            metadata = body.get("metadata")
            aggregation_key = (body.get("aggregation_key") or "").strip()

            if not session_id:
                return _error_response("session_id is required", 400)
            if kind not in ("error", "event", "info"):
                return _error_response("kind must be error, event, or info", 400)
            if not source:
                return _error_response("source is required", 400)
            if not title:
                return _error_response("title is required", 400)
            if not isinstance(message, str):
                message = str(message)
            if len(message) > 8000:
                message = message[:8000] + "..."
            meta_dict: dict[str, Any] | None = None
            if metadata is not None:
                if not isinstance(metadata, dict):
                    return _error_response("metadata must be an object", 400)
                meta_dict = metadata
            if not aggregation_key:
                aggregation_key = None

            nid = get_notifications_repository().add_notification(
                session_id=session_id,
                kind=kind,
                source=source,
                title=title,
                message=message,
                metadata=meta_dict,
                aggregation_key=aggregation_key,
            )
            return jsonify({"id": nid})
        except Exception as e:
            error_log.error("webui_observability_routes.create_coreui_notification", exc_info=True)
            return _error_response(e)

    @bp.route("/notifications/<int:nid>/dismiss", methods=["PATCH"])
    def dismiss_coreui_notification(nid: int) -> Any:
        """Mark a notification as dismissed."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            session_id = body.get("session_id") or request.args.get("session_id")
            if not session_id:
                return _error_response("session_id is required", 400)
            repo = get_notifications_repository()
            ok = repo.dismiss(session_id, nid)
            if not ok and session_id != "system":
                ok = repo.dismiss("system", nid)
            if not ok:
                return _error_response("not found or already dismissed", 404)
            return jsonify({"ok": True})
        except Exception as e:
            error_log.error("webui_observability_routes.dismiss_coreui_notification", exc_info=True)
            return _error_response(e)

    @bp.route("/notifications/clear", methods=["POST"])
    def clear_coreui_notifications() -> Any:
        """Remove all persisted notifications for the session (live activities unaffected)."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            session_id = body.get("session_id")
            if not session_id:
                return _error_response("session_id is required", 400)
            deleted = get_notifications_repository().clear_session(session_id)
            return jsonify({"deleted": deleted})
        except Exception as e:
            error_log.error("webui_observability_routes.clear_coreui_notifications", exc_info=True)
            return _error_response(e)

    @bp.route("/proxy-logs", methods=["GET"])
    def get_proxy_logs() -> Any:
        """Return proxy logs from database (``session_id=proxy``, ``source=proxy``)."""
        try:
            denied = _require_remote_reveal_pin_for_logs()
            if denied is not None:
                return denied
            limit = int(request.args.get("limit", 100))
            since_id_val = _parse_since_id_query(request.args.get("since_id"))
            from_date = request.args.get("from")
            to_date = request.args.get("to")
            ac_raw = (request.args.get("autocomplete_only") or "").strip().lower()
            autocomplete_only = ac_raw in ("1", "true", "yes")

            logs_repo = get_logs_repository()
            t0 = time.perf_counter()
            if autocomplete_only:
                logs = logs_repo.get_logs(
                    session_id="proxy",
                    level="INFO",
                    limit=limit,
                    since_id=since_id_val,
                    source="proxy",
                    from_date=from_date or None,
                    to_date=to_date or None,
                    autocomplete_only=True,
                )
            else:
                logs = logs_repo.get_logs(
                    session_id="proxy",
                    level="INFO",
                    limit=limit,
                    since_id=since_id_val,
                    source="proxy",
                    include_system=False,
                    from_date=from_date or None,
                    to_date=to_date or None,
                )
            duration_ms = (time.perf_counter() - t0) * 1000.0
            _log_webui_logs_read_duration(
                logs_repo,
                endpoint="GET /api/webui/proxy-logs",
                limit=limit,
                since_id=since_id_val,
                duration_ms=duration_ms,
            )

            return jsonify({"logs": logs})
        except Exception as e:
            error_log.error("webui_observability_routes.get_proxy_logs", exc_info=True)
            return _error_response(e)

    @bp.route("/proxy-trace/current", methods=["GET"])
    def get_proxy_trace_current() -> Any:
        """Return the latest live trace from in-memory store."""
        try:
            denied = _require_remote_reveal_pin_for_logs()
            if denied is not None:
                return denied
            trace = get_current_trace()
            active_traces = get_active_traces()
            updated_at = get_current_trace_updated_at()
            return jsonify(
                {
                    "trace": trace,
                    "active_traces": active_traces,
                    "status": get_proxy_status_label(),
                    "updated_at": updated_at,
                }
            )
        except Exception as e:
            error_log.error("webui_observability_routes.get_proxy_trace_current", exc_info=True)
            return _error_response(e)

    @bp.route("/proxy-traces", methods=["GET"])
    def get_proxy_traces() -> Any:
        """Ring-buffer snapshots of LLM proxy traces, UI-oriented JSON."""
        denied = _require_remote_reveal_pin_for_logs()
        if denied is not None:
            return denied
        try:
            lim_raw = request.args.get("limit", "40")
            limit = max(1, min(200, int(lim_raw)))
        except (TypeError, ValueError):
            limit = 40
        try:
            rows = list(reversed(recent_proxy_traces(limit)))
            traces = [annotate_proxy_trace_for_ui(r) if isinstance(r, dict) else r for r in rows]
            return jsonify({"available": True, "traces": traces})
        except Exception as e:
            error_log.error("webui_observability_routes.get_proxy_traces", exc_info=True)
            return _error_response(e)

    @bp.route("/proxy-traces/clear", methods=["POST"])
    def post_proxy_traces_clear() -> Any:
        try:
            denied = _require_remote_reveal_pin_for_logs()
            if denied is not None:
                return denied
            clear_proxy_trace_buffer()
            return jsonify({"ok": True})
        except Exception as e:
            error_log.error("webui_observability_routes.post_proxy_traces_clear", exc_info=True)
            return _error_response(e)

    @bp.route("/proxy-journal", methods=["GET"])
    def get_proxy_journal() -> Any:
        """Persisted proxy request rows only (session_id=proxy)."""
        denied = _require_remote_reveal_pin_for_logs()
        if denied is not None:
            return denied
        try:
            lim_raw = request.args.get("limit", "50")
            limit = max(1, min(5000, int(lim_raw)))
        except (TypeError, ValueError):
            limit = 50
        since_id_val = _parse_since_id_query(request.args.get("since_id"))
        try:
            off_raw = request.args.get("offset", "0")
            offset = max(0, int(off_raw))
        except (TypeError, ValueError):
            offset = 0
        from_date = (request.args.get("from") or "").strip() or None
        to_date = (request.args.get("to") or "").strip() or None
        try:
            logs_repo = get_logs_repository()
            common_kwargs = {
                "from_date": from_date,
                "to_date": to_date,
            }
            if since_id_val is not None:
                logs = logs_repo.get_logs(
                    session_id="proxy",
                    level="INFO",
                    source="proxy",
                    include_system=False,
                    from_date=from_date,
                    to_date=to_date,
                    limit=limit,
                    since_id=since_id_val,
                    newest_first=True,
                )
                return jsonify({"ok": True, "logs": logs})
            logs = logs_repo.get_proxy_journal_groups(
                **common_kwargs,
                limit=limit,
                offset=offset,
            )
            total = logs_repo.count_proxy_journal_groups(**common_kwargs)
            return jsonify({"ok": True, "logs": logs, "total": total, "offset": offset, "limit": limit})
        except Exception as e:
            error_log.error("webui_observability_routes.get_proxy_journal", exc_info=True)
            return jsonify({"ok": False, "logs": [], "error": str(e)}), 500

    @bp.route("/proxy-journal", methods=["DELETE"])
    def delete_proxy_journal() -> Any:
        """Delete persisted proxy log rows (same scope as DELETE /proxy-logs without autocomplete filter)."""
        try:
            denied = _require_remote_reveal_pin_for_logs()
            if denied is not None:
                return denied
            logs_repo = get_logs_repository()
            deleted = logs_repo.delete_proxy_logs(autocomplete_only=False)
            return jsonify({"ok": True, "deleted_count": deleted})
        except Exception as e:
            error_log.error("webui_observability_routes.delete_proxy_journal", exc_info=True)
            return jsonify({"ok": False, "error": str(e)}), 500

    @bp.route("/logs", methods=["POST"])
    def create_log() -> Any:
        """Create a log entry."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            session_id = body.get("session_id")
            level = body.get("level", "INFO").upper()
            message = body.get("message", "")
            source = body.get("source")
            error_type = body.get("error_type")
            metadata = body.get("metadata")

            if not session_id or not message:
                return _error_response("session_id and message are required", 400)

            logs_repo = get_logs_repository()
            log_id = logs_repo.add_log(
                session_id=session_id,
                level=level,
                message=message,
                source=source,
                error_type=error_type,
                metadata=metadata,
            )

            return jsonify({"id": log_id, "status": "created"})
        except Exception as e:
            error_log.error("webui_observability_routes.create_log", exc_info=True)
            return _error_response(e)

    @bp.route("/logs", methods=["DELETE"])
    def delete_logs() -> Any:
        """Delete log entries for a session from the database (matches GET scope by default)."""
        try:
            denied = _require_remote_reveal_pin_for_logs()
            if denied is not None:
                return denied
            session_id = request.args.get("session_id")
            if not session_id:
                return _error_response("session_id is required", 400)
            inc_raw = (request.args.get("include_system") or "1").strip().lower()
            include_system = inc_raw not in ("0", "false", "no")

            logs_repo = get_logs_repository()
            deleted = logs_repo.delete_logs_for_session(session_id, include_system=include_system)
            return jsonify({"status": "ok", "deleted_count": deleted})
        except Exception as e:
            error_log.error("webui_observability_routes.delete_logs", exc_info=True)
            return _error_response(e)

    @bp.route("/proxy-logs", methods=["DELETE"])
    def delete_proxy_logs() -> Any:
        """Delete proxy (and optionally autocomplete-only) logs from the database."""
        try:
            denied = _require_remote_reveal_pin_for_logs()
            if denied is not None:
                return denied
            ac_raw = (request.args.get("autocomplete_only") or "").strip().lower()
            autocomplete_only = ac_raw in ("1", "true", "yes")

            logs_repo = get_logs_repository()
            deleted = logs_repo.delete_proxy_logs(autocomplete_only=autocomplete_only)
            return jsonify({"status": "ok", "deleted_count": deleted})
        except Exception as e:
            error_log.error("webui_observability_routes.delete_proxy_logs", exc_info=True)
            return _error_response(e)


__all__ = ["register_observability_routes"]
