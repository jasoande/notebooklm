"""
Circuit Breaker Pattern Implementation
Prevents cascading failures and provides fail-fast behavior
"""

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Any


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Failing, reject requests
    HALF_OPEN = "HALF_OPEN"  # Testing recovery


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is in OPEN state"""
    pass


class CircuitBreaker:
    """
    Circuit breaker pattern implementation
    Protects against cascading failures
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 120,
        success_threshold: int = 2,
        enabled: bool = True
    ):
        """
        Args:
            failure_threshold: Failures before opening circuit
            timeout: Seconds to wait before attempting recovery
            success_threshold: Successes needed to close from half-open
            enabled: Enable/disable circuit breaker
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold
        self.enabled = enabled

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_state_change = datetime.now()

        self.lock = asyncio.Lock()

        if enabled:
            logging.info(
                f"CircuitBreaker initialized: "
                f"failure_threshold={failure_threshold}, "
                f"timeout={timeout}s"
            )

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker

        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is OPEN
        """
        if not self.enabled:
            return await func(*args, **kwargs)

        async with self.lock:
            # Check if we can transition from OPEN to HALF_OPEN
            if self.state == CircuitState.OPEN:
                if datetime.now() - self.last_failure_time > timedelta(seconds=self.timeout):
                    logging.info("Circuit breaker transitioning to HALF_OPEN")
                    self._transition_to(CircuitState.HALF_OPEN)
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker is OPEN. "
                        f"Retry after {self.timeout}s timeout."
                    )

        # Execute function
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result

        except Exception as e:
            await self._on_failure()
            raise

    async def _on_success(self) -> None:
        """Handle successful execution"""
        async with self.lock:
            self.failure_count = 0

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    logging.info(
                        f"Circuit breaker closing after {self.success_count} "
                        f"successful attempts"
                    )
                    self._transition_to(CircuitState.CLOSED)
                    self.success_count = 0

    async def _on_failure(self) -> None:
        """Handle failed execution"""
        async with self.lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            if self.state == CircuitState.HALF_OPEN:
                logging.warning("Circuit breaker reopening after failure in HALF_OPEN state")
                self._transition_to(CircuitState.OPEN)
                self.success_count = 0

            elif self.state == CircuitState.CLOSED:
                if self.failure_count >= self.failure_threshold:
                    logging.error(
                        f"Circuit breaker opening after {self.failure_count} failures"
                    )
                    self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        """
        Transition to new state

        Args:
            new_state: Target state
        """
        old_state = self.state
        self.state = new_state
        self.last_state_change = datetime.now()

        if old_state != new_state:
            logging.info(f"Circuit breaker: {old_state.value} -> {new_state.value}")

    def get_state(self) -> str:
        """Get current circuit state"""
        return self.state.value

    def get_stats(self) -> dict:
        """Get circuit breaker statistics"""
        return {
            'state': self.state.value,
            'enabled': self.enabled,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'last_failure_time': (
                self.last_failure_time.isoformat()
                if self.last_failure_time else None
            ),
            'last_state_change': self.last_state_change.isoformat(),
            'seconds_since_last_failure': (
                (datetime.now() - self.last_failure_time).total_seconds()
                if self.last_failure_time else None
            )
        }

    async def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state"""
        async with self.lock:
            logging.info("Manually resetting circuit breaker to CLOSED")
            self._transition_to(CircuitState.CLOSED)
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None
