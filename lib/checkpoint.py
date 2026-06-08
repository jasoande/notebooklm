"""
Checkpoint Manager for Pipeline Resumability
Allows pipelines to resume from failure points
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


class CheckpointManager:
    """
    Manages pipeline checkpoints for resumability
    Tracks progress and enables recovery from failures
    """

    def __init__(
        self,
        checkpoint_dir: Path,
        enabled: bool = True,
        cleanup_on_success: bool = True,
        retain_failed: bool = True
    ):
        """
        Args:
            checkpoint_dir: Directory for checkpoint files
            enabled: Enable checkpointing
            cleanup_on_success: Remove checkpoint on successful completion
            retain_failed: Keep failed checkpoints for debugging
        """
        self.checkpoint_dir = checkpoint_dir
        self.enabled = enabled
        self.cleanup_on_success = cleanup_on_success
        self.retain_failed = retain_failed

        if enabled:
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
            logging.info(f"Checkpoint manager initialized: {checkpoint_dir}")

    def get_checkpoint_path(self, client_id: str) -> Path:
        """Get checkpoint file path for client"""
        return self.checkpoint_dir / f"{client_id}.checkpoint.json"

    def load(self, client_id: str) -> Dict[str, Any]:
        """
        Load checkpoint for client

        Args:
            client_id: Client identifier

        Returns:
            Checkpoint data or empty dict
        """
        if not self.enabled:
            return {}

        checkpoint_path = self.get_checkpoint_path(client_id)

        if not checkpoint_path.exists():
            return {}

        try:
            with open(checkpoint_path, 'r') as f:
                checkpoint = json.load(f)

            logging.info(
                f"[{client_id}] Loaded checkpoint from phase {checkpoint.get('phase', 0)}"
            )
            return checkpoint

        except Exception as e:
            logging.error(f"[{client_id}] Failed to load checkpoint: {e}")
            return {}

    def save(
        self,
        client_id: str,
        phase: int,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Save checkpoint for client

        Args:
            client_id: Client identifier
            phase: Current phase number
            data: Additional checkpoint data
        """
        if not self.enabled:
            return

        checkpoint_path = self.get_checkpoint_path(client_id)

        checkpoint = {
            'client_id': client_id,
            'phase': phase,
            'timestamp': datetime.now().isoformat(),
            'data': data or {}
        }

        try:
            with open(checkpoint_path, 'w') as f:
                json.dump(checkpoint, f, indent=2)

            logging.debug(f"[{client_id}] Saved checkpoint at phase {phase}")

        except Exception as e:
            logging.error(f"[{client_id}] Failed to save checkpoint: {e}")

    def update(
        self,
        client_id: str,
        updates: Dict[str, Any]
    ) -> None:
        """
        Update checkpoint with additional data

        Args:
            client_id: Client identifier
            updates: Data to merge into checkpoint
        """
        if not self.enabled:
            return

        checkpoint = self.load(client_id)
        checkpoint.update(updates)
        checkpoint['timestamp'] = datetime.now().isoformat()

        checkpoint_path = self.get_checkpoint_path(client_id)

        try:
            with open(checkpoint_path, 'w') as f:
                json.dump(checkpoint, f, indent=2)

            logging.debug(f"[{client_id}] Updated checkpoint")

        except Exception as e:
            logging.error(f"[{client_id}] Failed to update checkpoint: {e}")

    def complete(self, client_id: str, success: bool = True) -> None:
        """
        Mark pipeline complete and optionally cleanup

        Args:
            client_id: Client identifier
            success: Whether pipeline succeeded
        """
        if not self.enabled:
            return

        checkpoint_path = self.get_checkpoint_path(client_id)

        if not checkpoint_path.exists():
            return

        if success and self.cleanup_on_success:
            try:
                checkpoint_path.unlink()
                logging.info(f"[{client_id}] Checkpoint cleaned up after success")
            except Exception as e:
                logging.warning(f"[{client_id}] Failed to cleanup checkpoint: {e}")

        elif not success and not self.retain_failed:
            try:
                checkpoint_path.unlink()
                logging.info(f"[{client_id}] Failed checkpoint removed")
            except Exception as e:
                logging.warning(f"[{client_id}] Failed to remove checkpoint: {e}")

        else:
            # Mark as complete in checkpoint file
            checkpoint = self.load(client_id)
            checkpoint['completed'] = True
            checkpoint['success'] = success
            checkpoint['completion_time'] = datetime.now().isoformat()

            try:
                with open(checkpoint_path, 'w') as f:
                    json.dump(checkpoint, f, indent=2)

                status = "succeeded" if success else "failed"
                logging.info(f"[{client_id}] Checkpoint marked as {status}")

            except Exception as e:
                logging.error(f"[{client_id}] Failed to mark checkpoint complete: {e}")

    def list_checkpoints(self) -> list:
        """
        List all existing checkpoints

        Returns:
            List of checkpoint info dicts
        """
        if not self.enabled:
            return []

        checkpoints = []

        for checkpoint_file in self.checkpoint_dir.glob("*.checkpoint.json"):
            try:
                with open(checkpoint_file, 'r') as f:
                    checkpoint = json.load(f)
                    checkpoints.append({
                        'client_id': checkpoint.get('client_id'),
                        'phase': checkpoint.get('phase'),
                        'timestamp': checkpoint.get('timestamp'),
                        'completed': checkpoint.get('completed', False),
                        'success': checkpoint.get('success', None)
                    })
            except Exception as e:
                logging.warning(f"Failed to read checkpoint {checkpoint_file}: {e}")

        return checkpoints

    def cleanup_all(self, completed_only: bool = True) -> int:
        """
        Cleanup checkpoint files

        Args:
            completed_only: Only remove completed checkpoints

        Returns:
            Number of files removed
        """
        if not self.enabled:
            return 0

        removed = 0

        for checkpoint_file in self.checkpoint_dir.glob("*.checkpoint.json"):
            try:
                if completed_only:
                    with open(checkpoint_file, 'r') as f:
                        checkpoint = json.load(f)
                        if not checkpoint.get('completed', False):
                            continue

                checkpoint_file.unlink()
                removed += 1

            except Exception as e:
                logging.warning(f"Failed to cleanup {checkpoint_file}: {e}")

        if removed > 0:
            logging.info(f"Cleaned up {removed} checkpoint files")

        return removed
