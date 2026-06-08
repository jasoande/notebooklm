#!/usr/bin/env python3
"""
Project APE - State Management
Persist pipeline state to enable resume from failures
"""
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


class PipelineState:
    """Thread-safe pipeline state manager with disk persistence."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.lock = threading.Lock()
        self.state: Dict[str, Dict] = {}
        self.load()

    def load(self) -> None:
        """Load state from disk if exists."""
        with self.lock:
            if self.state_file.exists():
                try:
                    self.state = json.loads(self.state_file.read_text())
                    logging.info(f"Loaded state from {self.state_file}")
                except Exception as e:
                    logging.warning(f"Failed to load state: {e}, starting fresh")
                    self.state = {}
            else:
                self.state = {}

    def save(self) -> None:
        """Save current state to disk atomically."""
        with self.lock:
            try:
                # Atomic write: write to temp file, then rename
                temp_file = self.state_file.with_suffix('.tmp')
                temp_file.write_text(json.dumps(self.state, indent=2))
                temp_file.replace(self.state_file)
            except Exception as e:
                logging.error(f"Failed to save state: {e}")

    def initialize_client(self, client_id: str, client_name: str) -> None:
        """Initialize state for a new client."""
        with self.lock:
            if client_id not in self.state:
                self.state[client_id] = {
                    "client_name": client_name,
                    "status": "pending",
                    "current_stage": None,
                    "notebook_id": None,
                    "start_time": datetime.utcnow().isoformat(),
                    "completed_steps": {},
                    "failed_steps": {},
                    "warnings": [],
                    "retry_count": 0,
                }
        self.save()

    def set_notebook_id(self, client_id: str, notebook_id: str) -> None:
        """Set notebook ID for client."""
        with self.lock:
            if client_id in self.state:
                self.state[client_id]["notebook_id"] = notebook_id
        self.save()

    def mark_step_started(self, client_id: str, step_name: str) -> None:
        """Mark a step as started."""
        with self.lock:
            if client_id in self.state:
                self.state[client_id]["current_stage"] = step_name
                self.state[client_id]["status"] = "in_progress"
        self.save()

    def mark_step_completed(
        self,
        client_id: str,
        step_name: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """Mark a step as successfully completed."""
        with self.lock:
            if client_id in self.state:
                self.state[client_id]["completed_steps"][step_name] = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "metadata": metadata or {}
                }
                # Remove from failed if it was there
                self.state[client_id]["failed_steps"].pop(step_name, None)
        self.save()

    def mark_step_failed(
        self,
        client_id: str,
        step_name: str,
        error: str,
        retry_count: int = 0
    ) -> None:
        """Mark a step as failed."""
        with self.lock:
            if client_id in self.state:
                self.state[client_id]["failed_steps"][step_name] = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "error": error,
                    "retry_count": retry_count
                }
                self.state[client_id]["retry_count"] = retry_count
        self.save()

    def add_warning(self, client_id: str, warning: str) -> None:
        """Add a quality warning."""
        with self.lock:
            if client_id in self.state:
                self.state[client_id]["warnings"].append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "message": warning
                })
        self.save()

    def mark_client_completed(self, client_id: str, final_status: str) -> None:
        """Mark entire client pipeline as completed."""
        with self.lock:
            if client_id in self.state:
                self.state[client_id]["status"] = final_status
                self.state[client_id]["end_time"] = datetime.utcnow().isoformat()
                self.state[client_id]["current_stage"] = None
        self.save()

    def is_step_completed(self, client_id: str, step_name: str) -> bool:
        """Check if a step has been completed."""
        with self.lock:
            return (
                client_id in self.state and
                step_name in self.state[client_id].get("completed_steps", {})
            )

    def get_completed_steps(self, client_id: str) -> List[str]:
        """Get list of completed step names for client."""
        with self.lock:
            if client_id in self.state:
                return list(self.state[client_id].get("completed_steps", {}).keys())
            return []

    def get_failed_steps(self, client_id: str) -> Dict[str, Any]:
        """Get failed steps with error details."""
        with self.lock:
            if client_id in self.state:
                return self.state[client_id].get("failed_steps", {})
            return {}

    def get_notebook_id(self, client_id: str) -> Optional[str]:
        """Get notebook ID if exists."""
        with self.lock:
            if client_id in self.state:
                return self.state[client_id].get("notebook_id")
            return None

    def get_resume_point(self, client_id: str) -> Optional[str]:
        """Determine where to resume from."""
        with self.lock:
            if client_id not in self.state:
                return None

            status = self.state[client_id].get("status")
            if status == "completed":
                return None  # Already done

            # If in progress, resume from current stage
            current_stage = self.state[client_id].get("current_stage")
            if current_stage:
                return current_stage

            # If has failures, resume from first failed step
            failed_steps = self.state[client_id].get("failed_steps", {})
            if failed_steps:
                return list(failed_steps.keys())[0]

            return None

    def get_client_summary(self, client_id: str) -> Dict:
        """Get full state summary for client."""
        with self.lock:
            return self.state.get(client_id, {})

    def get_all_clients(self) -> List[str]:
        """Get all client IDs in state."""
        with self.lock:
            return list(self.state.keys())

    def clear_client(self, client_id: str) -> None:
        """Remove client from state (for fresh restart)."""
        with self.lock:
            if client_id in self.state:
                del self.state[client_id]
        self.save()

    def print_summary(self) -> None:
        """Print human-readable state summary."""
        with self.lock:
            print("\n" + "=" * 71)
            print(" PIPELINE STATE SUMMARY")
            print("=" * 71)

            for client_id, data in self.state.items():
                status = data.get("status", "unknown")
                completed_count = len(data.get("completed_steps", {}))
                failed_count = len(data.get("failed_steps", {}))
                warnings_count = len(data.get("warnings", []))

                status_color = {
                    "completed": "\033[92m",
                    "in_progress": "\033[93m",
                    "failed": "\033[91m",
                }.get(status, "\033[90m")

                print(f"\n{data.get('client_name', client_id)}:")
                print(f"  Status: {status_color}{status.upper()}\033[0m")
                print(f"  Completed: {completed_count} steps")
                print(f"  Failed: {failed_count} steps")
                print(f"  Warnings: {warnings_count}")

                if data.get("current_stage"):
                    print(f"  Current: {data['current_stage']}")

                if failed_count > 0:
                    print(f"  Failed steps: {list(data.get('failed_steps', {}).keys())}")

            print("=" * 71 + "\n")


# Global state instance (initialized in main)
_state_instance: Optional[PipelineState] = None


def get_state() -> PipelineState:
    """Get global state instance."""
    global _state_instance
    if _state_instance is None:
        raise RuntimeError("State not initialized. Call init_state() first.")
    return _state_instance


def init_state(state_file: Path) -> PipelineState:
    """Initialize global state instance."""
    global _state_instance
    _state_instance = PipelineState(state_file)
    return _state_instance
