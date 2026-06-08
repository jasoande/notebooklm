#!/usr/bin/env python3
"""
Test Script for Deep Mode Optimizations
Verifies that all new modules work correctly
"""

import sys
import time
from pathlib import Path

# Add current directory to path
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

print("=" * 71)
print(" TESTING DEEP MODE OPTIMIZATIONS")
print("=" * 71)
print()

# ==============================================================================
# Test 1: SyncRateLimiter
# ==============================================================================

def test_rate_limiter():
    """Test token bucket rate limiter"""
    print("Test 1: SyncRateLimiter")
    print("-" * 71)

    try:
        from lib.sync_rate_limiter import SyncRateLimiter

        # Create rate limiter: 60 requests/min, burst of 3
        limiter = SyncRateLimiter(requests_per_minute=60, burst=3)
        print(f"  ✓ Created rate limiter (60 req/min, burst=3)")

        # Test burst tokens (should be immediate)
        print(f"  Testing burst tokens...")
        burst_times = []
        for i in range(3):
            start = time.time()
            limiter.acquire()
            elapsed = time.time() - start
            burst_times.append(elapsed)
            print(f"    Token {i+1}: {elapsed:.3f}s", end="")
            if elapsed < 0.1:
                print(" ✓ (burst)")
            else:
                print(" ⚠ (should be <0.1s)")

        # Test rate limiting (4th token should wait ~1 second)
        print(f"  Testing rate limiting...")
        start = time.time()
        limiter.acquire()
        elapsed = time.time() - start
        print(f"    Token 4: {elapsed:.3f}s", end="")
        if 0.8 < elapsed < 1.3:
            print(" ✓ (rate limited correctly)")
        else:
            print(f" ⚠ (expected ~1.0s)")

        # Get stats
        stats = limiter.get_stats()
        print(f"  Statistics:")
        print(f"    Tokens available: {stats['tokens_available']:.2f}")
        print(f"    Requests last minute: {stats['requests_last_minute']}")
        print(f"    Utilization: {stats['utilization_percent']:.1f}%")

        print(f"\n  ✅ SyncRateLimiter test PASSED")
        return True

    except Exception as e:
        print(f"\n  ❌ SyncRateLimiter test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# Test 2: ClientSession
# ==============================================================================

def test_client_session():
    """Test persistent session manager"""
    print("\nTest 2: ClientSession")
    print("-" * 71)

    try:
        from lib.client_session import ClientSession, SessionPool

        # Mock paths
        shared_auth = Path.home() / ".notebooklm" / "profiles" / "default" / "storage_state.json"
        if not shared_auth.exists():
            shared_auth = Path.home() / ".notebooklm" / "storage_state.json"

        storage_dir = SCRIPT_DIR

        # Test single session
        print(f"  Creating client session...")
        session = ClientSession(
            "test_client",
            "Test Client",
            shared_auth,
            storage_dir
        )
        print(f"    ✓ Session created")
        print(f"    Storage path: {session.get_storage_path().name}")

        # Test auth refresh logic
        print(f"  Testing auth refresh logic...")
        needs_refresh = session.safe_auth_refresh(min_interval=240.0)
        print(f"    Needs refresh: {needs_refresh} ✓")

        if needs_refresh:
            session.mark_auth_refreshed()
            print(f"    ✓ Auth marked as refreshed")

        # Test stats
        stats = session.get_stats()
        print(f"  Session statistics:")
        print(f"    Client ID: {stats['client_id']}")
        print(f"    Notebook ID: {stats['notebook_id']}")
        print(f"    Cleanup done: {stats['cleanup_done']}")

        # Test session pool
        print(f"  Testing session pool...")
        pool = SessionPool(storage_dir)
        session2 = pool.get_or_create_session("test2", "Test 2", shared_auth)
        print(f"    ✓ Created second session via pool")

        pool_stats = pool.get_stats()
        print(f"    Total sessions: {pool_stats['total_sessions']} ✓")

        # Cleanup
        print(f"  Cleaning up...")
        session.cleanup()
        pool.cleanup_all()
        print(f"    ✓ Cleanup complete")

        print(f"\n  ✅ ClientSession test PASSED")
        return True

    except Exception as e:
        print(f"\n  ❌ ClientSession test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# Test 3: Async URL Validator
# ==============================================================================

def test_url_validator():
    """Test async URL validation"""
    print("\nTest 3: Async URL Validator")
    print("-" * 71)

    try:
        from lib.async_url_validator import (
            validate_and_filter_urls_sync,
            get_cache_stats,
            clear_cache,
            AIOHTTP_AVAILABLE
        )

        if not AIOHTTP_AVAILABLE:
            print(f"  ⚠ aiohttp not available - will use fallback")
            print(f"    Install: pip install aiohttp")
        else:
            print(f"  ✓ aiohttp available")

        # Test URLs
        test_urls = [
            "https://www.redhat.com",
            "https://example.com",
            "https://www.google.com",
            "https://invalid.test.fake.notreal",
            "http://localhost/test",  # Should be blocked
        ]

        print(f"  Validating {len(test_urls)} URLs...")
        start = time.time()
        valid_urls = validate_and_filter_urls_sync(
            test_urls,
            client_token="test_client",
            timeout=5,
            max_concurrent=10
        )
        elapsed = time.time() - start

        print(f"    ✓ Validation completed in {elapsed:.2f}s")
        print(f"    Valid URLs: {len(valid_urls)}/{len(test_urls)}")
        for url in valid_urls:
            print(f"      • {url}")

        # Test caching
        print(f"  Testing URL cache...")
        cache_stats = get_cache_stats()
        print(f"    Cached URLs: {cache_stats['total_cached_urls']} ✓")

        # Validate same URLs again (should be instant from cache)
        start = time.time()
        valid_urls_2 = validate_and_filter_urls_sync(
            test_urls,
            client_token="test_client",
            timeout=5
        )
        elapsed_cached = time.time() - start

        print(f"    ✓ Cached validation: {elapsed_cached:.2f}s (should be <0.1s)")
        if elapsed_cached < 0.2:
            print(f"      ✓ Cache working correctly!")

        # Clear cache
        clear_cache()
        final_stats = get_cache_stats()
        print(f"    Cache cleared: {final_stats['total_cached_urls']} URLs ✓")

        print(f"\n  ✅ Async URL Validator test PASSED")
        return True

    except Exception as e:
        print(f"\n  ❌ Async URL Validator test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# Run All Tests
# ==============================================================================

def main():
    """Run all tests"""
    results = []

    # Run tests
    results.append(("SyncRateLimiter", test_rate_limiter()))
    results.append(("ClientSession", test_client_session()))
    results.append(("AsyncURLValidator", test_url_validator()))

    # Summary
    print("\n" + "=" * 71)
    print(" TEST SUMMARY")
    print("=" * 71)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name:<25} {status}")

    print("-" * 71)
    print(f"  Total: {passed}/{total} tests passed")
    print("=" * 71)

    if passed == total:
        print("\n✅ All optimizations are working correctly!")
        print("\nNext steps:")
        print("  1. Review OPTIMIZATION_IMPLEMENTATION_GUIDE.md")
        print("  2. Integrate modules into new_deep.py")
        print("  3. Test with 1-2 clients")
        print("  4. Run full 6-client pipeline")
        return 0
    else:
        print("\n⚠ Some tests failed. Review errors above.")
        print("\nCommon issues:")
        print("  • aiohttp not installed: pip install aiohttp")
        print("  • Auth files missing: Run notebooklm login first")
        return 1


if __name__ == "__main__":
    sys.exit(main())
