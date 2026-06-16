"""
Configuration loader for ChironAI.

Reads YAML config files from the local `config/` directory and exposes
typed dictionaries with sensible defaults. Environment variables can
override YAML values where appropriate.
"""

from config import env as _env_module
from config import loader as _loader_module
from config.env import *  # noqa: F403
from config.loader import *  # noqa: F403

# Star-import skips leading-underscore names; re-export for `import config` callers.
_valid_server_port = _env_module._valid_server_port
_rsc = _loader_module._rsc
