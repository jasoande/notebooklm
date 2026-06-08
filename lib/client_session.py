"""
Client Session Manager
Persistent session handling with storage reuse and per-client auth tracking
Eliminates storage file thrashing (create/delete cycles)
"""

import logging
import threading
import time
from pathlib import Path
from typing import Optional


class ClientSession:
    """
    Manages a persistent NotebookLM session for a single client.
    Eliminates storage file thrashing by reusing auth state throughout pipeline.
    """

    def __init__(
        self,
        client_id: str,
        client_name: str,
        shared_auth_path: Path,
        storage_dir: Path
    ):
        """
        Args:
            client_id: Unique client identifier
            client_name: Display name for client
            shared_auth_path: Path to shared authentication state
            storage_dir: Directory for storage files
        """
        self.client_id = client_id
        self.client_name = client_name
        self.storage_path = storage_dir / f".storage_{client_id}.json"
        self.notebook_id: Optional[str] = None

        # Per-client auth tracking (fixes race condition)
        self.last_auth_refresh = 0.0
        self.auth_lock = threading.Lock()

        self._initialized = False
        self._cleanup_done = False

        # Copy shared auth ONCE during initialization
        if shared_auth_path.exists():
            self.storage_path.write_text(shared_auth_path.read_text())
            logging.info(f"[{client_id}] Session initialized with auth from {shared_auth_path.name}")
        else:
            logging.warning(f"[{client_id}] Shared auth path not found: {shared_auth_path}")

    def get_storage_path(self) -> Path:
        """
        Get persistent storage path (no recreation).
        Storage file persists for entire pipeline lifecycle.

        Returns:
            Path to storage file
        """
        return self.storage_path

    def set_notebook_id(self, notebook_id: str) -> None:
        """
        Set notebook ID for this session.

        Args:
            notebook_id: NotebookLM notebook UUID
        """
        self.notebook_id = notebook_id
        logging.debug(f"[{self.client_id}] Notebook ID set: {notebook_id[:8]}...")

    def get_notebook_id(self) -> Optional[str]:
        """
        Get notebook ID for this session.

        Returns:
            Notebook UUID or None if not set
        """
        return self.notebook_id

    def safe_auth_refresh(self, min_interval: float = 240.0) -> bool:
        """
        Refresh auth token with configurable minimum interval.
        Uses PER-CLIENT tracking to avoid race conditions.

        Args:
            min_interval: Minimum seconds between refresh attempts (default 240s = 4min)

        Returns:
            True if refresh was performed, False if skipped
        """
        with self.auth_lock:
            now = time.time()
            elapsed = now - self.last_auth_refresh

            if elapsed > min_interval:
                # Need to refresh
                self.last_auth_refresh = now
                logging.info(f"[{self.client_id}] Auth refresh needed (last refresh {elapsed:.0f}s ago)")
                return True
            else:
                logging.debug(f"[{self.client_id}] Auth refresh skipped (last refresh {elapsed:.0f}s ago, min interval {min_interval:.0f}s)")
                return False

    def mark_auth_refreshed(self) -> None:
        """
        Mark auth as refreshed (called after successful refresh).
        Updates timestamp for rate limiting.
        """
        with self.auth_lock:
            self.last_auth_refresh = time.time()
            logging.debug(f"[{self.client_id}] Auth refresh timestamp updated")

    def cleanup(self) -> None:
        """
        Cleanup session storage file.
        Should be called ONCE at end of pipeline.
        """
        if self._cleanup_done:
            logging.debug(f"[{self.client_id}] Cleanup already done, skipping")
            return

        try:
            if self.storage_path.exists():
                self.storage_path.unlink()
                logging.info(f"[{self.client_id}] Session cleaned up (storage file deleted)")
                self._cleanup_done = True
        except Exception as e:
            logging.warning(f"[{self.client_id}] Cleanup failed: {e}")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - auto cleanup"""
        self.cleanup()

    def get_stats(self) -> dict:
        """
        Get session statistics.

        Returns:
            Dict with session stats
        """
        with self.auth_lock:
            time_since_refresh = time.time() - self.last_auth_refresh if self.last_auth_refresh > 0 else None

        return {
            'client_id': self.client_id,
            'client_name': self.client_name,
            'storage_path': str(self.storage_path),
            'notebook_id': self.notebook_id,
            'initialized': self._initialized,
            'cleanup_done': self._cleanup_done,
            'last_auth_refresh': self.last_auth_refresh,
            'time_since_refresh_seconds': time_since_refresh
        }


class SessionPool:
    """
    Manages multiple client sessions.
    Provides centralized session lifecycle management.
    """

    def __init__(self, storage_dir: Path):
        """
        Args:
            storage_dir: Directory for storage files
        """
        self.storage_dir = storage_dir
        self.sessions: dict[str, ClientSession] = {}
        self.lock = threading.Lock()

    def get_or_create_session(
        self,
        client_id: str,
        client_name: str,
        shared_auth_path: Path
    ) -> ClientSession:
        """
        Get existing session or create new one.

        Args:
            client_id: Client identifier
            client_name: Display name
            shared_auth_path: Path to shared auth

        Returns:
            ClientSession instance
        """
        with self.lock:
            if client_id not in self.sessions:
                session = ClientSession(
                    client_id,
                    client_name,
                    shared_auth_path,
                    self.storage_dir
                )
                self.sessions[client_id] = session
                logging.info(f"[SessionPool] Created new session for {client_id}")

            return self.sessions[client_id]

    def cleanup_all(self) -> None:
        """Cleanup all sessions"""
        with self.lock:
            for client_id, session in self.sessions.items():
                session.cleanup()

            self.sessions.clear()
            logging.info(f"[SessionPool] Cleaned up all sessions")

    def get_stats(self) -> dict:
        """Get pool statistics"""
        with self.lock:
            return {
                'total_sessions': len(self.sessions),
                'sessions': {cid: sess.get_stats() for cid, sess in self.sessions.items()}
            }
