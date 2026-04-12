"""
Metrics collector for ChironAI observability.

Provides counters, gauges, and histograms for RAG requests, latency, and quality metrics.
Thread-safe with in-memory storage (last N values for histograms).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


@dataclass
class MetricPoint:
    """Single metric measurement."""
    timestamp: float
    value: float
    tags: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """
    In-memory metrics collector with thread-safe operations.
    
    Supports:
    - Counters: monotonically increasing values (e.g., request count)
    - Gauges: point-in-time values (e.g., current queue size)
    - Histograms: distribution of values (e.g., latency percentiles)
    """
    
    def __init__(self, max_histogram_size: int = 1000):
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._max_histogram_size = max_histogram_size
        self._lock = threading.Lock()
    
    def increment(self, name: str, value: int = 1, tags: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter by value."""
        key = self._make_key(name, tags)
        with self._lock:
            self._counters[key] += value
    
    def gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge value."""
        key = self._make_key(name, tags)
        with self._lock:
            self._gauges[key] = value
    
    def histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a value in a histogram."""
        key = self._make_key(name, tags)
        with self._lock:
            self._histograms[key].append(value)
            # Trim to max size to prevent memory growth
            if len(self._histograms[key]) > self._max_histogram_size:
                self._histograms[key] = self._histograms[key][-self._max_histogram_size:]
    
    def get_counter(self, name: str, tags: Optional[Dict[str, str]] = None) -> int:
        """Get current counter value."""
        key = self._make_key(name, tags)
        with self._lock:
            return self._counters.get(key, 0)
    
    def get_gauge(self, name: str, tags: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Get current gauge value."""
        key = self._make_key(name, tags)
        with self._lock:
            return self._gauges.get(key)
    
    def get_histogram_values(self, name: str, tags: Optional[Dict[str, str]] = None) -> List[float]:
        """Get all values in histogram."""
        key = self._make_key(name, tags)
        with self._lock:
            return list(self._histograms.get(key, []))
    
    def get_percentiles(
        self, 
        name: str, 
        percentiles: List[float] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> Dict[str, float]:
        """
        Calculate percentiles for a histogram.
        
        Args:
            name: Metric name
            percentiles: List of percentiles to calculate (default: [50, 95, 99])
            tags: Optional tags to filter by
            
        Returns:
            Dict mapping percentile names to values (e.g., {"p50": 123.4, "p95": 456.7})
        """
        if percentiles is None:
            percentiles = [50, 95, 99]
        
        key = self._make_key(name, tags)
        with self._lock:
            values = self._histograms.get(key, [])
        
        if not values:
            return {}
        
        if HAS_NUMPY:
            return {
                f"p{int(p)}": float(np.percentile(values, p))
                for p in percentiles
            }
        else:
            # Fallback without numpy
            sorted_values = sorted(values)
            n = len(sorted_values)
            result = {}
            for p in percentiles:
                idx = int((p / 100) * (n - 1))
                result[f"p{int(p)}"] = sorted_values[idx]
            return result
    
    def get_stats(self, name: str, tags: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get basic statistics for a histogram (avg, min, max, count)."""
        key = self._make_key(name, tags)
        with self._lock:
            values = self._histograms.get(key, [])
        
        if not values:
            return {}
        
        return {
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "count": len(values),
        }
    
    def _make_key(self, name: str, tags: Optional[Dict[str, str]] = None) -> str:
        """Create a unique key from name and tags."""
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}{{{tag_str}}}"
    
    def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
    
    def export_all(self) -> Dict[str, object]:
        """Export all metrics as a dictionary."""
        with self._lock:
            result = {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    k: {
                        "values": list(v),
                        "percentiles": self._calc_percentiles(v) if HAS_NUMPY else {},
                    }
                    for k, v in self._histograms.items()
                },
            }
        return result
    
    def _calc_percentiles(self, values: List[float]) -> Dict[str, float]:
        """Calculate percentiles for a list of values."""
        if not values:
            return {}
        return {
            "p50": float(np.percentile(values, 50)),
            "p95": float(np.percentile(values, 95)),
            "p99": float(np.percentile(values, 99)),
        }


# Global singleton instance
metrics = MetricsCollector()


# Convenience functions for direct import
def increment(name: str, value: int = 1, tags: Optional[Dict[str, str]] = None) -> None:
    """Increment a counter."""
    metrics.increment(name, value, tags)


def gauge(name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
    """Set a gauge."""
    metrics.gauge(name, value, tags)


def histogram(name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
    """Record a histogram value."""
    metrics.histogram(name, value, tags)


def get_percentiles(name: str, percentiles: List[float] = None, tags: Optional[Dict[str, str]] = None) -> Dict[str, float]:
    """Get percentiles for a histogram."""
    return metrics.get_percentiles(name, percentiles, tags)
