"""
Account Planning Engine - Shared Library
Production-ready utilities for NotebookLM automation
"""

from .rate_limiter import RateLimiter, ExponentialBackoff, RateLimitError
from .session_manager import NotebookLMSession
from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from .checkpoint import CheckpointManager

# Optional: config_loader (requires PyYAML)
try:
    from .config_loader import ConfigLoader
except ImportError:
    ConfigLoader = None

from .sync_rate_limiter import SyncRateLimiter, ExponentialBackoff as SyncExponentialBackoff, detect_rate_limit
from .client_session import ClientSession, SessionPool
from .async_url_validator import (
    validate_urls_parallel,
    validate_and_filter_urls_sync,
    get_cache_stats,
    clear_cache
)

__all__ = [
    # Async rate limiting
    'RateLimiter',
    'ExponentialBackoff',
    'RateLimitError',

    # Sync rate limiting (NEW - for deep mode)
    'SyncRateLimiter',
    'SyncExponentialBackoff',
    'detect_rate_limit',

    # Async session management
    'NotebookLMSession',

    # Sync session management (NEW - for deep mode)
    'ClientSession',
    'SessionPool',

    # Circuit breaker
    'CircuitBreaker',
    'CircuitBreakerOpenError',

    # Checkpoint management
    'CheckpointManager',

    # Config loading
    'ConfigLoader',

    # URL validation (NEW - for deep mode)
    'validate_urls_parallel',
    'validate_and_filter_urls_sync',
    'get_cache_stats',
    'clear_cache',
]
