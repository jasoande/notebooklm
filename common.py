#!/usr/bin/env python3
"""
Project APE - Account Planning Engine
Common utilities and shared functionality for Fast and Deep processing modes
"""
import logging
import os
import queue
import re
import requests
import subprocess
import sys
import threading
import time
import random
from pathlib import Path
from typing import Dict, Optional, Tuple, Any, List
from urllib.parse import urlparse

# ==============================================================================
# PRE-COMPILED REGEX PATTERNS (Performance Optimization)
# ==============================================================================

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
SOURCES_PATTERN = re.compile(r'\b\d+\s+source(s)?\b', re.IGNORECASE)
DIVIDER_PATTERN = re.compile(r'│|┃|║|─|═|-|_|:|\+')
NON_ASCII_PATTERN = re.compile(r'[^\x00-\x7F]+')
DATE_PATTERN = re.compile(r'\d{4}-\d{2}-\d{2}|\d{2}:\d{2}|\b[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\b')
STATUS_KEYWORDS = re.compile(r'\b(ready|processing|waiting|status|uuid|title|created|owner)\b', re.IGNORECASE)
NON_ALPHANUM_PATTERN = re.compile(r'[^a-zA-Z0-9]')
UUID_PATTERN = re.compile(r'([a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12})', re.IGNORECASE)
THROTTLE_PATTERN = re.compile(
    r"quota|rate limit|exhausted|429|503|too many requests|resource_exhausted|rate limited|ratelimiterror|user_displayable_error",
    re.IGNORECASE
)


# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def log_subprocess_noise(client_token: str, stderr_content: str) -> None:
    """Parses and logs subprocess warnings/errors."""
    if not stderr_content:
        return
    for line in stderr_content.splitlines():
        line = line.strip()
        if not line or "rpc.decoder" in line or "Byte-count mismatch" in line:
            continue
        if "WARNING" in line or "ERROR" in line:
            logging.warning(f"[{client_token} Subprocess] {line}")
        else:
            logging.debug(f"[{client_token} Subprocess] {line}")


def normalize_name_string(text: str) -> str:
    """Normalize text for comparison by removing special chars, ANSI codes, etc."""
    if not text:
        return ""
    cleaned = ANSI_ESCAPE.sub('', text)
    cleaned = SOURCES_PATTERN.sub(' ', cleaned)
    cleaned = DIVIDER_PATTERN.sub(' ', cleaned)
    cleaned = NON_ASCII_PATTERN.sub(' ', cleaned)
    cleaned = DATE_PATTERN.sub(' ', cleaned)
    cleaned = STATUS_KEYWORDS.sub(' ', cleaned)
    return NON_ALPHANUM_PATTERN.sub('', cleaned).lower().strip()


def validate_url(url: str, timeout: int = 5) -> Tuple[bool, str]:
    """
    Validate URL is accessible before adding to NotebookLM.

    Returns:
        (is_valid, reason) - Boolean validity and reason string
    """
    try:
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
            'tracxn.com',           # Paywall site
            'pitchbook.com',        # Paywall site
            'fintechforum.de',      # Frequently broken
        ]

        url_lower = url.lower()
        for pattern in blocked_patterns:
            if pattern in url_lower:
                return False, f"Blocked pattern: {pattern}"

        # Check minimum URL length (prevent truncated URLs)
        if len(url) < 25:
            return False, "URL too short (likely truncated)"

        # Check for obviously truncated URLs (no file extension on paths that should have them)
        if '/edgar/data/' in url_lower and not url_lower.endswith(('.htm', '.html', '.txt', '.pdf', '.xml')):
            # SEC EDGAR URLs should have file extensions
            if url.count('/') > 6:  # Has deep path structure but no extension
                return False, "Truncated SEC EDGAR URL (missing file extension)"

        # Check for truncated AWS URLs
        if 'awsstatic.com/' in url_lower or 'amazonaws.com/' in url_lower:
            # AWS URLs ending with a single letter are likely truncated
            if url_lower.rstrip('/').endswith(tuple('/' + c for c in 'abcdefghijklmnopqrstuvwxyz')):
                return False, "Truncated AWS URL"

        # Parse URL to check structure
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False, "Invalid URL structure"

        # Only allow http/https
        if parsed.scheme not in ['http', 'https']:
            return False, f"Unsupported scheme: {parsed.scheme}"

        # HEAD request to check if URL is accessible
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; ProjectAPE/1.0; +https://redhat.com)'
        }

        response = requests.head(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers=headers
        )

        # Accept 200 OK
        if response.status_code == 200:
            return True, "OK"

        # 403 Forbidden means exists but blocked - skip it
        elif response.status_code == 403:
            return False, "Forbidden (likely requires authentication)"

        # 401 Unauthorized
        elif response.status_code == 401:
            return False, "Requires authentication"

        # 404 Not Found
        elif response.status_code == 404:
            return False, "404 Not Found"

        # 410 Gone
        elif response.status_code == 410:
            return False, "410 Gone (permanently deleted)"

        # 5xx Server Error
        elif response.status_code >= 500:
            return False, f"Server error: HTTP {response.status_code}"

        # Other status codes
        else:
            return False, f"HTTP {response.status_code}"

    except requests.Timeout:
        return False, "Request timeout"

    except requests.TooManyRedirects:
        return False, "Too many redirects"

    except requests.ConnectionError:
        return False, "Connection failed"

    except requests.RequestException as e:
        return False, f"Request error: {str(e)[:50]}"

    except Exception as e:
        return False, f"Validation error: {str(e)[:50]}"


def validate_and_filter_urls(urls: List[str], client_token: str = "Unknown") -> List[str]:
    """
    Validate a list of URLs and return only valid ones.

    Args:
        urls: List of URL strings to validate
        client_token: Client identifier for logging

    Returns:
        List of valid URLs
    """
    valid_urls = []

    for url in urls:
        # Clean URL
        clean_url = url.rstrip('.,;:)"\'')

        # Validate
        is_valid, reason = validate_url(clean_url)

        if is_valid:
            valid_urls.append(clean_url)
            logging.debug(f"[{client_token}] Valid URL: {clean_url}")
        else:
            logging.info(f"[{client_token}] Skipping invalid URL: {clean_url} - {reason}")

    logging.info(f"[{client_token}] Validated {len(valid_urls)}/{len(urls)} URLs")
    return valid_urls


def execute_with_backoff(
    cmd: list,
    client_token: str = "Orchestrator",
    input_data: Optional[str] = None,
    max_attempts: int = 3,
    base_delay: float = 3.0,  # OPTIMIZED: Reduced from 30.0 to 3.0 seconds
    cmd_timeout: float = 300.0
) -> subprocess.CompletedProcess:
    """
    Execute subprocess command with exponential backoff retry logic.

    Raises:
        RuntimeError: If all retry attempts are exhausted
    """
    last_res = None
    for attempt in range(max_attempts):
        try:
            logging.info(f"[{client_token}] Executing: {' '.join(cmd)}")
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

            # Check for rate limiting (need longer backoff)
            if THROTTLE_PATTERN.search(err_text) or THROTTLE_PATTERN.search(out_text):
                logging.warning(f"[{client_token}] Rate limit detected on attempt {attempt + 1}/{max_attempts}")
                if attempt < max_attempts - 1:
                    # Rate limits need longer delays
                    sleep_duration = (2 ** attempt * 10.0) + random.uniform(5.0, 10.0)
                    logging.info(f"[{client_token}] Backing off for {sleep_duration:.1f}s")
                    time.sleep(sleep_duration)
                    continue
                else:
                    break

            # Check for command failure
            if res.returncode != 0:
                logging.error(f"[{client_token}] Command failed with exit code {res.returncode}")
                if attempt < max_attempts - 1:
                    # OPTIMIZED: Faster retry for regular failures (3s base instead of 30s)
                    sleep_duration = (2 ** attempt * base_delay) + random.uniform(2.0, 5.0)
                    logging.info(f"[{client_token}] Retrying in {sleep_duration:.1f}s...")
                    time.sleep(sleep_duration)
                    continue
                else:
                    break

            return res  # Success

        except subprocess.TimeoutExpired:
            logging.critical(f"[{client_token}] Command timeout on attempt {attempt + 1}")
        except Exception as e:
            logging.warning(f"[{client_token}] Execution error on attempt {attempt + 1}: {str(e)}")

        if attempt < max_attempts - 1:
            sleep_duration = (2 ** attempt * base_delay) + random.uniform(2.0, 5.0)
            logging.info(f"[{client_token}] Retrying in {sleep_duration:.1f}s...")
            time.sleep(sleep_duration)

    error_msg = f"[{client_token}] Command exhausted {max_attempts} attempts: {' '.join(cmd)}"
    logging.critical(error_msg)
    raise RuntimeError(error_msg)


# ==============================================================================
# NOTEBOOKLM CLIENT
# ==============================================================================

class NotebookLMClient:
    """Manages NotebookLM authentication and operations."""

    def __init__(self, client_id: str, client_name: str, storage_dir: Path):
        self.client_id = client_id
        self.client_name = client_name
        self.storage_dir = storage_dir
        self._auth_lock = threading.Lock()
        self._last_auth_refresh = 0

    def get_storage_path(self, operation: str = "default") -> Path:
        """Get storage file path for specific operation."""
        return self.storage_dir / f".storage_{operation}_{self.client_id}.json"

    def safe_auth_refresh(self, storage_path: Path, min_interval: float = 120.0) -> None:
        """Refresh auth token with rate limiting."""
        with self._auth_lock:
            now = time.time()
            if now - self._last_auth_refresh > min_interval:
                try:
                    execute_with_backoff(
                        ["notebooklm", "--storage", str(storage_path), "auth", "refresh", "--quiet"],
                        client_token=self.client_id
                    )
                    self._last_auth_refresh = time.time()
                    logging.info(f"[{self.client_id}] Auth token refreshed")
                except RuntimeError:
                    logging.warning(f"[{self.client_id}] Auth refresh failed but continuing")
            else:
                logging.debug(f"[{self.client_id}] Auth refresh skipped (recent refresh)")

    def fetch_notebook_cache(self, storage_path: Optional[Path] = None) -> Dict[str, str]:
        """Fetch and parse notebook cache, returning normalized_name -> uuid mapping."""
        cmd = ["notebooklm"]
        if storage_path:
            cmd.extend(["--storage", str(storage_path)])
        cmd.append("list")

        try:
            res = execute_with_backoff(cmd, client_token=self.client_id)
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

                # Parse dividers
                for divider in ["│", "┃", "║", "  "]:
                    if divider in clean_name:
                        parts = [p.strip() for p in clean_name.split(divider) if p.strip()]
                        if parts:
                            clean_name = " ".join(parts)

                normalized_key = normalize_name_string(clean_name)
                if normalized_key:
                    cache[normalized_key] = nb_uuid

        logging.debug(f"[{self.client_id}] Cached {len(cache)} notebooks")
        return cache


# ==============================================================================
# DASHBOARD MANAGER
# ==============================================================================

class DashboardManager:
    """Manages real-time HTML dashboard and terminal UI."""

    def __init__(self, dashboard_path: Path, mode: str = "FAST"):
        self.dashboard_path = dashboard_path
        self.mode = mode.upper()
        self.state = {}
        self.lock = threading.Lock()
        self.console_lock = threading.Lock()
        self.start_time = time.time()
        self.finished_count = 0
        self.total_count = 0

    def update(
        self,
        client_token: str,
        client_name: str,
        step: Optional[str] = None,
        progress: Optional[int] = None,
        status: Optional[str] = None,
        **kwargs
    ) -> None:
        """Update dashboard state for a client."""
        with self.lock:
            if client_token not in self.state:
                self.state[client_token] = {
                    "name": client_name,
                    "step": "Initializing",
                    "progress": 0,
                    "status": "PENDING"
                }

            if step is not None:
                self.state[client_token]["step"] = step
            if progress is not None:
                self.state[client_token]["progress"] = progress
            if status is not None:
                self.state[client_token]["status"] = status

            # Store additional kwargs (e.g., notebook_id, plan_link)
            for key, value in kwargs.items():
                if value is not None:
                    self.state[client_token][key] = value

        self._write_html()
        self._update_terminal()

    def increment_finished(self) -> None:
        """Increment finished pipeline counter."""
        with self.lock:
            self.finished_count += 1
        self._update_terminal()

    def _get_timer_string(self) -> str:
        """Get formatted elapsed time."""
        elapsed = int(time.time() - self.start_time)
        minutes = elapsed // 60
        seconds = elapsed % 60
        return f"{minutes:02d}m {seconds:02d}s"

    def _update_terminal(self) -> None:
        """Update terminal UI with progress."""
        with self.console_lock:
            width = 30
            pct = int((self.finished_count / self.total_count) * 100) if self.total_count > 0 else 100
            filled = int(round(width * pct / 100))
            bar = '█' * filled + '░' * (width - filled)

            sys.stdout.write("\033[H\033[J")  # Clear screen
            sys.stdout.write("=" * 71 + "\n")
            sys.stdout.write(f" ⛭ \033[1mPROJECT APE — {self.mode} MODE CONSOLE\033[0m\n")
            sys.stdout.write("=" * 71 + "\n")
            sys.stdout.write(f" Progress: |\033[91m{bar}\033[0m| \033[92m{pct:>3}%\033[0m ({self.finished_count}/{self.total_count} Complete)\n")
            sys.stdout.write("-" * 71 + "\n")
            sys.stdout.write(f" {'WORKSPACE':<25} | {'PROGRESS':<10} | {'CURRENT PHASE':<30}\n")
            sys.stdout.write("-" * 71 + "\n")

            with self.lock:
                for token, data in self.state.items():
                    name_trunc = (data["name"][:22] + '...') if len(data["name"]) > 25 else data["name"]
                    status_color = {
                        "RUNNING": "\033[93m",
                        "DEGRADED": "\033[93m",
                        "COMPLETE": "\033[92m",
                        "FAILED": "\033[91m"
                    }.get(data["status"], "\033[90m")

                    step_trunc = (data["step"][:27] + '...') if len(data["step"]) > 30 else data["step"]
                    sys.stdout.write(f" {name_trunc:<25} | {status_color}{data['progress']:>3}%\033[0m      | {step_trunc:<30}\n")

            sys.stdout.write("=" * 71 + "\n")
            sys.stdout.flush()

    def _write_html(self) -> None:
        """Write HTML dashboard file."""
        timer = self._get_timer_string()
        mode_label = "Fast Mode" if self.mode == "FAST" else "Deep Mode"

        # Calculate statistics
        total = len(self.state)
        completed = sum(1 for d in self.state.values() if d.get("status") == "COMPLETE")
        running = sum(1 for d in self.state.values() if d.get("status") == "RUNNING")
        failed = sum(1 for d in self.state.values() if d.get("status") == "FAILED")
        pending = total - completed - running - failed

        # Calculate overall progress as average of all client progress percentages
        if total > 0:
            overall_progress = int(sum(d.get("progress", 0) for d in self.state.values()) / total)
        else:
            overall_progress = 0

        # Estimate time remaining - calculate based on running clients too
        if completed > 0:
            elapsed = time.time() - self.start_time
            avg_time = elapsed / completed
            remaining_count = total - completed
            eta_seconds = int(avg_time * remaining_count)
            eta_minutes = eta_seconds // 60
            eta_secs = eta_seconds % 60
            eta_str = f"{eta_minutes:02d}:{eta_secs:02d}"
        elif running > 0:
            # If nothing completed yet but things are running, countdown from expected time minus elapsed
            elapsed = time.time() - self.start_time
            avg_expected = 960  # 16 minutes in seconds (fast mode typical)
            eta_seconds = max(0, int(avg_expected - elapsed))
            eta_minutes = eta_seconds // 60
            eta_secs = eta_seconds % 60
            eta_str = f"{eta_minutes:02d}:{eta_secs:02d}"
        else:
            eta_seconds = 0
            eta_str = "--:--"

        with self.lock:
            html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Project APE - Account Planning Engine</title>
    <meta http-equiv="refresh" content="2">
    <script>
        // No timers - will show completion time at end
    </script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Red Hat Text", "Roboto", Arial, sans-serif;
            background: #0f1419;
            color: #e6edf3;
            line-height: 1.6;
        }}

        /* Header */
        /* Header */
        .header {{
            background: linear-gradient(135deg, #0a0d14 0%, #1a1f2e 50%, #0f1419 100%);
            border-bottom: 3px solid #ee0000;
            padding: 35px 60px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.6);
            position: relative;
        }}
        .header::after {{
            content: '';
            position: absolute;
            bottom: -3px;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, #ee0000 50%, transparent);
        }}
        .header-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 50px;
            margin-bottom: 20px;
        }}
        .logo-section {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        .logo {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        .title-container {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}
        .title-main {{
            font-size: 1.8rem;
            font-weight: 900;
            color: #fff;
            letter-spacing: 1px;
            text-shadow: 0 2px 10px rgba(238,0,0,0.4);
        }}
        .title-sub {{
            font-size: 0.95rem;
            color: #c0c8d0;
            font-weight: 400;
            letter-spacing: 1px;
            opacity: 0.85;
        }}
        .monkey-logo {{
            border: 2px solid #ee0000;
            box-shadow: 0 4px 12px rgba(238,0,0,0.3);
        }}
        .monkey-logo-right {{
            border: 3px solid #ee0000;
            box-shadow: 0 6px 16px rgba(238,0,0,0.4);
        }}
        .timer-box {{
            display: none;  /* Hidden - will show at end */
        }}
        .header-right {{
            text-align: right;
            display: flex;
            justify-content: flex-end;
            align-items: center;
        }}
        .redhat-logo {{
            height: 120px;
            width: auto;
            max-width: none;
            object-fit: contain;
            filter: drop-shadow(0 2px 6px rgba(0,0,0,0.3));
        }}

        /* Stats Bar */
        .stats-bar {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 8px;
            padding: 12px 16px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 2rem;
            font-weight: 800;
            line-height: 1;
            margin-bottom: 4px;
        }}
        .stat-label {{
            font-size: 0.75rem;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .stat-completed {{ color: #3fb950; }}
        .stat-running {{ color: #f0883e; }}
        .stat-failed {{ color: #f85149; }}
        .stat-pending {{ color: #58a6ff; }}

        /* Overall Progress */
        .overall-progress {{
            margin-top: 20px;
            padding: 20px;
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .overall-label {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 0.9rem;
            color: #8b949e;
        }}
        .progress-bar {{
            height: 24px;
            background: #161b22;
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid #30363d;
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.3);
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #3fb950 0%, #56d364 100%);
            transition: width 0.5s ease;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            padding-right: 10px;
            font-size: 0.75rem;
            font-weight: 700;
            color: #fff;
        }}

        /* Client Cards Grid */
        .container {{
            max-width: 1400px;
            margin: 30px auto;
            padding: 0 30px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
            gap: 20px;
        }}
        .card {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 10px;
            padding: 20px;
            transition: all 0.2s ease;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }}
        .card:hover {{
            border-color: #ee0000;
            box-shadow: 0 4px 16px rgba(238,0,0,0.2);
            transform: translateY(-2px);
        }}

        /* Card Header */
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid #30363d;
        }}
        .client-name {{
            font-size: 1.3rem;
            font-weight: 700;
            color: #fff;
            flex: 1;
        }}
        .status-pill {{
            font-size: 0.7rem;
            font-weight: 800;
            padding: 5px 12px;
            border-radius: 20px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            white-space: nowrap;
        }}
        .pill-RUNNING {{ background: rgba(240,136,62,0.2); color: #f0883e; border: 1px solid #f0883e; }}
        .pill-COMPLETE {{ background: rgba(63,185,80,0.2); color: #3fb950; border: 1px solid #3fb950; }}
        .pill-FAILED {{ background: rgba(248,81,73,0.2); color: #f85149; border: 1px solid #f85149; }}
        .pill-DEGRADED {{ background: rgba(240,136,62,0.2); color: #f0883e; border: 1px solid #f0883e; }}
        .pill-PENDING {{ background: rgba(88,166,255,0.2); color: #58a6ff; border: 1px solid #58a6ff; }}

        /* Progress Bar in Card */
        .card-progress {{
            margin: 16px 0;
        }}
        .card-progress-label {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 6px;
            font-size: 0.85rem;
        }}
        .progress-percentage {{
            font-weight: 700;
            color: #ee0000;
        }}
        .card-progress-bar {{
            height: 8px;
            background: #0d1117;
            border-radius: 4px;
            overflow: hidden;
        }}
        .card-progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #ee0000 0%, #ff4444 100%);
            transition: width 0.4s ease;
        }}

        /* Step Info */
        .step-info {{
            background: #0d1117;
            padding: 12px;
            border-radius: 6px;
            border: 1px solid #21262d;
            margin: 12px 0;
        }}
        .step-label {{
            font-size: 0.75rem;
            color: #8b949e;
            text-transform: uppercase;
            margin-bottom: 4px;
            letter-spacing: 0.5px;
        }}
        .step-text {{
            font-size: 0.95rem;
            color: #e6edf3;
            font-weight: 500;
        }}

        /* Metrics */
        .metrics {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
            margin-top: 12px;
        }}
        .metric {{
            background: #0d1117;
            padding: 8px 10px;
            border-radius: 4px;
            border: 1px solid #21262d;
            font-size: 0.8rem;
        }}
        .metric-label {{
            color: #8b949e;
            margin-right: 6px;
        }}
        .metric-value {{
            color: #e6edf3;
            font-weight: 600;
        }}

        /* Action Links */
        .actions {{
            display: flex;
            gap: 8px;
            margin-top: 16px;
        }}
        .btn {{
            flex: 1;
            display: block;
            background: #238636;
            color: #fff;
            text-decoration: none;
            padding: 10px 16px;
            font-size: 0.85rem;
            font-weight: 600;
            border-radius: 6px;
            text-align: center;
            transition: all 0.2s;
        }}
        .btn:hover {{
            background: #2ea043;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(35,134,54,0.3);
        }}
        .btn-secondary {{
            background: #21262d;
            color: #e6edf3;
        }}
        .btn-secondary:hover {{
            background: #30363d;
        }}

        /* Footer */
        .footer {{
            text-align: center;
            padding: 30px;
            color: #8b949e;
            font-size: 0.85rem;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-top">
            <div class="logo-section">
                <div class="logo">
                    <img src="data:image/png;base64,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" class="monkey-logo" class="monkey-logo" alt="Monkey" style="width: 60px; height: 60px; border-radius: 50%; object-fit: cover; margin-right: 15px;">
                    <div class="title-container">
                        <div class="title-main">Project APE - {mode_label}</div>
                        <div class="title-sub">Account Planning Engine</div>
                    </div>
                </div>
            </div>
            <div class="header-right">
            </div>
        </div>
        <div class="stats-bar">
            <div class="stat-card">
                <div class="stat-value stat-completed">{completed}</div>
                <div class="stat-label">Completed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value stat-running">{running}</div>
                <div class="stat-label">Running</div>
            </div>
            <div class="stat-card">
                <div class="stat-value stat-pending">{pending}</div>
                <div class="stat-label">Pending</div>
            </div>
            <div class="stat-card">
                <div class="stat-value stat-failed">{failed}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total}</div>
                <div class="stat-label">Total Clients</div>
            </div>
        </div>

        <div class="overall-progress">
            <div class="overall-label">
                <span>Overall Pipeline Progress</span>
                <span><strong>{completed}</strong> of <strong>{total}</strong> clients</span>
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {overall_progress}%;">
                    {overall_progress}%
                </div>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="grid">
"""

            for token, data in self.state.items():
                # Build metrics
                validation_score = data.get("validation_score", "N/A")
                notebook_id = data.get("notebook_id", "")
                nb_short = notebook_id[:8] + "..." if notebook_id else "Pending"

                # Build action buttons
                actions_html = ""
                if "notebook_id" in data and data["notebook_id"]:
                    url = f"https://notebooklm.google.com/notebook/{data['notebook_id']}"
                    actions_html = f'<a class="btn" href="{url}" target="_blank">📓 Open {data["name"]} NotebookLM</a>'
                if "plan_link" in data and data["plan_link"]:
                    actions_html += f'<a class="btn btn-secondary" href="{data["plan_link"]}" target="_blank">📄 View Plan</a>'

                if actions_html:
                    actions_html = f'<div class="actions">{actions_html}</div>'

                html += f"""
        <div class="card">
            <div class="card-header">
                <div class="client-name">{data["name"]}</div>
                <span class="status-pill pill-{data["status"]}">{data["status"]}</span>
            </div>

            <div class="card-progress">
                <div class="card-progress-label">
                    <span>Pipeline Progress</span>
                    <span class="progress-percentage">{data["progress"]}%</span>
                </div>
                <div class="card-progress-bar">
                    <div class="card-progress-fill" style="width: {data["progress"]}%;"></div>
                </div>
            </div>

            <div class="step-info">
                <div class="step-label">Current Phase</div>
                <div class="step-text">{data["step"]}</div>
            </div>

            <div class="metrics">
                <div class="metric">
                    <span class="metric-label">Notebook ID:</span>
                    <span class="metric-value">{nb_short}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Quality Score:</span>
                    <span class="metric-value">{validation_score}</span>
                </div>
            </div>

            {actions_html}
        </div>
"""

            html += """
        </div>
    </div>

    <div class="footer">
        Red Hat Account Planning Engine • Auto-refreshes every 2 seconds<br>
        Powered by NotebookLM AI • Generated with Claude Code
    </div>
</body>
</html>
"""

        try:
            tmp = self.dashboard_path.with_suffix(".tmp")
            tmp.write_text(html, encoding="utf-8")
            os.replace(str(tmp), str(self.dashboard_path))
        except IOError as e:
            logging.warning(f"Dashboard write failed: {e}")
