"""
Rate Limiting and Exponential Backoff Implementation
Prevents API quota exhaustion and handles retries intelligently
"""

import asyncio
import logging
import random
from datetime import datetime, timedelta
from collections import deque
from typing import Callable, Any, Optional


class RateLimitError(Exception):
    """Raised when rate limit is detected in API response"""
    pass


class RateLimiter:
    """
    Token bucket rate limiter with sliding window
    Ensures we don't exceed API quota limits
    """

    def __init__(self, requests_per_minute: int = 20, burst: int = 3):
        """
        Args:
            requests_per_minute: Maximum requests allowed per minute
            burst: Maximum burst size (tokens available immediately)
        """
        self.rate = requests_per_minute
        self.burst = burst
        self.tokens = float(burst)
        self.last_update = datetime.now()
        self.request_history = deque(maxlen=1000)
        self.lock = asyncio.Lock()

        logging.info(f"RateLimiter initialized: {requests_per_minute} req/min, burst={burst}")

    async def acquire(self) -> None:
        """
        Acquire a token, waiting if necessary
        This should be called before each API request
        """
        async with self.lock:
            now = datetime.now()
            elapsed = (now - self.last_update).total_seconds()

            # Refill tokens based on elapsed time
            self.tokens = min(
                self.burst,
                self.tokens + elapsed * (self.rate / 60.0)
            )
            self.last_update = now

            # If not enough tokens, wait for refill
            if self.tokens < 1.0:
                wait_time = (1.0 - self.tokens) * (60.0 / self.rate)
                logging.debug(f"Rate limit: waiting {wait_time:.2f}s for token refill")
                await asyncio.sleep(wait_time)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0

            self.request_history.append(now)

    def get_stats(self) -> dict:
        """Get current rate limiter statistics"""
        now = datetime.now()
        one_min_ago = now - timedelta(minutes=1)
        recent_requests = sum(1 for t in self.request_history if t > one_min_ago)

        return {
            'tokens_available': self.tokens,
            'requests_last_minute': recent_requests,
            'rate_limit': self.rate,
            'utilization_percent': (recent_requests / self.rate) * 100
        }


class ExponentialBackoff:
    """
    Exponential backoff with jitter for intelligent retries
    Implements industry-standard retry pattern
    """

    def __init__(
        self,
        base_delay: float = 2.0,
        max_delay: float = 300.0,
        max_retries: int = 10,
        backoff_multiplier: float = 2.0,
        jitter_percent: float = 0.1
    ):
        """
        Args:
            base_delay: Initial delay in seconds
            max_delay: Maximum delay cap in seconds
            max_retries: Maximum retry attempts
            backoff_multiplier: Multiplier for exponential growth
            jitter_percent: Random jitter as percentage (0.0-1.0)
        """
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.backoff_multiplier = backoff_multiplier
        self.jitter_percent = jitter_percent

        self.attempt_count = 0
        self.success_count = 0
        self.failure_count = 0

    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with exponential backoff retry logic

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from successful function execution

        Raises:
            Last exception if all retries exhausted
        """
        last_exception = None

        for attempt in range(self.max_retries):
            self.attempt_count += 1

            try:
                result = await func(*args, **kwargs)
                self.success_count += 1

                # Reset on success
                if attempt > 0:
                    logging.info(f"Retry successful after {attempt} attempts")

                return result

            except RateLimitError as e:
                last_exception = e
                self.failure_count += 1

                if attempt == self.max_retries - 1:
                    logging.error(f"Rate limit retry exhausted after {self.max_retries} attempts")
                    raise

                # Calculate exponential backoff with jitter
                delay = min(
                    self.max_delay,
                    self.base_delay * (self.backoff_multiplier ** attempt)
                )
                jitter = random.uniform(0, delay * self.jitter_percent)
                wait_time = delay + jitter

                logging.warning(
                    f"Rate limited (attempt {attempt + 1}/{self.max_retries}), "
                    f"waiting {wait_time:.1f}s before retry"
                )
                await asyncio.sleep(wait_time)

            except Exception as e:
                last_exception = e
                self.failure_count += 1

                if attempt == self.max_retries - 1:
                    logging.error(f"Retry exhausted after {self.max_retries} attempts: {e}")
                    raise

                # Shorter delay for non-rate-limit errors
                delay = min(self.max_delay, self.base_delay * (1.5 ** attempt))
                jitter = random.uniform(0, delay * self.jitter_percent)
                wait_time = delay + jitter

                logging.warning(
                    f"Error on attempt {attempt + 1}/{self.max_retries}: {e}, "
                    f"retrying in {wait_time:.1f}s"
                )
                await asyncio.sleep(wait_time)

        # Should not reach here, but just in case
        if last_exception:
            raise last_exception

    def get_stats(self) -> dict:
        """Get retry statistics"""
        return {
            'total_attempts': self.attempt_count,
            'successes': self.success_count,
            'failures': self.failure_count,
            'success_rate': (
                self.success_count / self.attempt_count * 100
                if self.attempt_count > 0 else 0
            )
        }


def detect_rate_limit(stdout: str, stderr: str) -> bool:
    """
    Detect if API response indicates rate limiting

    Args:
        stdout: Standard output from subprocess
        stderr: Standard error from subprocess

    Returns:
        True if rate limit detected
    """
    combined = (stdout + stderr).lower()

    rate_limit_indicators = [
        'quota exceeded',
        'rate limit',
        'too many requests',
        'throttled',
        '429',
        'rate_limit_exceeded',
        'quota_exceeded',
        'exhausted'
    ]

    return any(indicator in combined for indicator in rate_limit_indicators)
