"""Extension-management module boundary for repository-backed extensions."""

from extensions_backend.repository_metadata import GitHubExtensionRepositoryClient
from extensions_backend.blocklist import ExtensionBlocklistMatch, ExtensionBlocklistPolicy
from extensions_backend.registry_client import (
    ExtensionRegistryClient,
    ExtensionRegistryDiagnostic,
    ExtensionRegistryLoadResult,
)
from extensions_backend.service import ExtensionManagementService

__all__ = [
    "ExtensionBlocklistMatch",
    "ExtensionBlocklistPolicy",
    "ExtensionManagementService",
    "ExtensionRegistryClient",
    "ExtensionRegistryDiagnostic",
    "ExtensionRegistryLoadResult",
    "GitHubExtensionRepositoryClient",
]
