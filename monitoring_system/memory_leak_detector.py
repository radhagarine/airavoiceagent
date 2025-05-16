"""Memory leak detection module."""

import gc
import tracemalloc
import psutil
import weakref
from threading import Thread
from collections import defaultdict
from typing import Dict, Any, Optional

from prometheus_client import Gauge, Counter

# Create metrics specific to memory leak detection
memory_allocations = Gauge(
    'memory_allocations_current',
    'Current memory allocations by type',
    ['allocation_type']
)

memory_growth_rate = Gauge(
    'memory_growth_rate_mb_per_minute',
    'Rate of memory growth in MB per minute'
)

gc_collection_count = Counter(
    'garbage_collection_total',
    'Total garbage collections by generation',
    ['generation']
)

object_count_by_type = Gauge(
    'python_objects_total',
    'Total Python objects by type',
    ['object_type']
)

# Import logger from core
from .core import logger

class MemoryLeakDetector:
    """Detects memory leaks and tracks memory usage patterns."""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.baseline_memory = None
        self.memory_samples = []
        self.max_samples = 60  # Keep last 60 samples (30 minutes at 30s intervals)
        self.leak_threshold_mb = 50  # Alert if memory grows by 50MB consistently
        self.object_tracking = defaultdict(int)
        self.weak_refs = set()
        self.monitoring_thread = None
        
        if self.enabled:
            self._initialize()
    
    def _initialize(self):
        """Initialize memory leak detection."""
        tracemalloc.start(25)  # Keep top 25 stack frames
        self.baseline_memory = self._get_memory_usage()
        
        # Start memory monitoring thread
        self.monitoring_thread = Thread(target=self._monitor_memory, daemon=True)
        self.monitoring_thread.start()
        
        logger.info("Memory leak detection enabled")
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024  # Convert to MB
    
    def _monitor_memory(self):
        """Background thread to monitor memory usage."""
        import time
        
        while True:
            try:
                current_memory = self._get_memory_usage()
                
                # Record memory sample
                self.memory_samples.append(current_memory)
                if len(self.memory_samples) > self.max_samples:
                    self.memory_samples.pop(0)
                
                # Calculate growth rate
                if len(self.memory_samples) >= 2:
                    growth_rate = self._calculate_growth_rate()
                    memory_growth_rate.set(growth_rate)
                
                # Update memory metrics
                memory_allocations.labels(allocation_type='rss').set(current_memory)
                
                # Check for memory leaks
                if self._detect_leak():
                    self._log_memory_leak()
                
                # Track object counts
                self._track_object_counts()
                
                # Track garbage collection
                self._track_gc_stats()
                
                # Sleep for 30 seconds
                time.sleep(30)
                
            except Exception as e:
                logger.error("Error in memory monitoring", error=str(e))
                time.sleep(30)
    
    def _calculate_growth_rate(self) -> float:
        """Calculate memory growth rate in MB per minute."""
        if len(self.memory_samples) < 2:
            return 0.0
        
        # Calculate average growth over the last 10 samples (5 minutes)
        sample_count = min(10, len(self.memory_samples))
        recent_samples = self.memory_samples[-sample_count:]
        
        # Linear regression to find trend
        n = len(recent_samples)
        sum_x = sum(range(n))
        sum_y = sum(recent_samples)
        sum_xy = sum(i * recent_samples[i] for i in range(n))
        sum_x2 = sum(i * i for i in range(n))
        
        # Growth rate per sample (30 seconds) converted to per minute
        growth_per_sample = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        growth_per_minute = growth_per_sample * 2  # 30 seconds * 2 = 1 minute
        
        return growth_per_minute
    
    def _detect_leak(self) -> bool:
        """Detect if there's a memory leak."""
        if len(self.memory_samples) < 10:  # Need at least 5 minutes of data
            return False
        
        growth_rate = self._calculate_growth_rate()
        
        # Consider it a leak if memory is growing consistently
        return growth_rate > self.leak_threshold_mb / 10  # 5MB per minute threshold
    
    def _log_memory_leak(self):
        """Log details about detected memory leak."""
        current_memory = self._get_memory_usage()
        growth_rate = self._calculate_growth_rate()
        
        # Get tracemalloc snapshot
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')
        
        # Log the leak
        logger.error(
            "Memory leak detected",
            current_memory_mb=current_memory,
            growth_rate_mb_per_min=growth_rate,
            baseline_memory_mb=self.baseline_memory,
            memory_increase_mb=current_memory - self.baseline_memory
        )
        
        # Log top memory allocations
        logger.error("Top memory allocations:")
        for index, stat in enumerate(top_stats[:5]):
            logger.error(
                f"Memory allocation {index + 1}",
                size_mb=stat.size / 1024 / 1024,
                count=stat.count,
                traceback=str(stat.traceback)
            )
        
        # Update baseline after reporting leak
        self.baseline_memory = current_memory
    
    def _track_object_counts(self):
        """Track Python object counts by type."""
        # Force garbage collection
        gc.collect()
        
        # Count objects by type
        object_counts = defaultdict(int)
        for obj in gc.get_objects():
            obj_type = type(obj).__name__
            object_counts[obj_type] += 1
        
        # Update metrics for common object types
        important_types = ['dict', 'list', 'tuple', 'function', 'type', 'weakref']
        for obj_type in important_types:
            if obj_type in object_counts:
                object_count_by_type.labels(object_type=obj_type).set(object_counts[obj_type])
    
    def _track_gc_stats(self):
        """Track garbage collection statistics."""
        gc_stats = gc.get_stats()
        for i, stats in enumerate(gc_stats):
            collections = stats.get('collections', 0)
            # Only increment what's new since last check
            gc_collection_count.labels(generation=str(i)).inc(0)
    
    def track_object_creation(self, obj, identifier: str = None):
        """Track creation of specific objects that might leak."""
        if not self.enabled:
            return
        
        # Use weak reference to avoid preventing garbage collection
        try:
            weak_ref = weakref.ref(obj, lambda ref: self._object_destroyed(identifier))
            self.weak_refs.add(weak_ref)
            self.object_tracking[identifier or type(obj).__name__] += 1
        except TypeError:
            # Some objects don't support weak references
            pass
    
    def _object_destroyed(self, identifier: str):
        """Called when a tracked object is destroyed."""
        if identifier:
            self.object_tracking[identifier] = max(0, self.object_tracking[identifier] - 1)
    
    def get_memory_report(self) -> Dict[str, Any]:
        """Get comprehensive memory usage report."""
        if not tracemalloc.is_tracing():
            return {"error": "tracemalloc not enabled"}
        
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')
        
        return {
            "current_memory_mb": self._get_memory_usage(),
            "baseline_memory_mb": self.baseline_memory,
            "memory_growth_mb": self._get_memory_usage() - self.baseline_memory,
            "growth_rate_mb_per_min": self._calculate_growth_rate(),
            "top_allocations": [
                {
                    "size_mb": stat.size / 1024 / 1024,
                    "count": stat.count,
                    "filename": stat.traceback.format()[0] if stat.traceback else "unknown"
                }
                for stat in top_stats[:10]
            ],
            "tracked_objects": dict(self.object_tracking),
            "gc_stats": gc.get_stats()
        }
    
    def shutdown(self):
        """Shutdown memory leak detection."""
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        logger.info("Memory leak detection shutdown")