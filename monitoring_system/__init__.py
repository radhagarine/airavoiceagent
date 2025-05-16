"""Monitoring system package with memory leak detection."""

# Import all the existing monitoring functionality
from .core import (
    logger,
    log_context,
    monitor_performance,
    track_latency,
    metrics,
    add_metrics_endpoint,
    initialize_monitoring,
    update_system_metrics
)

# Import memory leak detection
from .memory_leak_detector import MemoryLeakDetector

# Global memory leak detector instance
_memory_leak_detector = None

def initialize_memory_leak_detection(enabled: bool = True):
    """Initialize memory leak detection."""
    global _memory_leak_detector
    if _memory_leak_detector is None:
        _memory_leak_detector = MemoryLeakDetector(enabled)
    return _memory_leak_detector

def track_object_creation(obj, identifier: str = None):
    """Track object creation for leak detection."""
    if _memory_leak_detector:
        _memory_leak_detector.track_object_creation(obj, identifier)

def get_memory_report() -> dict:
    """Get detailed memory usage report."""
    if _memory_leak_detector:
        return _memory_leak_detector.get_memory_report()
    return {"error": "Memory leak detection not initialized"}

async def shutdown_monitoring():
    """Shutdown all monitoring systems."""
    if _memory_leak_detector:
        _memory_leak_detector.shutdown()
    await metrics.shutdown()

__all__ = [
    'logger',
    'log_context', 
    'monitor_performance',
    'track_latency',
    'metrics',
    'add_metrics_endpoint',
    'initialize_monitoring',
    'update_system_metrics',
    'initialize_memory_leak_detection',
    'track_object_creation',
    'get_memory_report',
    'shutdown_monitoring'
]