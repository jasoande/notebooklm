"""
Async URL Validation with Connection Pooling and Caching
High-performance URL validation for parallel processing
"""

import asyncio
import logging
import threading
from typing import List, Tuple, Dict, Optional
from urllib.parse import urlparse


try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logging.warning("aiohttp not available - falling back to synchronous validation")


# Global URL validation cache (shared across clients)
_url_validation_cache: Dict[str, Tuple[bool, str]] = {}
_cache_lock = threading.Lock()


async def validate_url_async(
    url: str,
    session: 'aiohttp.ClientSession',
    timeout: int = 5
) -> Tuple[bool, str]:
    """
    Validate URL asynchronously with connection pooling.

    Args:
        url: URL to validate
        session: Shared aiohttp session (for connection pooling)
        timeout: Request timeout in seconds

    Returns:
        Tuple of (is_valid, reason)
    """
    # Quick pattern check for known problematic URLs
    blocked_patterns = [
        'cloudflare.com/cdn-cgi',
        'captcha',
        'login.',
        'signin.',
        'auth.',
        '/404',
        'error',
        'page-not-found',
        'example.com',
        'localhost',
        '127.0.0.1',
        'tracxn.com',
        'pitchbook.com',
        'fintechforum.de',
    ]

    url_lower = url.lower()
    for pattern in blocked_patterns:
        if pattern in url_lower:
            return False, f"Blocked pattern: {pattern}"

    # Check minimum URL length
    if len(url) < 25:
        return False, "URL too short (likely truncated)"

    # Parse URL structure
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False, "Invalid URL structure"

        if parsed.scheme not in ['http', 'https']:
            return False, f"Unsupported scheme: {parsed.scheme}"
    except Exception as e:
        return False, f"Parse error: {str(e)[:50]}"

    # HTTP HEAD request to check accessibility
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; ProjectAPE/1.0; +https://redhat.com)'
    }

    try:
        async with session.head(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True,
            headers=headers
        ) as response:
            if response.status == 200:
                return True, "OK"
            elif response.status == 403:
                return False, "Forbidden (likely requires authentication)"
            elif response.status == 401:
                return False, "Requires authentication"
            elif response.status == 404:
                return False, "404 Not Found"
            elif response.status == 410:
                return False, "410 Gone (permanently deleted)"
            elif response.status >= 500:
                return False, f"Server error: HTTP {response.status}"
            else:
                return False, f"HTTP {response.status}"

    except asyncio.TimeoutError:
        return False, "Request timeout"
    except aiohttp.TooManyRedirects:
        return False, "Too many redirects"
    except aiohttp.ClientError as e:
        return False, f"Client error: {str(e)[:50]}"
    except Exception as e:
        return False, f"Validation error: {str(e)[:50]}"


async def validate_urls_parallel(
    urls: List[str],
    client_token: str = "Unknown",
    timeout: int = 5,
    max_concurrent: int = 10
) -> List[str]:
    """
    Validate multiple URLs in parallel with connection pooling.

    Args:
        urls: List of URLs to validate
        client_token: Client identifier for logging
        timeout: Request timeout per URL
        max_concurrent: Maximum concurrent requests

    Returns:
        List of valid URLs
    """
    if not AIOHTTP_AVAILABLE:
        logging.error(f"[{client_token}] aiohttp not available - cannot validate URLs")
        return urls  # Return all URLs unvalidated

    if not urls:
        return []

    # Check cache first
    cached_results = []
    uncached_urls = []

    with _cache_lock:
        for url in urls:
            if url in _url_validation_cache:
                is_valid, reason = _url_validation_cache[url]
                if is_valid:
                    cached_results.append(url)
                logging.debug(f"[{client_token}] Cache hit for {url}: {reason}")
            else:
                uncached_urls.append(url)

    logging.info(
        f"[{client_token}] URL validation: {len(cached_results)} cached, "
        f"{len(uncached_urls)} to validate"
    )

    # Validate uncached URLs in parallel
    valid_urls = cached_results.copy()

    if uncached_urls:
        # Connection pooling: reuse TCP connections
        connector = aiohttp.TCPConnector(
            limit=max_concurrent,
            limit_per_host=2,
            ttl_dns_cache=300
        )

        async with aiohttp.ClientSession(connector=connector) as session:
            # Create validation tasks
            tasks = [
                validate_url_async(url, session, timeout)
                for url in uncached_urls
            ]

            # Execute all validations in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for url, result in zip(uncached_urls, results):
                if isinstance(result, Exception):
                    logging.error(f"[{client_token}] Exception validating {url}: {result}")
                    is_valid, reason = False, str(result)[:50]
                else:
                    is_valid, reason = result

                # Cache result
                with _cache_lock:
                    _url_validation_cache[url] = (is_valid, reason)

                # Add to valid list
                if is_valid:
                    valid_urls.append(url)
                    logging.debug(f"[{client_token}] Valid URL: {url}")
                else:
                    logging.info(f"[{client_token}] Invalid URL: {url} - {reason}")

    logging.info(
        f"[{client_token}] Validated {len(valid_urls)}/{len(urls)} URLs "
        f"({len(cached_results)} from cache)"
    )

    return valid_urls


def validate_and_filter_urls_sync(
    urls: List[str],
    client_token: str = "Unknown",
    timeout: int = 5,
    max_concurrent: int = 10
) -> List[str]:
    """
    Synchronous wrapper for async URL validation.
    Creates event loop, validates URLs, closes loop.

    Args:
        urls: List of URLs to validate
        client_token: Client identifier for logging
        timeout: Request timeout per URL
        max_concurrent: Maximum concurrent requests

    Returns:
        List of valid URLs
    """
    if not AIOHTTP_AVAILABLE:
        logging.warning(f"[{client_token}] aiohttp not available - returning all URLs unvalidated")
        return urls

    # Create new event loop for this validation batch
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        valid_urls = loop.run_until_complete(
            validate_urls_parallel(urls, client_token, timeout, max_concurrent)
        )
        return valid_urls
    finally:
        loop.close()


def get_cache_stats() -> Dict:
    """
    Get URL validation cache statistics.

    Returns:
        Dict with cache stats
    """
    with _cache_lock:
        total_urls = len(_url_validation_cache)
        valid_count = sum(1 for is_valid, _ in _url_validation_cache.values() if is_valid)
        invalid_count = total_urls - valid_count

        return {
            'total_cached_urls': total_urls,
            'valid_urls_cached': valid_count,
            'invalid_urls_cached': invalid_count,
            'cache_hit_rate_potential': f"{(total_urls / max(1, total_urls)) * 100:.1f}%"
        }


def clear_cache() -> None:
    """Clear URL validation cache"""
    with _cache_lock:
        count = len(_url_validation_cache)
        _url_validation_cache.clear()
        logging.info(f"URL validation cache cleared ({count} entries removed)")


# Fallback synchronous validation (if aiohttp not available)
def validate_url_sync_fallback(url: str, timeout: int = 5) -> Tuple[bool, str]:
    """
    Fallback synchronous URL validation using requests library.
    Used when aiohttp is not available.

    Args:
        url: URL to validate
        timeout: Request timeout

    Returns:
        Tuple of (is_valid, reason)
    """
    try:
        import requests

        # Quick checks
        if len(url) < 25:
            return False, "URL too short"

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False, "Invalid URL structure"

        # HTTP HEAD request
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; ProjectAPE/1.0)'}
        response = requests.head(url, timeout=timeout, allow_redirects=True, headers=headers)

        if response.status_code == 200:
            return True, "OK"
        elif response.status_code == 403:
            return False, "Forbidden"
        elif response.status_code == 404:
            return False, "404 Not Found"
        else:
            return False, f"HTTP {response.status_code}"

    except requests.Timeout:
        return False, "Request timeout"
    except Exception as e:
        return False, str(e)[:50]
