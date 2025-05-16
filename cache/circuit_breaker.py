
"""Circuit breaker implementation for cache resilience."""

import time
from contextlib import asynccontextmanager
from typing import Literal

from monitoring_system import logger


class CircuitBreaker:
    """Circuit breaker for Redis operations with monitoring."""
    
    def __init__(self, threshold: int = 5, timeout: int = 30, name: str = "cache"):
        self.threshold = threshold
        self.timeout = timeout
        self.name = name
        self.failure_count = 0
        self.last_failure_time = 0
        self.state: Literal["CLOSED", "OPEN", "HALF_OPEN"] = "CLOSED"
        self._last_success_time = time.time()
    
    def is_open(self) -> bool:
        """Check if circuit breaker is open."""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout:
                logger.info("Circuit breaker transitioning to HALF_OPEN", 
                          name=self.name)
                self.state = "HALF_OPEN"
                return False
            return True
        return False
    
    def record_success(self):
        """Record successful operation."""
        previous_state = self.state
        self.failure_count = 0
        self._last_success_time = time.time()
        
        if self.state == "HALF_OPEN":
            logger.info("Circuit breaker recovered, transitioning to CLOSED", 
                       name=self.name)
            self.state = "CLOSED"
        elif previous_state == "OPEN":
            # This shouldn't happen, but handle it gracefully
            logger.warning("Circuit breaker had success while OPEN", 
                         name=self.name)
            self.state = "CLOSED"
    
    def record_failure(self):
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        logger.debug("Circuit breaker recorded failure", 
                    name=self.name,
                    failure_count=self.failure_count,
                    threshold=self.threshold)
        
        if self.failure_count >= self.threshold:
            logger.error("Circuit breaker tripped", 
                        name=self.name,
                        failure_count=self.failure_count,
                        threshold=self.threshold)
            self.state = "OPEN"
    
    @asynccontextmanager
    async def protect(self):
        """Context manager for protected operations."""
        if self.is_open():
            logger.warning("Circuit breaker is OPEN, rejecting operation", 
                         name=self.name)
            raise CircuitBreakerOpenError(f"Circuit breaker {self.name} is OPEN")
        
        try:
            yield
            self.record_success()
        except Exception as e:
            self.record_failure()
            logger.error("Operation failed through circuit breaker", 
                        name=self.name,
                        error=str(e))
            raise
    
    def get_status(self) -> dict:
        """Get circuit breaker status for monitoring."""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "threshold": self.threshold,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self._last_success_time,
            "time_since_last_failure": time.time() - self.last_failure_time if self.last_failure_time > 0 else None
        }


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""
    pass