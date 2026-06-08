"""
Synchronous Token Bucket Rate Limiter
Prevents API quota exhaustion without blocking worker threads unnecessarily
"""

import logging
import random
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Dict


class SyncRateLimiter:
    """
    Thread-safe token bucket rate limiter for synchronous operations.
    Ensures we don't exceed API quota limits while maximizing throughput.
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
        self.last_update = time.time()
        self.request_history = deque(maxlen=1000)
        self.lock = threading.Lock()

        logging.info(f"SyncRateLimiter initialized: {requests_per_minute} req/min, burst={burst}")

    def acquire(self) -> None:
        """
        Acquire a token, waiting if necessary.
        This should be called before each API request.
        Thread-safe and blocks until a token is available.
        """
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update

            # Refill tokens based on elapsed time
            tokens_to_add = elapsed * (self.rate / 60.0)
            self.tokens = min(self.burst, self.tokens + tokens_to_add)
            self.last_update = now

            # If not enough tokens, calculate wait time
            if self.tokens < 1.0:
                wait_time = (1.0 - self.tokens) * (60.0 / self.rate)
                logging.debug(f"Rate limit: waiting {wait_time:.2f}s for token refill")

                # Release lock during sleep so other threads can check
                self.lock.release()
                time.sleep(wait_time)
                self.lock.acquire()

                # After waiting, we should have enough tokens
                # Re-check in case another thread took our token
                now = time.time()
                elapsed = now - self.last_update
                tokens_to_add = elapsed * (self.rate / 60.0)
                self.tokens = min(self.burst, self.tokens + tokens_to_add)
                self.last_update = now

            # Consume one token
            self.tokens -= 1.0
            self.request_history.append(now)

    def try_acquire(self) -> bool:
        """
        Try to acquire a token without waiting.
        Returns True if token was acquired, False otherwise.
        """
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update

            # Refill tokens based on elapsed time
            tokens_to_add = elapsed * (self.rate / 60.0)
            self.tokens = min(self.burst, self.tokens + tokens_to_add)
            self.last_update = now

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                self.request_history.append(now)
                return True

            return False

    def get_stats(self) -> Dict:
        """Get current rate limiter statistics"""
        with self.lock:
            now = time.time()
            one_min_ago = now - 60.0
            recent_requests = sum(1 for t in self.request_history if t > one_min_ago)

            return {
                'tokens_available': self.tokens,
                'requests_last_minute': recent_requests,
                'rate_limit': self.rate,
                'utilization_percent': (recent_requests / self.rate) * 100 if self.rate > 0 else 0,
                'burst_capacity': self.burst
            }

    def reset(self) -> None:
        """Reset rate limiter to initial state"""
        with self.lock:
            self.tokens = float(self.burst)
            self.last_update = time.time()
            self.request_history.clear()
            logging.info("Rate limiter reset to initial state")


class ExponentialBackoff:
    """
    Exponential backoff with jitter for intelligent retries.
    Works with synchronous operations.
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

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for given attempt number.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Exponential backoff
        delay = min(
            self.max_delay,
            self.base_delay * (self.backoff_multiplier ** attempt)
        )

        # Add jitter
        jitter = random.uniform(0, delay * self.jitter_percent)
        return delay + jitter

    def get_stats(self) -> Dict:
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
    Detect if API response indicates rate limiting.

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
        '503',
        'rate_limit_exceeded',
        'quota_exceeded',
        'exhausted',
        'ratelimiterror',
        'user_displayable_error'
    ]

    return any(indicator in combined for indicator in rate_limit_indicators)
