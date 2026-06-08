#!/usr/bin/env python3
"""
Integration Tests for Project APE
Tests end-to-end functionality without requiring real NotebookLM CLI
"""

import sys
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import subprocess

# Add current directory to path
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

print("=" * 71)
print(" PROJECT APE - INTEGRATION TESTS")
print("=" * 71)
print()

# ==============================================================================
# Test 1: Auth Validation Logic
# ==============================================================================

def test_auth_validation():
    """Test AuthRefreshManager auth validation logic"""
    print("Test 1: Auth Validation Logic")
    print("-" * 71)

    try:
        # Mock subprocess to simulate expired auth
        def mock_run_expired(*args, **kwargs):
            result = MagicMock()
            result.returncode = 2
            result.stderr = "Unexpected error: Authentication expired or invalid"
            result.stdout = ""
            return result

        def mock_run_valid(*args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            result.stdout = "Notebook list success"
            return result

        # Test expired auth detection
        with patch('subprocess.run', side_effect=mock_run_expired):
            from deep_v3_optimized import AuthRefreshManager

            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                shared_auth = tmpdir_path / "shared.json"
                default_auth = tmpdir_path / "default.json"

                # Create dummy auth files
                shared_auth.write_text('{"auth": "data"}')
                default_auth.write_text('{"auth": "data"}')

                manager = AuthRefreshManager(
                    shared_auth_path=shared_auth,
                    default_auth_path=default_auth,
                    script_dir=tmpdir_path,
                    interval=300
                )

                # Test expired auth detection
                is_valid = manager._test_auth(default_auth)
                assert is_valid == False, "Should detect expired auth"
                print("  ✓ Expired auth detected correctly")

        # Test valid auth detection
        with patch('subprocess.run', side_effect=mock_run_valid):
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                default_auth = tmpdir_path / "default.json"
                default_auth.write_text('{"auth": "data"}')

                manager = AuthRefreshManager(
                    shared_auth_path=tmpdir_path / "shared.json",
                    default_auth_path=default_auth,
                    script_dir=tmpdir_path,
                    interval=300
                )

                is_valid = manager._test_auth(default_auth)
                assert is_valid == True, "Should detect valid auth"
                print("  ✓ Valid auth detected correctly")

        print("  ✅ Test 1 PASSED\n")
        return True

    except Exception as e:
        print(f"  ❌ Test 1 FAILED: {e}\n")
        return False

# ==============================================================================
# Test 2: Configuration Loading
# ==============================================================================

def test_configuration_loading():
    """Test vars.py configuration loading"""
    print("Test 2: Configuration Loading")
    print("-" * 71)

    try:
        import vars as config

        # Check required attributes
        assert hasattr(config, 'clients'), "Missing clients list"
        assert hasattr(config, 'persona'), "Missing persona"

        print(f"  ✓ Configuration loaded successfully")
        print(f"  ✓ Clients defined: {len(config.clients)}")
        print(f"  ✓ Persona: {config.persona}")

        # Validate each client has required attributes
        for client in config.clients:
            name_attr = f"{client}_name"
            industry_attr = f"{client}_industry"
            folder_attr = f"{client}_folder"

            assert hasattr(config, name_attr), f"Missing {name_attr}"
            assert hasattr(config, industry_attr), f"Missing {industry_attr}"
            # folder_attr is optional for test clients

            print(f"  ✓ Client '{client}' configuration valid")

        print("  ✅ Test 2 PASSED\n")
        return True

    except Exception as e:
        print(f"  ❌ Test 2 FAILED: {e}\n")
        return False

# ==============================================================================
# Test 3: Dashboard Manager Integration
# ==============================================================================

def test_dashboard_manager():
    """Test DashboardManager creation and updates"""
    print("Test 3: Dashboard Manager Integration")
    print("-" * 71)

    try:
        from common import DashboardManager

        with tempfile.TemporaryDirectory() as tmpdir:
            dashboard_path = Path(tmpdir) / "test_dashboard.html"

            # Create dashboard
            dashboard = DashboardManager(dashboard_path, mode="TEST")
            print("  ✓ Dashboard created")

            # Update with client data
            dashboard.update(
                client_token="test_client",
                client_name="Test Client",
                step="Testing",
                progress=50,
                status="RUNNING"
            )
            print("  ✓ Dashboard updated")

            # Verify file was created
            assert dashboard_path.exists(), "Dashboard file should exist"
            print("  ✓ Dashboard file created")

            # Verify content
            content = dashboard_path.read_text()
            assert "Test Client" in content, "Client name should appear in dashboard"
            assert "50" in content, "Progress should appear in dashboard"
            print("  ✓ Dashboard content validated")

            # Test increment
            dashboard.increment_finished()
            assert dashboard.finished_count == 1, "Finished count should increment"
            print("  ✓ Dashboard metrics work")

        print("  ✅ Test 3 PASSED\n")
        return True

    except Exception as e:
        print(f"  ❌ Test 3 FAILED: {e}\n")
        return False

# ==============================================================================
# Test 4: State Manager Persistence
# ==============================================================================

def test_state_manager():
    """Test state persistence and recovery"""
    print("Test 4: State Manager Persistence")
    print("-" * 71)

    try:
        from state_manager import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "test_state.json"

            # Create state manager
            state = StateManager(state_file)
            print("  ✓ State manager created")

            # Set client state
            state.set_client_status("test_client", "in_progress")
            state.set_client_phase("test_client", "prompt_execution")
            print("  ✓ Client state updated")

            # Save state
            state.save()
            assert state_file.exists(), "State file should exist"
            print("  ✓ State saved to file")

            # Load state in new instance
            state2 = StateManager(state_file)
            assert state2.get_client_status("test_client") == "in_progress"
            assert state2.get_client_phase("test_client") == "prompt_execution"
            print("  ✓ State loaded from file")

            # Test resume logic
            assert state2.should_skip_phase("test_client", "authentication") == True
            assert state2.should_skip_phase("test_client", "prompt_execution") == False
            print("  ✓ Resume logic works")

        print("  ✅ Test 4 PASSED\n")
        return True

    except Exception as e:
        print(f"  ❌ Test 4 FAILED: {e}\n")
        return False

# ==============================================================================
# Test 5: Metrics Collection
# ==============================================================================

def test_metrics():
    """Test metrics collection and export"""
    print("Test 5: Metrics Collection")
    print("-" * 71)

    try:
        from metrics import MetricsCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_file = Path(tmpdir) / "test_metrics.json"

            # Create metrics collector
            metrics = MetricsCollector(metrics_file)
            print("  ✓ Metrics collector created")

            # Record metrics
            metrics.record_execution_time("test_operation", 1.5)
            metrics.record_retry("test_client", "test_command")
            metrics.record_retry("test_client", "test_command")
            print("  ✓ Metrics recorded")

            # Export metrics
            metrics.export()
            assert metrics_file.exists(), "Metrics file should exist"
            print("  ✓ Metrics exported to file")

            # Verify content
            data = json.loads(metrics_file.read_text())
            assert "execution_times" in data or "executions" in data
            print("  ✓ Metrics content validated")

        print("  ✅ Test 5 PASSED\n")
        return True

    except Exception as e:
        print(f"  ❌ Test 5 FAILED: {e}\n")
        return False

# ==============================================================================
# Test 6: Validators Framework
# ==============================================================================

def test_validators():
    """Test prompt validation framework"""
    print("Test 6: Validators Framework")
    print("-" * 71)

    try:
        from validators import validate_output, calculate_quality_score

        # Test valid output
        valid_output = " ".join(["word"] * 500)  # 500 words
        valid_output += "\n[Source: Test Source 1]\n[Source: Test Source 2]"

        validation_rules = {
            "min_words": 400,
            "max_words": 700,
            "min_citations": 2
        }

        is_valid, score = validate_output(valid_output, validation_rules)
        assert is_valid == True, "Valid output should pass"
        assert score >= 7.0, "Quality score should be >= 7.0"
        print(f"  ✓ Valid output passed (score: {score})")

        # Test invalid output (too short)
        invalid_output = " ".join(["word"] * 50)  # Only 50 words
        is_valid, score = validate_output(invalid_output, validation_rules)
        assert is_valid == False, "Short output should fail"
        print(f"  ✓ Invalid output detected (score: {score})")

        print("  ✅ Test 6 PASSED\n")
        return True

    except Exception as e:
        print(f"  ❌ Test 6 FAILED: {e}\n")
        return False

# ==============================================================================
# Test 7: Error Recovery
# ==============================================================================

def test_error_recovery():
    """Test exponential backoff and retry logic"""
    print("Test 7: Error Recovery Logic")
    print("-" * 71)

    try:
        # Mock execute_with_backoff behavior
        attempt_count = 0

        def mock_command_fail_twice(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise subprocess.CalledProcessError(1, "test")
            result = MagicMock()
            result.returncode = 0
            result.stdout = "success"
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_command_fail_twice):
            from deep_v3_optimized import execute_with_backoff

            # Should succeed on 3rd attempt
            result = execute_with_backoff(
                ["test", "command"],
                client_token="test",
                max_attempts=3,
                base_delay=0.1  # Fast for testing
            )

            assert attempt_count == 3, "Should retry exactly 3 times"
            print(f"  ✓ Retried {attempt_count} times (expected 3)")
            print("  ✓ Exponential backoff works")

        print("  ✅ Test 7 PASSED\n")
        return True

    except Exception as e:
        print(f"  ❌ Test 7 FAILED: {e}\n")
        return False

# ==============================================================================
# Run All Tests
# ==============================================================================

def main():
    """Run all integration tests"""
    print("Running integration tests...\n")

    tests = [
        test_auth_validation,
        test_configuration_loading,
        test_dashboard_manager,
        test_state_manager,
        test_metrics,
        test_validators,
        test_error_recovery,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"FATAL ERROR in {test.__name__}: {e}\n")
            results.append(False)

    # Summary
    print("=" * 71)
    print(f" INTEGRATION TEST SUMMARY: {sum(results)}/{len(results)} PASSED")
    print("=" * 71)

    for i, (test, result) in enumerate(zip(tests, results), 1):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {test.__name__}")

    print()

    if all(results):
        print("🎉 All integration tests passed!")
        return 0
    else:
        print("⚠️ Some integration tests failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
