"""
Logging infrastructure.

WebUI error logger for HTTP/CLI boundaries.
"""

from infrastructure.logging.webui_error_logger import (
    get_webui_error_logger,
    log_webui_error,
)

__all__ = ["get_webui_error_logger", "log_webui_error"]
