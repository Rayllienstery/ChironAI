"""Domain errors for MD ingestion."""


class IngestionError(Exception):
    """Raised when ingestion or filtering fails in a domain-visible way."""
