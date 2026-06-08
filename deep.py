#!/usr/bin/env python3
"""
Project APE - Deep Mode Execution (V3 Optimized)
Automated Account Planning Engine with deep research capabilities.

Author: Project APE Team
Python: 3.9+
"""

import glob
import json
import logging
import os
import subprocess
import sys
import time
import queue
import re
import random
import threading
import webbrowser
import csv
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

# Import shared utilities from common module
try:
    from common import (
        DashboardManager,
        validate_and_filter_urls,
        execute_with_backoff as common_execute_with_backoff,
    )
    URL_VALIDATION_AVAILABLE = True
    DASHBOARD_MANAGER_AVAILABLE = True
except ImportError:
    URL_VALIDATION_AVAILABLE = False
    DASHBOARD_MANAGER_AVAILABLE = False
    logging.warning("Common utilities not available - common.py not found")

# OPTIMIZATION: Import new optimization modules
from lib.sync_rate_limiter import SyncRateLimiter
from lib.client_session import SessionPool
from lib.async_url_validator import validate_and_filter_urls_sync

# --- Fallback Check for Google API Dependencies ---
try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
except ImportError:
    print("Error: Missing required Google API dependencies. Run 'pip install google-api-python-client'", file=sys.stderr)
    sys.exit(1)

# --- Configuration & Setup ---
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.append(str(SCRIPT_DIR))

# PRODUCTION: Environment-based configuration
class DeepModeConfig:
    """Configuration with environment variable overrides

    CRITICAL FIX: Google's deep research API has VERY strict rate limits.
    Empirical testing shows ~1 deep research request per 2-3 minutes MAX.
    """
    # CRITICAL: Deep research rate limiting (much stricter than regular API)
    # Default: 1 request per 2 minutes (0.5 req/min)
    RATE_LIMIT_RPM = float(os.getenv("DEEP_RATE_LIMIT_RPM", "0.5"))
    RATE_LIMIT_BURST = int(os.getenv("DEEP_RATE_LIMIT_BURST", "1"))

    # CRITICAL: Use 1 worker to prevent concurrent deep research
    MAX_WORKERS = int(os.getenv("DEEP_MAX_WORKERS", "1"))

    AUTH_REFRESH_INTERVAL = float(os.getenv("DEEP_AUTH_REFRESH_INTERVAL", "240"))
    DEEP_MODE_TIMEOUT = float(os.getenv("DEEP_MODE_TIMEOUT", "480"))
    MAX_RETRIES = int(os.getenv("DEEP_MAX_RETRIES", "5"))

    # CRITICAL: Longer delays for deep research
    DEEP_RESEARCH_BASE_DELAY = float(os.getenv("DEEP_RESEARCH_BASE_DELAY", "120.0"))  # 2 minutes
    DEEP_RESEARCH_COOLDOWN_MIN = float(os.getenv("DEEP_RESEARCH_COOLDOWN_MIN", "90.0"))  # 1.5 min
    DEEP_RESEARCH_COOLDOWN_MAX = float(os.getenv("DEEP_RESEARCH_COOLDOWN_MAX", "150.0"))  # 2.5 min

    SESSION_CLEANUP_ENABLED = os.getenv("DEEP_SESSION_CLEANUP", "true").lower() == "true"

deep_config = DeepModeConfig()

try:
    import vars as config
except ImportError:
    print(f"Error: Could not find vars.py in {SCRIPT_DIR}", file=sys.stderr)
    sys.exit(1)

LOG_FILE_NAME_CLEAN = "pipeline_deep_execution.log"
dashboard_filename = getattr(config, "DASHBOARD_NAME", "pipeline_dashboard.html")

try:
    LOG_FILE_PATH = PROJECT_ROOT / LOG_FILE_NAME_CLEAN
    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE_PATH, 'a'): pass
except Exception:
    LOG_FILE_PATH = SCRIPT_DIR / LOG_FILE_NAME_CLEAN

DASHBOARD_PATH = SCRIPT_DIR / dashboard_filename

log_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    datefmt="%H:%M:%S"
)

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

if root_logger.hasHandlers():
    root_logger.handlers.clear()

file_handler = logging.FileHandler(LOG_FILE_PATH, mode="w", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(log_formatter)
root_logger.addHandler(file_handler)

# OPTIMIZED: Use DashboardManager from common.py (same as fast.py)
if DASHBOARD_MANAGER_AVAILABLE:
    dashboard = DashboardManager(DASHBOARD_PATH, mode="DEEP")
else:
    # Fallback to legacy dashboard if common.py not available
    ui_queue = queue.Queue()
    dashboard_lock = threading.Lock()
    console_print_lock = threading.Lock()
    dashboard_state = {}
    start_time_global = time.time()
    finished_pipelines_count = 0
    total_pipelines_count = 0
    dashboard = None

# OPTIMIZED: Replace semaphore lock with rate limiter + session pool
deep_rate_limiter = SyncRateLimiter(
    requests_per_minute=deep_config.RATE_LIMIT_RPM,
    burst=deep_config.RATE_LIMIT_BURST
)
session_pool = SessionPool(storage_dir=SCRIPT_DIR)

# OPTIMIZATION: Shutdown event for graceful termination
shutdown_event = threading.Event()

# CRITICAL: Background auth refresh manager to prevent token expiration
class AuthRefreshManager:
    """Periodically refreshes auth from default profile to prevent Google OAuth token expiration"""
    def __init__(self, shared_auth_path, default_auth_path, script_dir, interval=300):
        self.shared_auth_path = shared_auth_path
        self.default_auth_path = default_auth_path
        self.script_dir = script_dir
        self.interval = interval  # 5 minutes default
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

    def start(self):
        """Start background auth refresh thread"""
        with self.lock:
            if not self.running:
                self.running = True
                self.thread = threading.Thread(target=self._refresh_loop, daemon=True, name="AuthRefresh")
                self.thread.start()
                logging.info(f"Auth refresh manager started (interval: {self.interval}s)")

    def stop(self):
        """Stop background auth refresh"""
        with self.lock:
            self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def _refresh_loop(self):
        """Periodically copy fresh auth from default profile, re-authenticating if needed"""
        while self.running:
            time.sleep(self.interval)
            if not self.running:
                break

            try:
                # CRITICAL FIX: Validate auth before copying
                if self.default_auth_path.exists():
                    import shutil
                    import subprocess

                    # Test if default auth is still valid
                    is_valid = self._test_auth(self.default_auth_path)

                    if not is_valid:
                        logging.warning("⚠️ Default auth expired, triggering re-authentication...")

                        # Attempt to re-authenticate
                        if not self._reauth():
                            logging.error("❌ Re-authentication failed, will retry next cycle")
                            continue

                    # Copy fresh auth to shared location
                    shutil.copy2(self.default_auth_path, self.shared_auth_path)
                    logging.info("✅ Auth refreshed from default profile")

                    # Update all client storage files
                    updated = 0
                    for storage_file in self.script_dir.glob(".storage_*.json"):
                        if not storage_file.name.endswith(".context.json"):
                            shutil.copy2(self.shared_auth_path, storage_file)
                            updated += 1

                    if updated > 0:
                        logging.debug(f"Updated {updated} client storage files with fresh auth")
                else:
                    logging.warning("Default auth profile not found, skipping refresh")
            except Exception as e:
                logging.warning(f"Auth refresh failed: {e}")

    def _test_auth(self, auth_path):
        """Test if auth file is valid by running a simple command"""
        try:
            import subprocess
            result = subprocess.run(
                ["notebooklm", "--storage", str(auth_path), "list"],
                capture_output=True,
                text=True,
                timeout=10
            )
            # Check for auth errors
            if "expired" in result.stderr.lower() or "invalid" in result.stderr.lower() or "not logged in" in result.stdout.lower():
                return False
            return result.returncode == 0
        except Exception as e:
            logging.debug(f"Auth test failed: {e}")
            return False

    def _reauth(self):
        """Trigger interactive re-authentication"""
        try:
            import subprocess

            logging.info("🔐 Triggering re-authentication...")
            print("\n" + "="*71)
            print("🔐 AUTHENTICATION REQUIRED")
            print("="*71)
            print("Your Google OAuth token has expired.")
            print("A browser window will open for re-authentication.")
            print("="*71 + "\n")

            # Run login command
            result = subprocess.run(["notebooklm", "login"], check=False, text=True)

            if result.returncode == 0 and self.default_auth_path.exists():
                # Verify new auth works
                if self._test_auth(self.default_auth_path):
                    logging.info("✅ Re-authentication successful")
                    print("\n✅ Re-authentication successful!\n")
                    return True
                else:
                    logging.error("❌ Re-authentication produced invalid auth")
                    return False
            else:
                logging.error("❌ Re-authentication failed or was cancelled")
                return False

        except Exception as e:
            logging.error(f"Re-authentication error: {e}")
            return False

auth_refresh_manager = None

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    print("\n\n⚠️  Interrupt received! Shutting down gracefully...")
    print("Stopping running tasks and cleaning up...")
    shutdown_event.set()
    logging.info("SHUTDOWN: User interrupt received")
    sys.exit(0)

# Pre-compiled Regex Patterns
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
SOURCES_PATTERN = re.compile(r'\b\d+\s+source(s)?\b', re.IGNORECASE)
DIVIDER_PATTERN = re.compile(r'│|┃|║|─|═|-|_|:|\+')
NON_ASCII_PATTERN = re.compile(r'[^\x00-\x7F]+')
DATE_PATTERN = re.compile(r'\d{4}-\d{2}-\d{2}|\d{2}:\d{2}|\b[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\b')
STATUS_KEYWORDS = re.compile(r'\b(ready|processing|waiting|status|uuid|title|created|owner)\b', re.IGNORECASE)
NON_ALPHANUM_PATTERN = re.compile(r'[^a-zA-Z0-9]')
UUID_PATTERN = re.compile(r'([a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12})', re.IGNORECASE)

# Throttle Match Optimization
THROTTLE_PATTERN = re.compile(
    r"quota|rate limit|exhausted|429|503|too many requests|resource_exhausted|rate limited|ratelimiterror|user_displayable_error",
    re.IGNORECASE
)

def log_subprocess_noise(client_token, stderr_content):
    if not stderr_content:
        return
    for line in stderr_content.splitlines():
        line = line.strip()
        if not line or "rpc.decoder" in line or "Byte-count mismatch" in line:
            continue
        if "WARNING" in line or "ERROR" in line:
            logging.warning(f"[{client_token} Subprocess Sideband] {line}")
        else:
            logging.debug(f"[{client_token} Subprocess Stderr] {line}")

def normalize_name_string(text):
    if not text:
        return ""
    cleaned = ANSI_ESCAPE.sub('', text)
    cleaned = SOURCES_PATTERN.sub(' ', cleaned)
    cleaned = DIVIDER_PATTERN.sub(' ', cleaned)
    cleaned = NON_ASCII_PATTERN.sub(' ', cleaned)
    cleaned = DATE_PATTERN.sub(' ', cleaned)
    cleaned = STATUS_KEYWORDS.sub(' ', cleaned)
    return NON_ALPHANUM_PATTERN.sub('', cleaned).lower().strip()

def execute_with_backoff(
    cmd: List[str],
    client_token: str = "Orchestrator",
    input_data: Optional[str] = None,
    max_attempts: int = 3,
    base_delay: float = 30.0,
    cmd_timeout: float = 300.0
) -> subprocess.CompletedProcess:
    """
    Executes a subprocess command with exponential backoff retry logic.
    """
    last_res = None
    for attempt in range(max_attempts):
        try:
            logging.info(f"Executing Subprocess: {' '.join(cmd)}")
            res = subprocess.run(
                cmd,
                input=input_data,
                check=False,
                text=True,
                capture_output=True,
                timeout=cmd_timeout
            )
            last_res = res
            log_subprocess_noise(client_token, res.stderr)

            err_text = res.stderr or ""
            out_text = res.stdout or ""

            if THROTTLE_PATTERN.search(err_text) or THROTTLE_PATTERN.search(out_text):
                logging.warning(f"[{client_token}] Rate limit/Error intercepted on attempt {attempt + 1} of {max_attempts}.")
                if attempt < max_attempts - 1:
                    sleep_duration = (pow(2, attempt) * base_delay) + random.uniform(15.0, 30.0)
                    time.sleep(sleep_duration)
                    continue
                else:
                    break # Exhausted attempts

            if res.returncode != 0:
                logging.error(f"[{client_token}] Command failed with exit code {res.returncode}. Stderr: {res.stderr}")
                if attempt < max_attempts - 1:
                    time.sleep((pow(2, attempt) * base_delay) + random.uniform(15.0, 30.0))
                    continue
                else:
                    break # Exhausted attempts

            return res # Success

        except subprocess.TimeoutExpired:
            logging.critical(f"[{client_token}] Subprocess timed out on attempt {attempt + 1}: {' '.join(cmd)}")
        except Exception as e:
            logging.warning(f"[{client_token}] Execution resistance encountered on attempt {attempt + 1}: {str(e)}")

        if attempt < max_attempts - 1:
            time.sleep((pow(2, attempt) * base_delay) + random.uniform(15.0, 30.0))

    error_msg = f"\n[LOCAL FAILURE] Client '{client_token}' failed command after {max_attempts} attempts. Aborting step.\n"
    logging.critical(f"PIPELINE DEGRADED: {client_token} exhausted retries on command: {' '.join(cmd)}")
    raise RuntimeError(error_msg)

# GLOBAL DICTIONARY TO TRACK AUTHENTICATION REFRESH TIMESTAMPS
last_auth_refresh_times = {}

# OPTIMIZED: Improved auth refresh with actual expiration and interval handling
def safe_auth_refresh(client_storage, client_str, min_interval=None):
    """Refresh auth token with configurable interval and expiration handling."""
    global last_auth_refresh_times
    
    # Check if we are within the cooldown period to prevent SSO server spam
    if min_interval is not None:
        now = time.time()
        last_refresh = last_auth_refresh_times.get(client_str, 0)
        if (now - last_refresh) < min_interval:
            logging.debug(f"[{client_str}] Skipping auth refresh (cooldown active).")
            return

    try:
        # Try to refresh
        result = subprocess.run(
            ["notebooklm", "--storage", str(client_storage), "auth", "refresh", "--quiet"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Record the time of this attempt, whether it succeeded or failed
        if min_interval is not None:
            last_auth_refresh_times[client_str] = time.time()

        # Check if auth expired
        if result.returncode != 0 and ("expired" in result.stderr.lower() or "invalid" in result.stderr.lower()):
            logging.error(f"[{client_str}] Auth expired! Need to re-login.")
            print(f"\n❌ Authentication expired for {client_str}")
            print("Please run: notebooklm login")
            print("Then restart the script.\n")
            raise RuntimeError("Authentication expired - please re-login")

        if result.returncode == 0:
            logging.info(f"[{client_str}] Auth token refreshed")
        else:
            logging.warning(f"[{client_str}] Auth refresh returned code {result.returncode}")
            
    except subprocess.TimeoutExpired:
        logging.warning(f"[{client_str}] Auth refresh timed out")
    except RuntimeError:
        raise  # Re-raise auth expiration errors
    except Exception as e:
        logging.warning(f"[{client_str}] Auth refresh failed: {e}")

def track_global_progress(phase_title="DEEP"):
    if not DASHBOARD_MANAGER_AVAILABLE or not dashboard:
        ui_queue.put({"type": "render", "phase_title": phase_title})

def background_ui_manager():
    global finished_pipelines_count, total_pipelines_count, dashboard_state
    last_ui_update = 0
    current_phase = "DEEP"

    while True:
        try:
            item = ui_queue.get(timeout=0.1)
            if item.get("type") == "shutdown":
                break
            if "phase_title" in item:
                current_phase = item["phase_title"]
        except queue.Empty:
            pass

        now = time.time()
        if now - last_ui_update >= 1.0:
            with console_print_lock:
                width = 30
                pct = int((finished_pipelines_count / total_pipelines_count) * 100) if total_pipelines_count > 0 else 100
                filled_length = int(round(width * pct / 100))
                bar = '█' * filled_length + '░' * (width - filled_length)

                sys.stdout.write("\033[H\033[J")
                sys.stdout.write("=======================================================================\n")
                sys.stdout.write(" ⛭ \033[1mRED HAT ACCOUNT PLANNING ENGINE — DEEP MODE CONSOLE (V3 OPTIMIZED)\033[0m\n")
                sys.stdout.write("=======================================================================\n")
                sys.stdout.write(f" [{current_phase:<7}] Progress: |\033[91m{bar}\033[0m| \033[92m{pct:>3}%\033[0m ({finished_pipelines_count}/{total_pipelines_count} Pipelines Finalized)\n")
                sys.stdout.write("-------------------------------------------------------------------\n")
                sys.stdout.write(f" {'WORKSPACE BLOCK':<25} | {'PROGRESS':<10} | {'CURRENT OPERATIONAL PHASE':<35}\n")
                sys.stdout.write("-------------------------------------------------------------------\n")

                with dashboard_lock:
                    for token, data in dashboard_state.items():
                        name_trunc = (data["name"][:22] + '...') if len(data["name"]) > 25 else data["name"]
                        status_color = "\033[93m" if data["status"] in ["RUNNING", "DEGRADED"] else ("\033[92m" if data["status"] == "COMPLETE" else "\033[90m")
                        if data["status"] == "FAILED": status_color = "\033[91m"
                        sys.stdout.write(f" {name_trunc:<25} | {status_color}{data['progress']:>3}%\033[0m      | {data['step']:<35}\n")
                sys.stdout.write("=======================================================================\n")
                sys.stdout.flush()

            write_dashboard_html()
            last_ui_update = now

def write_dashboard_html():
    global start_time_global
    elapsed_seconds = int(time.time() - start_time_global)
    minutes = elapsed_seconds // 60
    seconds = elapsed_seconds % 60
    timer_string = f"{minutes:02d}m {seconds:02d}s"

    with dashboard_lock:
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Red Hat Unified Account Planning Console - V3 Optimized</title>
    <meta http-equiv="refresh" content="2">
    <style>
        body {{ font-family: "RedHatText", "Overpass", Arial, sans-serif; background-color: #0b0d10; color: #f5f5f7; margin: 0; padding: 0; -webkit-font-smoothing: antialiased; }}
        .rh-banner {{ display: flex; flex-direction: row; align-items: center; justify-content: space-between; padding: 24px 42px; background: linear-gradient(135deg, #151515 0%, #252525 100%); color: #ffffff; border-bottom: 4px solid #cc0000; box-shadow: 0 4px 20px rgba(0,0,0,0.5); height: 96px; box-sizing: border-box; }}
        .header-left {{ display: flex; flex-direction: row; align-items: center; gap: 20px; flex: 1; justify-content: flex-start; }}
        .header-center {{ display: flex; justify-content: center; align-items: center; flex: 1; }}
        .header-right {{ display: flex; justify-content: flex-end; align-items: center; flex: 1; height: 100%; }}
        .rh-logo-title {{ font-size: 2.16rem; font-weight: 500; letter-spacing: -0.5px; color: #ffffff; margin: 0; white-space: nowrap; }}
        .rh-logo-bold {{ color: #ff3333; font-weight: 900; letter-spacing: -1px; }}
        .badge-lap {{ padding: 6px 16px; background: #cc0000; border: 2px solid #ffffff; color: #ffffff; font-weight: 900; font-size: 1rem; letter-spacing: 2px; border-radius: 4px; box-shadow: 0 0 25px rgba(255, 51, 51, 0.6); text-transform: uppercase; text-align: center; animation: pulse 2s infinite; margin: 0; white-space: nowrap; }}
        .deep-mode-text {{ font-size: 2.16rem; font-weight: 800; text-transform: uppercase; letter-spacing: 3px; color: #33ff33; text-shadow: 0 0 10px rgba(51, 255, 51, 0.5); margin: 0; white-space: nowrap; }}
        .rh-header-logo {{ max-height: 60px; width: auto; object-fit: contain; display: block; }}
        @keyframes pulse {{
            0% {{ box-shadow: 0 0 25px rgba(255, 51, 51, 0.6); }}
            50% {{ box-shadow: 0 0 40px rgba(255, 51, 51, 0.9); }}
            100% {{ box-shadow: 0 0 25px rgba(255, 51, 51, 0.6); }}
        }}
        .main-layout {{ max-width: 1300px; margin: 35px auto; padding: 0 25px; }}
        .status-alert {{ display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 30px; background: #151515; border: 2px solid #3c3f42; border-top: 4px solid #33ff33; border-radius: 6px; margin-bottom: 35px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); gap: 15px; text-align: center; }}
        .metrics-title {{ font-weight: 700; font-size: 1.12rem; color: #d1d5db; letter-spacing: 0.5px; text-transform: uppercase; }}
        .giant-timer {{ font-family: 'Courier New', monospace; font-size: 2.34rem; color: #33ff33; background: #000000; padding: 8px 26px; border-radius: 6px; font-weight: 900; border: 2px solid #33ff33; box-shadow: inset 0 0 20px rgba(51, 255, 51, 0.4), 0 0 15px rgba(51, 255, 51, 0.3); letter-spacing: 2px; }}
        .grid-container {{ display: grid; grid-gap: 25px; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); }}
        .rh-card {{ background: #151515; border: 1px solid #2f3133; border-radius: 6px; padding: 24px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); transition: all 0.2s ease; display: flex; flex-direction: column; justify-content: space-between; }}
        .rh-card:hover {{ border-color: #33ff33; box-shadow: 0 6px 20px rgba(51,255,51,0.15); }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 1px solid #212427; padding-bottom: 10px; }}
        .client-name {{ font-size: 1.4rem; font-weight: 700; color: #ffffff; }}
        .progress-track {{ height: 16px; background: #212427; border-radius: 4px; overflow: hidden; margin: 15px 0; border: 1px solid #2f3133; }}
        .progress-fill {{ height: 100%; background: linear-gradient(90deg, #3e8635 0%, #5ba34c 100%); box-shadow: inset 0 1px 2px rgba(255,255,255,0.1); transition: width 0.4s ease; }}
        .status-pill {{ font-size: 0.8rem; font-weight: 800; padding: 6px 16px; border-radius: 30px; text-transform: uppercase; letter-spacing: 1px; }}
        .pill-RUNNING {{ background: rgba(51,255,51,0.15); color: #8bc34a; border: 1px solid #33ff33; }}
        .pill-QUEUED {{ background: rgba(0, 150, 255, 0.1); color: #63b3ed; border: 1px solid #3182ce; }}
        .pill-COMPLETE {{ background: rgba(62,134,53,0.15); color: #8bc34a; border: 1px solid #3e8635; }}
        .pill-DEGRADED {{ background: rgba(236,122,8,0.15); color: #f4c176; border: 1px solid #ec7a08; }}
        .pill-FAILED {{ background: rgba(201,25,11,0.15); color: #ff6b6b; border: 1px solid #c9190b; }}
        .pill-PENDING {{ background: #212427; color: #d1d5db; border: 1px solid #4f5255; }}
        .step-log {{ font-size: 0.95rem; color: #d1d5db; display: flex; flex-direction: column; gap: 12px; background: #0b0d10; padding: 12px; border-radius: 4px; border: 1px solid #212427; }}
        .step-text-row {{ display: flex; justify-content: space-between; align-items: center; width: 100%; }}
        .meta-sector {{ font-size: 0.8rem; color: #8a8d90; font-style: italic; margin-top: -8px; margin-bottom: 10px; }}
        .rh-box-container {{ background-color: #162235; border: 1px solid #0096ff; border-radius: 6px; padding: 10px; text-align: center; margin-top: 8px; box-shadow: 0 2px 10px rgba(0, 150, 255, 0.25); }}
        .plan-btn {{ display: block; background: #0096ff; color: white; text-decoration: none; padding: 8px 14px; font-size: 0.85rem; font-weight: bold; border-radius: 4px; text-transform: uppercase; transition: background 0.2s ease, border-color 0.2s ease; border: 1px solid transparent; }}
        .plan-btn:hover {{ background: #33a8ff; border-color: #ffffff; }}
    </style>
</head>
<body>
    <div class="rh-banner">
        <div class="header-left">
            <div class="rh-logo-title"><span class="rh-logo-bold">Red Hat</span> Account Planning Engine</div>
            <div class="badge-lap">Project APE</div>
        </div>
        <div class="header-center">
            <div class="deep-mode-text">V3 Optimized</div>
        </div>
        <div class="header-right">
            <img src="data:image/png;base64,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" class="rh-header-logo" alt="Red Hat Logo">
        </div>
    </div>
    <div class="main-layout">
        <div class="status-alert">
            <div class="metrics-title">Central Orchestrator Fleet Execution Timer (Optimized Pipeline)</div>
            <div class="giant-timer">{timer_string}</div>
        </div>
        <div class="grid-container">
    """
        for token, data in dashboard_state.items():
            plan_url = data["plan_link"] if data["plan_link"] else "#"
            html_content += f"""
            <div class="rh-card">
                <div>
                    <div class="card-header">
                        <span class="client-name">{data["name"]}</span>
                        <span class="status-pill pill-{data["status"]}">{data["status"]}</span>
                    </div>
                    <div class="meta-sector">System Workspace Block ID: {token}</div>
                    <div class="progress-track">
                        <div class="progress-fill" style="width: {data["progress"]}%;"></div>
                    </div>
                </div>
                <div class="step-log">
                    <div class="step-text-row">
                        <span>Current Step: <strong style="color:#33ff33;">{data["step"]}</strong></span>
                        <span style="color:#8a8d90; font-family:monospace; font-weight:bold;">{data["progress"]}%</span>
                    </div>
                    {f'<div class="rh-box-container"><a class="plan-btn" href="{plan_url}" target="_blank">{data["name"]} Account Plan</a></div>' if data["plan_link"] else ""}
                </div>
            </div>
            """
        html_content += "</div></div></body></html>"

    try:
        # Use .html.tmp to avoid replacing .html suffix entirely
        tmp_dashboard = Path(str(DASHBOARD_PATH) + ".tmp")
        tmp_dashboard.write_text(html_content, encoding="utf-8")
        os.replace(str(tmp_dashboard), str(DASHBOARD_PATH))
    except IOError:
        pass

def update_dashboard(
    client_token: str,
    step: Optional[str] = None,
    progress: Optional[int] = None,
    status: Optional[str] = None,
    plan_link: Optional[str] = None,
    **kwargs: Any
) -> None:
    """
    Update dashboard with client progress information.
    """
    client_name = getattr(config, f"{client_token}_name", client_token)

    if DASHBOARD_MANAGER_AVAILABLE and dashboard:
        dashboard.update(
            client_token=client_token,
            client_name=client_name,
            step=step,
            progress=progress,
            status=status,
            plan_link=plan_link,
            **kwargs 
        )
    else:
        with dashboard_lock:
            if client_token not in dashboard_state:
                dashboard_state[client_token] = {"name": client_name, "step": "Initializing", "progress": 0, "status": "PENDING", "plan_link": None}
            if step is not None: dashboard_state[client_token]["step"] = step
            if progress is not None: dashboard_state[client_token]["progress"] = progress
            if status is not None: dashboard_state[client_token]["status"] = status
            if plan_link is not None: dashboard_state[client_token]["plan_link"] = plan_link
            for key, value in kwargs.items():
                if value is not None:
                    dashboard_state[client_token][key] = value
        track_global_progress()

def fetch_notebook_cache(storage_path=None):
    cmd = ["notebooklm"]
    if storage_path: cmd.extend(["--storage", str(storage_path)])
    cmd.append("list")

    try:
        res = execute_with_backoff(cmd, client_token="Cache_Fetch")
    except RuntimeError:
        return {}

    cache = {}
    if not res or res.returncode != 0:
        return cache

    for line in res.stdout.splitlines():
        match = UUID_PATTERN.search(line)
        if match:
            nb_uuid = match.group(1)
            clean_name = line.replace(nb_uuid, "")
            for divider in ["│", "┃", "║", "  "]:
                if divider in clean_name:
                    parts = [p.strip() for p in clean_name.split(divider) if p.strip()]
                    if parts: clean_name = " ".join(parts)

            normalized_key = normalize_name_string(clean_name)
            if normalized_key:
                cache[normalized_key] = nb_uuid
    return cache

def ensure_notebook_exists(client_str: str, shared_auth_path: Path) -> Optional[Tuple[str, str, str]]:
    client_storage = SCRIPT_DIR / f".storage_{client_str}.json"

    update_dashboard(client_str, step="Pre-flight verification", progress=5, status="RUNNING")
    try:
        if shared_auth_path.exists():
            client_storage.write_text(shared_auth_path.read_text())

        name_value = getattr(config, f"{client_str}_name", "").strip()
        if not name_value:
            update_dashboard(client_str, step="Skipped", progress=0, status="PENDING")
            return None

        # OPTIMIZATION: Use per-client auth refresh
        safe_auth_refresh(client_storage, client_str, min_interval=240.0)
        notebook_cache = fetch_notebook_cache(storage_path=client_storage)
        normalized_target_name = normalize_name_string(name_value)

        nb_id = notebook_cache.get(normalized_target_name)
        if not nb_id:
            for cached_key, cached_uuid in notebook_cache.items():
                if normalized_target_name in cached_key or cached_key in normalized_target_name:
                    nb_id = cached_uuid
                    break

        if not nb_id:
            time.sleep(random.uniform(2.0, 4.0))
            cmd = ["notebooklm", "--storage", str(client_storage), "create", name_value]
            res = execute_with_backoff(cmd, client_token=client_str)
            uuid_match = UUID_PATTERN.search(res.stdout if res else "")
            nb_id = uuid_match.group(1) if uuid_match else None

        if not nb_id:
            raise Exception(f"Failed to map target workspace layout UUID for: {name_value}")

        update_dashboard(client_str, step="Workspace Active", progress=15, status="RUNNING", notebook_id=nb_id)
        return str(client_str), name_value, nb_id
    except Exception as e:
        update_dashboard(client_str, step="Pre-flight error", progress=100, status="FAILED")
        raise e

def convert_raw_csv_to_structured_text(csv_path):
    try:
        txt_output_path = Path(csv_path).with_suffix('.txt')
        structured_lines = []
        with open(csv_path, mode='r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f)
            headers = [h.strip() for h in next(reader, [])]
            for row_idx, row in enumerate(reader):
                structured_lines.append(f"=== RECORD ENTRY INDEX {row_idx + 1} ===")
                for col_idx, cell in enumerate(row):
                    header_label = headers[col_idx] if col_idx < len(headers) else f"Field_{col_idx}"
                    structured_lines.append(f"{header_label}: {cell.strip()}")
                structured_lines.append("")
        txt_output_path.write_text("\n".join(structured_lines), encoding="utf-8")
        return txt_output_path
    except Exception: return None

def ingest_client_sources(client_str, shared_auth_path, nb_id):
    client_storage = SCRIPT_DIR / f".storage_{client_str}.json"
    temporary_files_to_clean = []
    update_dashboard(client_str, step="Phase 0: Ingestion Inbound", progress=25, status="RUNNING")
    try:
        if shared_auth_path.exists(): client_storage.write_text(shared_auth_path.read_text())
        safe_auth_refresh(client_storage, client_str, min_interval=240.0)
        execute_with_backoff(["notebooklm", "--storage", str(client_storage), "use", nb_id, "--force"], client_token=client_str)

        client_folder_raw = getattr(config, f"{client_str}_folder", ".")
        drive_folder_value = Path(PROJECT_ROOT / client_folder_raw).resolve()

        drive_targets = []
        if drive_folder_value.exists() and drive_folder_value.is_dir():
            drive_targets.extend([str(p) for p in drive_folder_value.glob("*") if p.is_file() and not p.name.startswith(".")])
        if not drive_targets:
            update_dashboard(client_str, step="No Sources Found", progress=45, status="RUNNING")
            return "RUNNING"

        for idx, target_id in enumerate(drive_targets):
            is_local = os.path.exists(target_id) and os.path.isfile(target_id)
            if is_local and Path(target_id).suffix.lower() == '.csv':
                structural_txt = convert_raw_csv_to_structured_text(target_id)
                if structural_txt and structural_txt.exists():
                    target_id = str(structural_txt)
                    temporary_files_to_clean.append(structural_txt)

            raw_title = Path(target_id).stem if is_local else f"doc_{idx}"
            source_title = f"{client_str}_source_{NON_ALPHANUM_PATTERN.sub('', raw_title)}"

            time.sleep(random.uniform(1.0, 3.0))
            cmd = ["notebooklm", "--storage", str(client_storage), "source", "add", "--title", source_title, target_id]
            execute_with_backoff(cmd, client_token=client_str)

        update_dashboard(client_str, step="Ingestion Completed", progress=45, status="RUNNING")
        return "RUNNING"
    except Exception as e:
        update_dashboard(client_str, step="Phase 0 Ingestion Failure", progress=100, status="FAILED")
        raise e
    finally:
        for f in temporary_files_to_clean:
            if f.exists(): f.unlink()

def remove_duplicate_sources(client_str, shared_auth_path, nb_id):
    """Remove duplicate sources from NotebookLM workspace."""
    client_storage = SCRIPT_DIR / f".storage_{client_str}.json"
    try:
        if shared_auth_path.exists():
            client_storage.write_text(shared_auth_path.read_text())

        safe_auth_refresh(client_storage, client_str, min_interval=240.0)
        execute_with_backoff(["notebooklm", "--storage", str(client_storage), "use", nb_id, "--force"], client_token=client_str)

        res = execute_with_backoff(["notebooklm", "--storage", str(client_storage), "source", "list"], client_token=client_str)

        if not res or not res.stdout:
            return

        source_map = {}
        for line in res.stdout.splitlines():
            uuid_match = UUID_PATTERN.search(line)
            if uuid_match:
                source_id = uuid_match.group(1)
                title = line.replace(source_id, "").strip()
                for divider in ["│", "┃", "║", "  "]:
                    if divider in title:
                        parts = [p.strip() for p in title.split(divider) if p.strip()]
                        if parts:
                            title = " ".join(parts)
                            break

                title = title.strip()
                if title:
                    if title not in source_map:
                        source_map[title] = []
                    source_map[title].append(source_id)

        duplicates_removed = 0
        for title, source_ids in source_map.items():
            if len(source_ids) > 1:
                logging.info(f"[{client_str}] Found {len(source_ids)} duplicates of '{title}', removing {len(source_ids) - 1}")
                for dup_id in source_ids[1:]:
                    try:
                        execute_with_backoff(["notebooklm", "--storage", str(client_storage), "source", "remove", dup_id], client_token=client_str)
                        duplicates_removed += 1
                        time.sleep(random.uniform(1.0, 2.0))
                    except RuntimeError:
                        logging.warning(f"[{client_str}] Failed to remove duplicate source {dup_id}")

        if duplicates_removed > 0:
            logging.info(f"[{client_str}] Removed {duplicates_removed} duplicate sources")

    except Exception as e:
        logging.warning(f"[{client_str}] Duplicate removal failed: {e}")

def execute_ask_prompts_and_harvest(client_str, ask_prompt_files, shared_auth_path, nb_id):
    client_storage = SCRIPT_DIR / f".storage_{client_str}.json"
    name_value = getattr(config, f"{client_str}_name", f"UnknownClient-{client_str}")
    industry_value = getattr(config, f"{client_str}_industry", "")
    current_run_status = "RUNNING"
    try:
        if shared_auth_path.exists(): client_storage.write_text(shared_auth_path.read_text())
        safe_auth_refresh(client_storage, client_str, min_interval=240.0)
        execute_with_backoff(["notebooklm", "--storage", str(client_storage), "use", nb_id, "--force"], client_token=client_str)

        for p_idx, prompt_file in enumerate(ask_prompt_files):
            safe_auth_refresh(client_storage, client_str, min_interval=240.0)

            update_dashboard(client_str, step=f"Deep Research Queue: {prompt_file.name}", progress=50, status=current_run_status)

            updated_content = prompt_file.read_text().replace("$industry", industry_value).replace("$name", name_value)
            temp_prompt_carrier = SCRIPT_DIR / f".temp_ask_{client_str}_{prompt_file.name}"
            temp_prompt_carrier.write_text(updated_content, encoding="utf-8")

            last_response_obj = None

            if p_idx == 0:
                initial_cooldown = random.uniform(30.0, 60.0)
                logging.info(f"[{client_str}] Initial deep research cooldown: {initial_cooldown:.1f}s")
                time.sleep(initial_cooldown)

            logging.info(f"[{client_str}] Acquiring rate limit token...")
            deep_rate_limiter.acquire()
            logging.info(f"[{client_str}] Token acquired, executing deep research...")
            update_dashboard(client_str, step=f"Deep Processing: {prompt_file.name}", progress=55, status=current_run_status)

            cmd = ["notebooklm", "--storage", str(client_storage), "source", "add-research", "--prompt-file", str(temp_prompt_carrier.resolve()), "--mode", "deep"]

            try:
                last_response_obj = execute_with_backoff(
                    cmd,
                    client_token=client_str,
                    max_attempts=deep_config.MAX_RETRIES,
                    base_delay=deep_config.DEEP_RESEARCH_BASE_DELAY,
                    cmd_timeout=deep_config.DEEP_MODE_TIMEOUT
                )
            except RuntimeError as e:
                logging.error(f"[{client_str}] Failed to complete Deep Research prompt {prompt_file.name}. Error: {e}")
                current_run_status = "DEGRADED"

            cooldown_time = random.uniform(
                deep_config.DEEP_RESEARCH_COOLDOWN_MIN,
                deep_config.DEEP_RESEARCH_COOLDOWN_MAX
            )
            logging.info(f"[{client_str}] Deep research cooldown: {cooldown_time:.1f}s")
            time.sleep(cooldown_time)

            if last_response_obj and last_response_obj.stdout:
                discovered_citations = re.findall(r'(https?://[^\s>"\'<\(\)]+)', last_response_obj.stdout)
                if discovered_citations:
                    logging.info(f"[{client_str}] Discovered {len(set(discovered_citations))} potential citations")

                    try:
                        valid_citations = validate_and_filter_urls_sync(
                            list(set(discovered_citations)),
                            client_token=client_str,
                            timeout=5,
                            max_concurrent=10
                        )
                    except Exception as e:
                        logging.warning(f"[{client_str}] URL validation failed: {e}, using all discovered URLs")
                        valid_citations = list(set(discovered_citations))

                    valid_citations = valid_citations[:10]

                    safe_auth_refresh(client_storage, client_str, min_interval=240.0)

                    for c_idx, cited_url in enumerate(valid_citations):
                        try:
                            clean_url = cited_url.strip()
                            url_slug = NON_ALPHANUM_PATTERN.sub('', clean_url.split('//')[-1][:20])
                            harvested_title = f"verified_source_{p_idx}_{c_idx}_{url_slug}"

                            update_dashboard(client_str, step=f"Importing Citation {c_idx+1}/{len(valid_citations)}", progress=60, status=current_run_status)
                            import_cmd = ["notebooklm", "--storage", str(client_storage), "source", "add", "--title", harvested_title, clean_url]
                            execute_with_backoff(import_cmd, client_token=client_str)
                            logging.info(f"[{client_str}] Successfully added citation: {clean_url}")
                        except Exception as import_err:
                            logging.warning(f"[{client_str}] Failed to import validated URL {cited_url}: {str(import_err)}")

            if temp_prompt_carrier.exists(): temp_prompt_carrier.unlink()

        update_dashboard(client_str, step="Deep Ingestion Gated", progress=70, status=current_run_status)
        return current_run_status
    except Exception:
        update_dashboard(client_str, step="Phase 1 Ask Defect", progress=100, status="FAILED")
        return "FAILED"

def execute_chat_prompts(client_str, chat_prompt_files, shared_auth_path, nb_id, current_run_status):
    if current_run_status == "FAILED" or not chat_prompt_files:
        return current_run_status

    client_storage = SCRIPT_DIR / f".storage_{client_str}.json"
    name_value = getattr(config, f"{client_str}_name", f"UnknownClient-{client_str}")
    industry_value = getattr(config, f"{client_str}_industry", "")
    try:
        time.sleep(random.uniform(3.0, 8.0))
        if shared_auth_path.exists(): client_storage.write_text(shared_auth_path.read_text())
        safe_auth_refresh(client_storage, client_str, min_interval=240.0)
        execute_with_backoff(["notebooklm", "--storage", str(client_storage), "use", nb_id, "--force"], client_token=client_str)

        for p_idx, prompt_file in enumerate(chat_prompt_files):
            safe_auth_refresh(client_storage, client_str, min_interval=240.0)

            progress_calc = 70 + int((p_idx / len(chat_prompt_files)) * 15)
            update_dashboard(client_str, step=f"Structuring Note {p_idx+1}", progress=progress_calc, status=current_run_status)

            updated_content = prompt_file.read_text().replace("$industry", industry_value).replace("$name", name_value)
            temp_prompt_carrier = SCRIPT_DIR / f".temp_chat_{client_str}_{prompt_file.name}"
            temp_prompt_carrier.write_text(updated_content, encoding="utf-8")

            try:
                time.sleep(random.uniform(3.0, 6.0))
                cmd = ["notebooklm", "--storage", str(client_storage), "ask", "--prompt-file", str(temp_prompt_carrier.resolve()), "--save-as-note"]
                execute_with_backoff(cmd, client_token=client_str, base_delay=20.0)
            except RuntimeError:
                current_run_status = "DEGRADED"

            if temp_prompt_carrier.exists(): temp_prompt_carrier.unlink()

        update_dashboard(client_str, step="Prompts Finished", progress=85, status=current_run_status)
        return current_run_status
    except Exception:
        update_dashboard(client_str, step="Phase 2 Chat Defect", progress=100, status="FAILED")
        return "FAILED"

def post_process_and_generate_google_doc(client_str, shared_auth_path, nb_id, current_run_status):
    if current_run_status == "FAILED":
        return
    client_storage = SCRIPT_DIR / f".storage_{client_str}.json"
    human_name = getattr(config, f"{client_str}_name", client_str)
    clean_name_string = NON_ALPHANUM_PATTERN.sub('', human_name.replace(' ', ''))
    update_dashboard(client_str, step="Compiling Google Doc Layout...", progress=90, status="RUNNING")
    try:
        if shared_auth_path.exists(): client_storage.write_text(shared_auth_path.read_text())
        safe_auth_refresh(client_storage, client_str, min_interval=240.0)
        execute_with_backoff(["notebooklm", "--storage", str(client_storage), "use", nb_id, "--force"], client_token=client_str)

        notes_res = execute_with_backoff(["notebooklm", "--storage", str(client_storage), "note", "list"], client_token=client_str)
        compiled_sections = [f"<h1>Enterprise Cloud Account Strategic Plan: {human_name}</h1>", "<hr/>"]

        if notes_res and notes_res.stdout:
            for line in notes_res.stdout.splitlines():
                note_match = UUID_PATTERN.search(line)
                if note_match:
                    n_uuid = note_match.group(1)
                    note_data = execute_with_backoff(["notebooklm", "--storage", str(client_storage), "note", "show", n_uuid], client_token=client_str)
                    if note_data and note_data.stdout:
                        compiled_sections.append(note_data.stdout.strip())
                        compiled_sections.append("<hr/>")

        master_html_blob = "\n".join(compiled_sections)
        temp_html_carrier = SCRIPT_DIR / f"_temp_import_{clean_name_string}.html"
        temp_html_carrier.write_text(master_html_blob, encoding="utf-8")

        safe_auth_refresh(client_storage, client_str, min_interval=240.0)

        doc_title = f"Red Hat Strategic Plan - {human_name}"
        parent_folder_id = getattr(config, "GOOGLE_DRIVE_ROOT_FOLDER_ID", None)

        creds_path = client_storage
        if not creds_path.exists():
            logging.error(f"[{client_str}] Missing credentials for Google Doc generation")
            update_dashboard(client_str, step="Google Doc Error: Missing Creds", progress=100, status="DEGRADED")
            return

        credentials = Credentials.from_authorized_user_file(str(creds_path))
        drive_service = build('drive', 'v3', credentials=credentials)
        docs_service = build('docs', 'v1', credentials=credentials)

        file_metadata = {'name': doc_title, 'mimeType': 'application/vnd.google-apps.document'}
        if parent_folder_id:
            file_metadata['parents'] = [parent_folder_id]

        new_doc = drive_service.files().create(body=file_metadata, fields='id,webViewLink').execute()
        doc_id = new_doc.get('id')
        doc_link = new_doc.get('webViewLink', '#')

        requests_batch = [{'insertText': {'location': {'index': 1}, 'text': master_html_blob}}]
        docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': requests_batch}).execute()

        if temp_html_carrier.exists():
            temp_html_carrier.unlink()

        update_dashboard(client_str, step="Google Doc Created", progress=100, status="COMPLETE", plan_link=doc_link)
        logging.info(f"[{client_str}] ✅ Google Doc Published: {doc_link}")

    except Exception as e:
        update_dashboard(client_str, step="Google Doc Generation Failure", progress=100, status="DEGRADED")
        logging.error(f"[{client_str}] Google Doc generation failed: {str(e)}")

def execute_pipeline(client_str, ask_files, chat_files, shared_auth_store):
    global finished_pipelines_count, dashboard_lock

    logging.info(f"[{client_str}] Pipeline Initialization Started")

    try:
        provisioning_result = ensure_notebook_exists(client_str, shared_auth_store)
        if not provisioning_result:
            logging.info(f"[{client_str}] Pipeline skipped (disabled or no name)")
            if not DASHBOARD_MANAGER_AVAILABLE or not dashboard:
                with dashboard_lock:
                    finished_pipelines_count += 1
            else:
                dashboard.increment_finished()
            return

        _, _, nb_id = provisioning_result

        ingest_status = ingest_client_sources(client_str, shared_auth_store, nb_id)

        remove_duplicate_sources(client_str, shared_auth_store, nb_id)

        ask_status = execute_ask_prompts_and_harvest(client_str, ask_files, shared_auth_store, nb_id)
        chat_status = execute_chat_prompts(client_str, chat_files, shared_auth_store, nb_id, ask_status)
        post_process_and_generate_google_doc(client_str, shared_auth_store, nb_id, chat_status)

    except Exception as ex:
        logging.critical(f"[{client_str}] CRITICAL pipeline failure: {str(ex)}")
        update_dashboard(client_str, step="Critical Failure", progress=100, status="FAILED")
    finally:
        if DASHBOARD_MANAGER_AVAILABLE and dashboard:
            dashboard.increment_finished()
        else:
            with dashboard_lock:
                finished_pipelines_count += 1
        logging.info(f"[{client_str}] Pipeline Finalized")

def cleanup_old_session_storage():
    """Remove old session storage files to prevent unbounded growth"""
    if not deep_config.SESSION_CLEANUP_ENABLED:
        return

    try:
        import time
        cleaned = 0
        cutoff_time = time.time() - 300  

        for pattern in [".storage_*.json", ".temp_ask_*", ".temp_chat_*"]:
            for f in SCRIPT_DIR.glob(pattern):
                try:
                    if f.stat().st_mtime < cutoff_time:
                        f.unlink()
                        cleaned += 1
                except Exception as e:
                    logging.warning(f"Failed to cleanup {f}: {e}")

        if cleaned > 0:
            logging.info(f"Cleaned up {cleaned} old session files (>5 min old)")
    except Exception as e:
        logging.warning(f"Session cleanup failed: {e}")

def ensure_authentication():
    shared_auth_store = SCRIPT_DIR / ".shared_auth.json"
    default_auth = Path.home() / ".notebooklm" / "profiles" / "default" / "storage_state.json"

    def test_auth(auth_path):
        try:
            result = subprocess.run(
                ["notebooklm", "--storage", str(auth_path), "list"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if "expired" in result.stderr.lower() or "invalid" in result.stderr.lower() or "not logged in" in result.stdout.lower():
                return False
            return result.returncode == 0
        except Exception:
            return False

    if shared_auth_store.exists():
        logging.info(f"Found shared auth: {shared_auth_store}")
        if test_auth(shared_auth_store):
            logging.info("✅ Shared auth is valid")
            return shared_auth_store
        else:
            logging.warning("⚠️ Shared auth expired, will try default profile")
            shared_auth_store.unlink()  

    if default_auth.exists():
        logging.info(f"Checking default auth: {default_auth}")
        if test_auth(default_auth):
            logging.info(f"✅ Default auth is valid, copying to {shared_auth_store}")
            try:
                import shutil
                shutil.copy2(default_auth, shared_auth_store)
                print(f"✅ Using authenticated account from default profile\n")
                return shared_auth_store
            except Exception as e:
                logging.warning(f"Failed to copy default auth: {e}")
        else:
            logging.warning("⚠️ Default auth also expired")

    logging.info("No authentication found - initializing...")
    print("\n🔐 Authenticating with NotebookLM...")
    print("This will open your browser for authentication.\n")

    try:
        auth_cmd = ["notebooklm", "login"]
        result = subprocess.run(auth_cmd, check=False, text=True)

        if not default_auth.exists():
            logging.critical("Authentication failed or was cancelled.")
            print("\n❌ Authentication failed.")
            print("\nPlease authenticate manually by running:")
            print("  notebooklm login")
            sys.exit(1)

        import shutil
        shutil.copy2(default_auth, shared_auth_store)

        logging.info("✅ Authentication successful")
        print("\n✅ Authentication successful!\n")
        return shared_auth_store

    except Exception as e:
        logging.critical(f"Authentication error: {str(e)}")
        print(f"\n❌ Authentication error: {str(e)}")
        print("\nPlease authenticate manually by running:")
        print("  notebooklm login")
        sys.exit(1)

def log_performance_metrics():
    """Log final performance metrics for monitoring"""
    try:
        if DASHBOARD_MANAGER_AVAILABLE and dashboard:
            runtime = time.time() - dashboard.start_time
            state = dashboard.state
            total_count = dashboard.total_count
            finished_count = dashboard.finished_count
        else:
            runtime = time.time() - start_time_global
            state = dashboard_state
            total_count = total_pipelines_count
            finished_count = finished_pipelines_count

        failed_count = sum(1 for d in state.values() if d.get("status") == "FAILED")
        degraded_count = sum(1 for d in state.values() if d.get("status") == "DEGRADED")

        metrics = {
            "total_runtime_seconds": round(runtime, 2),
            "total_runtime_formatted": f"{int(runtime // 60)}m {int(runtime % 60)}s",
            "pipelines_total": total_count,
            "pipelines_completed": finished_count,
            "pipelines_failed": failed_count,
            "pipelines_degraded": degraded_count,
            "success_rate": round((finished_count - failed_count) / total_count * 100, 2) if total_count > 0 else 0
        }

        logging.info(f"PERFORMANCE_METRICS: {json.dumps(metrics, indent=2)}")
        return metrics
    except Exception as e:
        logging.warning(f"Failed to log metrics: {e}")
        return {}

def main():
    global total_pipelines_count
    signal.signal(signal.SIGINT, signal_handler)

    logging.info("=== RED HAT ACCOUNT PLANNING ENGINE - DEEP MODE EXECUTION (V3 OPTIMIZED) ===")
    logging.info(f"Configuration: rate_limit={deep_config.RATE_LIMIT_RPM} req/min, burst={deep_config.RATE_LIMIT_BURST}, workers={deep_config.MAX_WORKERS}")

    cleanup_old_session_storage()

    shared_auth_store = ensure_authentication()

    global auth_refresh_manager
    default_auth_path = Path.home() / ".notebooklm" / "profiles" / "default" / "storage_state.json"
    auth_refresh_manager = AuthRefreshManager(
        shared_auth_path=shared_auth_store,
        default_auth_path=default_auth_path,
        script_dir=SCRIPT_DIR,
        interval=300  
    )
    auth_refresh_manager.start()

    ask_prompt_files = sorted(SCRIPT_DIR.glob("ask_*.txt"))
    chat_prompt_files = sorted(SCRIPT_DIR.glob("chat_*.txt"))

    clients_list = getattr(config, "clients", [])
    if not clients_list:
        logging.critical("No clients defined in vars.py")
        sys.exit(1)

    if DASHBOARD_MANAGER_AVAILABLE and dashboard:
        dashboard.total_count = len(clients_list)
    else:
        global total_pipelines_count
        total_pipelines_count = len(clients_list)

    for client_token in clients_list:
        update_dashboard(client_token, step="Queued", progress=0, status="PENDING")

    if not DASHBOARD_MANAGER_AVAILABLE or not dashboard:
        ui_thread = threading.Thread(target=background_ui_manager, daemon=True, name="UI_Manager")
        ui_thread.start()

    try:
        webbrowser.open(DASHBOARD_PATH.as_uri())
        logging.info(f"Dashboard opened in browser: {DASHBOARD_PATH}")
    except Exception as e:
        logging.warning(f"Could not open dashboard in browser: {e}")

    with ThreadPoolExecutor(max_workers=deep_config.MAX_WORKERS, thread_name_prefix="Pipeline") as executor:
        futures = []
        for client_token in clients_list:
            future = executor.submit(execute_pipeline, client_token, ask_prompt_files, chat_prompt_files, shared_auth_store)
            futures.append(future)

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"Pipeline execution error: {str(e)}")

    if not DASHBOARD_MANAGER_AVAILABLE or not dashboard:
        ui_queue.put({"type": "shutdown"})
        if 'ui_thread' in locals():
            ui_thread.join(timeout=2.0)

    if auth_refresh_manager:
        auth_refresh_manager.stop()
        logging.info("Auth refresh manager stopped")

    metrics = log_performance_metrics()

    elapsed_total = time.time() - start_time_global
    minutes = int(elapsed_total // 60)
    seconds = int(elapsed_total % 60)

    logging.info(f"=== ALL PIPELINES COMPLETE - Total Runtime: {minutes}m {seconds}s ===")
    print(f"\n\n✅ All pipelines complete. Total runtime: {minutes}m {seconds}s")
    print(f"📊 Dashboard: file://{DASHBOARD_PATH}")
    if metrics:
        print(f"📈 Success Rate: {metrics.get('success_rate', 0)}%")
        print(f"   Completed: {metrics.get('pipelines_completed', 0)}/{metrics.get('pipelines_total', 0)}")
        if metrics.get('pipelines_failed', 0) > 0:
            print(f"   ⚠️  Failed: {metrics.get('pipelines_failed', 0)}")
        if metrics.get('pipelines_degraded', 0) > 0:
            print(f"   ⚠️  Degraded: {metrics.get('pipelines_degraded', 0)}")

if __name__ == "__main__":
    main()
