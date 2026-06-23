"""LogsManager — read-only RAG Fusion proxy journal access for internal LLM use."""

from logs_manager.manager import LogsManager, get_logs_manager

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "LogsManager",
    "get_logs_manager",
]
