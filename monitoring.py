import os
import time
import functools
import logging
import asyncio
from typing import Callable, Any, Optional
from contextlib import contextmanager

import structlog
import psutil
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST, push_to_gateway
from fastapi.responses import Response

# Production environment variables
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

# Configuration
METRICS_ENABLED = os.getenv("METRICS_ENABLED", "false").lower() == "true"
STRUCTURED_LOGGING_ENABLED = os.getenv("STRUCTURED_LOGGING_ENABLED", "false").lower() == "true"
PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL")  # Optional push gateway

# Configure logging
if STRUCTURED_LOGGING_ENABLED:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logger = structlog.get_logger()
else:
    logging.basicConfig(level=logging.INFO)
    
    class SimpleLogger:
        def __init__(self):
            self._logger = logging.getLogger()
        
        def info(self, message, **kwargs):
            self._logger.info(f"{message} {kwargs if kwargs else ''}")
        
        def warning(self, message, **kwargs):
            self._logger.warning(f"{message} {kwargs if kwargs else ''}")
        
        def error(self, message, **kwargs):
            self._logger.error(f"{message} {kwargs if kwargs else ''}")
        
        def debug(self, message, **kwargs):
            self._logger.debug(f"{message} {kwargs if kwargs else ''}")
        
        def bind(self, **kwargs):
            return self
    
    logger = SimpleLogger()

# Metrics setup
registry = CollectorRegistry()

# Define production metrics
operation_duration = Histogram(
    'operation_duration_seconds',
    'Time spent on operation',
    ['operation', 'status'],
    registry=registry
)

operation_count = Counter(
    'operation_total',
    'Total number of operations',
    ['operation', 'status'],
    registry=registry
)

business_lookup_count = Counter(
    'business_lookup_total',
    'Total business lookups',
    ['status'],
    registry=registry
)

# Production-specific metrics
active_calls = Gauge(
    'active_calls_current',
    'Current number of active calls',
    registry=registry
)

error_count = Counter(
    'errors_total',
    'Total errors by type',
    ['error_type', 'operation'],
    registry=registry
)

response_time_p99 = Histogram(
    'response_time_seconds',
    'Response time percentiles',
    ['endpoint'],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=registry
)

system_memory = Gauge(
    'memory_usage_bytes',
    'Memory usage in bytes',
    registry=registry
)

system_cpu = Gauge(
    'cpu_usage_percent',
    'CPU usage percentage',
    registry=registry
)

# Uptime tracking
app_start_time = Gauge(
    'app_start_time_seconds',
    'Application start time',
    registry=registry
)
app_start_time.set(time.time())

class NoOpMetrics:
    """No-op metrics for when monitoring is disabled."""
    def increment_counter(self, name, labels=None, value=1):
        pass
    
    def observe_histogram(self, name, value, labels=None):
        pass
    
    def set_gauge(self, name, value, labels=None):
        pass
    
    def get_metrics_text(self):
        return ""
    
    async def shutdown(self):
        """Push final metrics to gateway if configured."""
        if self.enabled and PUSHGATEWAY_URL:
            try:
                from prometheus_client import push_to_gateway
                push_to_gateway(PUSHGATEWAY_URL, job='voice-bot', registry=registry)
                logger.info("Final metrics pushed to gateway")
            except Exception as e:
                logger.error("Failed to push final metrics", error=str(e))
    
    def push_metrics(self):
        """Push metrics to pushgateway."""
        if self.enabled and PUSHGATEWAY_URL:
            try:
                from prometheus_client import push_to_gateway
                push_to_gateway(PUSHGATEWAY_URL, job='voice-bot', registry=registry)
                logger.debug("Metrics pushed to gateway")
            except Exception as e:
                logger.error("Failed to push metrics", error=str(e))

class MetricsCollector:
    """Simple metrics collector."""
    def __init__(self):
        self.enabled = METRICS_ENABLED
    
    def increment_counter(self, name, labels=None, value=1):
        if not self.enabled:
            return
        
        if name == 'business_lookup_total':
            business_lookup_count.labels(**labels).inc(value)
        elif name == 'operation_total':
            operation_count.labels(**labels).inc(value)
        elif name == 'errors_total':
            error_count.labels(**labels).inc(value)
        elif name == 'active_calls_increment':
            active_calls.inc(value)
    
    def observe_histogram(self, name, value, labels=None):
        if not self.enabled:
            return
        
        if name == 'operation_duration_seconds':
            operation_duration.labels(**labels).observe(value)
        elif name == 'response_time_seconds':
            response_time_p99.labels(**labels).observe(value)
    
    def set_gauge(self, name, value, labels=None):
        if not self.enabled:
            return
        
        if name == 'memory_usage_bytes':
            system_memory.set(value)
        elif name == 'cpu_usage_percent':
            system_cpu.set(value)
        elif name == 'active_calls_current':
            active_calls.set(value)
    
    def get_metrics_text(self):
        if not self.enabled:
            return ""
        return generate_latest(registry).decode('utf-8')
    
    async def shutdown(self):
        pass

# Global metrics instance
metrics = MetricsCollector()

@contextmanager
def log_context(**kwargs):
    """Context manager for structured logging."""
    if STRUCTURED_LOGGING_ENABLED:
        # For structlog, bind the context
        bound_logger = logger.bind(**kwargs)
        try:
            yield bound_logger
        finally:
            pass
    else:
        # For simple logger, just yield the logger as-is
        yield logger

def monitor_performance(operation_name: str, business_type: str = "unknown"):
    """Decorator to monitor function performance."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status = "success"
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start_time
                
                # Record metrics
                metrics.observe_histogram(
                    'operation_duration_seconds',
                    duration,
                    labels={'operation': operation_name, 'status': status}
                )
                metrics.increment_counter(
                    'operation_total',
                    labels={'operation': operation_name, 'status': status}
                )
                
                # Log
                logger.info(
                    f"Operation {operation_name} completed",
                    operation=operation_name,
                    duration=duration,
                    status=status
                )
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status = "success"
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start_time
                
                # Record metrics
                metrics.observe_histogram(
                    'operation_duration_seconds',
                    duration,
                    labels={'operation': operation_name, 'status': status}
                )
                metrics.increment_counter(
                    'operation_total',
                    labels={'operation': operation_name, 'status': status}
                )
                
                # Log
                logger.info(
                    f"Operation {operation_name} completed",
                    operation=operation_name,
                    duration=duration,
                    status=status
                )
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator

def track_latency(operation_name: str):
    """Track latency (alias for monitor_performance)."""
    return monitor_performance(operation_name)

def add_metrics_endpoint(app):
    """Add metrics endpoint to FastAPI app."""
    @app.get("/metrics")
    async def get_metrics():
        if not METRICS_ENABLED:
            return {"error": "Metrics not enabled"}
        return Response(content=metrics.get_metrics_text(), media_type=CONTENT_TYPE_LATEST)

def initialize_monitoring():
    """Initialize monitoring."""
    logger.info("Monitoring initialized", 
               metrics_enabled=METRICS_ENABLED,
               structured_logging=STRUCTURED_LOGGING_ENABLED)

# Update system metrics periodically
async def update_system_metrics():
    """Update system metrics."""
    if METRICS_ENABLED:
        memory = psutil.virtual_memory()
        metrics.set_gauge('memory_usage_bytes', memory.used)
        metrics.set_gauge('cpu_usage_percent', psutil.cpu_percent())

# Export everything
__all__ = [
    'logger',
    'log_context', 
    'monitor_performance',
    'track_latency',
    'metrics',
    'add_metrics_endpoint',
    'initialize_monitoring',
    'update_system_metrics'
]