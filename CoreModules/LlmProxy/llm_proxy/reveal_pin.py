"""Remote reveal PIN for the WebUI-managed Chiron /v1 proxy API key.

Scope: only the ``POST /llm-proxy/api-key/reveal`` route from a non-loopback
client.  Generate/delete remain loopback-only.  The PIN is stored as a bcrypt
hash in the settings repository; plaintext PINs never persist.
"""

from __future__ import annotations

import re
from typing import Any

import bcrypt

LLM_PROXY_REVEAL_PIN_HASH_SETTING = "llm_proxy_reveal_pin_hash"
LLM_PROXY_REVEAL_PIN_FAILED_ATTEMPTS_SETTING = "llm_proxy_reveal_pin_failed_attempts"

MAX_FAILED_ATTEMPTS = 3
PIN_REGEX = re.compile(r"^\d{4,8}$")


class PinError(Exception):
    """PIN-specific error with a machine-readable code."""

    code = "PIN_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class PinRequiredError(PinError):
    code = "PIN_REQUIRED"


class PinInvalidError(PinError):
    code = "PIN_INVALID"


class PinLockedOutError(PinError):
    code = "PIN_LOCKED_OUT"


class PinNotConfiguredError(PinError):
    code = "PIN_NOT_CONFIGURED"


class PinAlreadyConfiguredError(PinError):
    code = "PIN_ALREADY_CONFIGURED"


def _delete_setting(settings_repo: Any, key: str) -> None:
    if hasattr(settings_repo, "delete_app_setting"):
        settings_repo.delete_app_setting(key)
        return
    settings_repo.set_app_setting(key, "")


def _get_int_setting(settings_repo: Any, key: str, default: int = 0) -> int:
    raw = settings_repo.get_app_setting(key)
    if not raw:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def _set_int_setting(settings_repo: Any, key: str, value: int) -> None:
    settings_repo.set_app_setting(key, str(value))


def _get_hash(settings_repo: Any) -> str:
    return settings_repo.get_app_setting(LLM_PROXY_REVEAL_PIN_HASH_SETTING) or ""


def _set_hash(settings_repo: Any, pin_hash: str) -> None:
    settings_repo.set_app_setting(LLM_PROXY_REVEAL_PIN_HASH_SETTING, pin_hash)


def _get_failed_attempts(settings_repo: Any) -> int:
    return _get_int_setting(settings_repo, LLM_PROXY_REVEAL_PIN_FAILED_ATTEMPTS_SETTING, 0)


def _set_failed_attempts(settings_repo: Any, value: int) -> None:
    _set_int_setting(settings_repo, LLM_PROXY_REVEAL_PIN_FAILED_ATTEMPTS_SETTING, value)


def _hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _verify_pin(pin: str, pin_hash: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode("utf-8"), pin_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def is_pin_valid(pin: str) -> bool:
    """Return True when ``pin`` is a 4-8 digit string."""
    return bool(pin and isinstance(pin, str) and PIN_REGEX.fullmatch(pin))


def is_pin_configured(settings_repo: Any) -> bool:
    return bool(_get_hash(settings_repo))


def is_locked_out(settings_repo: Any) -> bool:
    return _get_failed_attempts(settings_repo) >= MAX_FAILED_ATTEMPTS


def get_pin_status(settings_repo: Any) -> dict[str, Any]:
    return {
        "configured": is_pin_configured(settings_repo),
        "locked_out": is_locked_out(settings_repo),
    }


def set_pin(settings_repo: Any, pin: str) -> None:
    """Install a new reveal PIN (loopback only)."""
    if not is_pin_valid(pin):
        raise PinError("PIN must be 4 to 8 digits")
    if is_pin_configured(settings_repo):
        raise PinAlreadyConfiguredError("PIN is already configured; use Change PIN instead")
    _set_hash(settings_repo, _hash_pin(pin))
    _set_failed_attempts(settings_repo, 0)


def change_pin(settings_repo: Any, current_pin: str, new_pin: str) -> None:
    """Change an existing reveal PIN (loopback only).

    Does not affect the LAN reveal lockout counter; that counter is only
    incremented by failed remote reveal attempts.
    """
    if not is_pin_valid(new_pin):
        raise PinError("New PIN must be 4 to 8 digits")
    if not is_pin_configured(settings_repo):
        raise PinNotConfiguredError("PIN is not configured")
    if not _verify_pin(current_pin, _get_hash(settings_repo)):
        raise PinInvalidError("Current PIN is incorrect")
    _set_hash(settings_repo, _hash_pin(new_pin))
    _set_failed_attempts(settings_repo, 0)


def disable_pin(settings_repo: Any, pin: str) -> None:
    """Remove the reveal PIN (loopback only).

    Does not affect the LAN reveal lockout counter; that counter is only
    incremented by failed remote reveal attempts.
    """
    if not is_pin_configured(settings_repo):
        raise PinNotConfiguredError("PIN is not configured")
    if not _verify_pin(pin, _get_hash(settings_repo)):
        raise PinInvalidError("PIN is incorrect")
    _delete_setting(settings_repo, LLM_PROXY_REVEAL_PIN_HASH_SETTING)
    _set_failed_attempts(settings_repo, 0)


def reset_lockout(settings_repo: Any) -> None:
    """Reset the failed-attempt counter (loopback only)."""
    _set_failed_attempts(settings_repo, 0)


def verify_pin_for_reveal(settings_repo: Any, pin: str) -> None:
    """Verify a LAN reveal attempt.  Raises PinError subclasses on failure.

    Side effects:
    - Increments the failed-attempt counter on invalid/empty PIN.
    - Resets the counter on success.
    """
    if not is_pin_configured(settings_repo):
        raise PinNotConfiguredError(
            "Remote reveal requires a PIN. Install one from the local machine first."
        )
    if is_locked_out(settings_repo):
        raise PinLockedOutError(_LOCKOUT_MESSAGE)
    if not pin:
        _set_failed_attempts(settings_repo, _get_failed_attempts(settings_repo) + 1)
        raise PinRequiredError("PIN is required for remote reveal")
    if not is_pin_valid(pin):
        _set_failed_attempts(settings_repo, _get_failed_attempts(settings_repo) + 1)
        if is_locked_out(settings_repo):
            raise PinLockedOutError(_LOCKOUT_MESSAGE)
        raise PinInvalidError("PIN must be 4 to 8 digits")
    if not _verify_pin(pin, _get_hash(settings_repo)):
        _set_failed_attempts(settings_repo, _get_failed_attempts(settings_repo) + 1)
        if is_locked_out(settings_repo):
            raise PinLockedOutError(_LOCKOUT_MESSAGE)
        raise PinInvalidError("Invalid PIN")
    _set_failed_attempts(settings_repo, 0)


_LOCKOUT_MESSAGE = (
    "PIN is locked. To reset the PIN, open ChironAI WebUI on the machine "
    "where the server is running (http://127.0.0.1:<port>/webui) and use "
    "Reset PIN in Tokens and Security → Remote Access."
)
