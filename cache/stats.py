
"""Cache statistics and metrics module."""

import time
from typing import Dict, Any, List
from collections import defaultdict

from monitoring_system import logger, metrics


class CacheStats:
    """Production cache statistics with detailed metrics."""
    
    def __init__(self):
        self.l1_hits = 0
        self.l1_misses = 0
        self.l2_hits = 0
        self.l2_misses = 0
        self.compute_hits = 0  # Times we had to compute values
        self.errors = 0
        self.circuit_breaker_trips = 0
        self.warming_operations = 0
        self.total_requests = 0
        self.compression_saves = 0
        self.start_time = time.time()
        
        # Performance tracking
        self.operation_times = defaultdict(list)
        self.error_types = defaultdict(int)
    
    def record_l1_hit(self):
        self.l1_hits += 1
        self.total_requests += 1
    
    def record_l1_miss(self):
        self.l1_misses += 1
    
    def record_l2_hit(self):
        self.l2_hits += 1
    
    def record_l2_miss(self):
        self.l2_misses += 1
    
    def record_compute(self):
        self.compute_hits += 1
    
    def record_error(self, error_type: str = "unknown"):
        self.errors += 1
        self.error_types[error_type] += 1
    
    def record_operation_time(self, operation: str, duration: float):
        self.operation_times[operation].append(duration)
        # Keep only last 100 measurements
        if len(self.operation_times[operation]) > 100:
            self.operation_times[operation].pop(0)
    
    def record_compression_save(self):
        self.compression_saves += 1
    
    def record_circuit_breaker_trip(self):
        self.circuit_breaker_trips += 1
    
    def record_warming_operation(self):
        self.warming_operations += 1
    
    @property
    def l1_hit_rate(self) -> float:
        total_l1 = self.l1_hits + self.l1_misses
        return self.l1_hits / total_l1 if total_l1 > 0 else 0.0
    
    @property
    def l2_hit_rate(self) -> float:
        total_l2 = self.l2_hits + self.l2_misses
        return self.l2_hits / total_l2 if total_l2 > 0 else 0.0
    
    @property
    def overall_hit_rate(self) -> float:
        total_hits = self.l1_hits + self.l2_hits
        return total_hits / self.total_requests if self.total_requests > 0 else 0.0
    
    @property
    def cache_miss_rate(self) -> float:
        cache_misses = self.l1_misses + self.l2_misses - self.l2_hits
        return cache_misses / self.total_requests if self.total_requests > 0 else 0.0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        uptime = time.time() - self.start_time
        
        # Calculate average operation times
        avg_times = {}
        for op, times in self.operation_times.items():
            avg_times[f"{op}_avg_ms"] = sum(times) / len(times) * 1000 if times else 0
        
        return {
            "performance": {
                "l1_hit_rate": round(self.l1_hit_rate * 100, 2),
                "l2_hit_rate": round(self.l2_hit_rate * 100, 2),
                "overall_hit_rate": round(self.overall_hit_rate * 100, 2),
                "cache_miss_rate": round(self.cache_miss_rate * 100, 2),
                **avg_times
            },
            "counts": {
                "l1_hits": self.l1_hits,
                "l1_misses": self.l1_misses,
                "l2_hits": self.l2_hits,
                "l2_misses": self.l2_misses,
                "compute_operations": self.compute_hits,
                "total_requests": self.total_requests
            },
            "reliability": {
                "errors": self.errors,
                "error_types": dict(self.error_types),
                "circuit_breaker_trips": self.circuit_breaker_trips,
                "error_rate": round(self.errors / self.total_requests * 100, 2) if self.total_requests > 0 else 0
            },
            "efficiency": {
                "compression_saves": self.compression_saves,
                "warming_operations": self.warming_operations,
                "uptime_seconds": round(uptime, 2)
            }
        }
    
    def update_prometheus_metrics(self, l1_cache_size: int):
        """Update Prometheus metrics with current cache statistics."""
        stats_data = self.get_stats()
        
        # Hit rates
        metrics.set_gauge('cache_hit_rate_percent',
                         stats_data['performance']['l1_hit_rate'],
                         labels={'cache_level': 'l1'})
        
        metrics.set_gauge('cache_hit_rate_percent',
                         stats_data['performance']['l2_hit_rate'],
                         labels={'cache_level': 'l2'})
        
        metrics.set_gauge('cache_hit_rate_percent',
                         stats_data['performance']['overall_hit_rate'],
                         labels={'cache_level': 'overall'})
        
        # Cache sizes
        metrics.set_gauge('cache_size_items',
                         l1_cache_size,
                         labels={'cache_level': 'l1'})
        
        # Error metrics
        metrics.set_gauge('cache_error_rate_percent',
                         stats_data['reliability']['error_rate'],
                         labels={'cache_type': 'overall'})
        
        # Operation counts
        metrics.increment_counter('cache_operations_total',
                                 labels={'operation': 'hit', 'level': 'l1'},
                                 value=0)  # We track incrementally
        
        # Compression effectiveness
        if stats_data['efficiency']['compression_saves'] > 0:
            metrics.increment_counter('cache_compression_saves_total',
                                     value=0)  # Track incrementally