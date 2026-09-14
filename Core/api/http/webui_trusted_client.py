"""Loopback client checks for sensitive WebUI management routes."""

from __future__ import annotations

import hmac
import ipaddress
from typing import TYPE_CHECKING, Any

from core.contracts.webui_api import PHONE_STATUS_TOKEN_HEADER

if TYPE_CHECKING:
    from flask import Request

REVEAL_PIN_HEADER = "X-Chiron-Reveal-Pin"


def is_loopback_client_request(request: Request) -> bool:
    """Return True when the HTTP client connected from a loopback address."""
    remote_addr = (request.remote_addr or "").strip()
    if not remote_addr:
        return False
    try:
        return ipaddress.ip_address(remote_addr).is_loopback
    except ValueError:
        return False


def loopback_client_required_response() -> tuple:
    """Build a 403 response for non-loopback proxy API key management."""
    from error_manager.http import error_response

    return error_response(
        "Proxy API key management is allowed only from the local machine. "
        "Open the WebUI at http://127.0.0.1:<port>/webui.",
        status=403,
    )


def extract_reveal_pin_from_request(request: Request) -> str:
    """Read reveal PIN from JSON body, ``X-Chiron-Reveal-Pin`` header, or query ``pin``."""
    body = request.get_json(force=True, silent=True) or {}
    if isinstance(body, dict):
        pin = str(body.get("pin") or "").strip()
        if pin:
            return pin
    header_pin = (request.headers.get(REVEAL_PIN_HEADER) or "").strip()
    if header_pin:
        return header_pin
    return str(request.args.get("pin") or "").strip()


def check_remote_reveal_pin(request: Request, settings_repo: Any) -> tuple | None:
    """Return an error response for denied LAN access, or ``None`` if allowed.

    Loopback clients bypass PIN checks.  Non-loopback clients must supply the
    configured reveal PIN (same policy as ``POST /llm-proxy/api-key/reveal``).
    """
    if is_loopback_client_request(request):
        return None
    from error_manager.http import error_response
    from llm_proxy.reveal_pin import PinError, verify_pin_for_reveal

    pin = extract_reveal_pin_from_request(request)
    try:
        verify_pin_for_reveal(settings_repo, pin)
    except PinError as e:
        return error_response(e.message, 403, extra={"code": e.code})
    return None


def extract_phone_status_token_from_request(request: Request) -> str:
    """Read the phone-status token from header or ``Authorization: Bearer``."""
    header_token = (request.headers.get(PHONE_STATUS_TOKEN_HEADER) or "").strip()
    if header_token:
        return header_token
    authorization = (request.headers.get("Authorization") or "").strip()
    prefix = "bearer "
    if authorization.lower().startswith(prefix):
        return authorization[len(prefix) :].strip()
    return str(request.args.get("token") or "").strip()


def check_phone_status_access(request: Request) -> tuple | None:
    """Allow loopback always; require ``CHIRONAI_PHONE_STATUS_TOKEN`` off-loopback."""
    if is_loopback_client_request(request):
        return None
    from error_manager.http import error_response

    from config.env import get_phone_status_token

    configured = get_phone_status_token()
    if not configured:
        return error_response(
            "Phone status is loopback-only unless CHIRONAI_PHONE_STATUS_TOKEN is set.",
            403,
        )
    provided = extract_phone_status_token_from_request(request)
    if not provided or not hmac.compare_digest(provided, configured):
        return error_response("Invalid or missing phone status token.", 403)
    return None
