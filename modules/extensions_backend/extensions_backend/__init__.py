"""Extension-management module boundary for repository-backed extensions."""

from extensions_backend.repository_metadata import GitHubExtensionRepositoryClient
from extensions_backend.blocklist import ExtensionBlocklistMatch, ExtensionBlocklistPolicy

__all__ = ["ExtensionBlocklistMatch", "ExtensionBlocklistPolicy", "GitHubExtensionRepositoryClient"]
