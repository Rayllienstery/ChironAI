"""HTTP security headers for ChironAI Flask applications."""

from __future__ import annotations

from typing import Any

SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self' http://127.0.0.1:* http://localhost:* ws://127.0.0.1:* ws://localhost:*; "
        "frame-src 'self' http://127.0.0.1:* http://localhost:*; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'self'"
    ),
}


def apply_security_headers(response: Any) -> Any:
    """Attach default hardening headers without overwriting explicit route headers."""

    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


def register_security_headers(app: Any) -> None:
    """Register the security header middleware on a Flask app."""

    app.after_request(apply_security_headers)


__all__ = ["SECURITY_HEADERS", "apply_security_headers", "register_security_headers"]
