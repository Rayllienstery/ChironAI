"""WebUI use cases: aggregate data from RAG/crawler/ingestion via ports."""

from __future__ import annotations

from webui_backend.domain.entities import DashboardStats
from webui_backend.domain.ports import CrawlerClient, RagClient


def get_dashboard_stats(
    rag_client: RagClient | None,
    crawler_client: CrawlerClient | None,
) -> DashboardStats:
    """Aggregate dashboard stats from RAG and crawler (and optional ingestion)."""
    rag_status = "unknown"
    crawler_status = "unknown"
    if rag_client:
        try:
            r = rag_client.health()
            rag_status = "ok" if r.get("status") == "ok" else "error"
        except Exception:
            rag_status = "unreachable"
    if crawler_client:
        try:
            crawler_client.list_sources()
            crawler_status = "ok"
        except Exception:
            crawler_status = "unreachable"
    return DashboardStats(rag_status=rag_status, crawler_status=crawler_status)


__all__ = ["get_dashboard_stats"]
