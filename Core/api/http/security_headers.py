"""HTTP security headers for ChironAI Flask applications."""

from __future__ import annotations

from typing import Any

from flask import request

SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        # P1.4: documented risk acceptance — docs/CSP_RISK_ACCEPTANCE.md (0.8.49)
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

HSTS_HEADER_VALUE = "max-age=31536000; includeSubDomains"


def _request_is_https() -> bool:
    if request.is_secure:
        return True
    forwarded = str(request.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
    return forwarded == "https"


def apply_security_headers(response: Any) -> Any:
    """Attach default hardening headers without overwriting explicit route headers."""

    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if _request_is_https():
        response.headers.setdefault("Strict-Transport-Security", HSTS_HEADER_VALUE)
    return response


def register_security_headers(app: Any) -> None:
    """Register the security header middleware on a Flask app."""

    app.after_request(apply_security_headers)


__all__ = ["HSTS_HEADER_VALUE", "SECURITY_HEADERS", "apply_security_headers", "register_security_headers"]
