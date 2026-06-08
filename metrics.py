#!/usr/bin/env python3
"""
Project APE - Metrics Tracking
Track and export execution statistics
"""
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class PromptMetrics:
    """Metrics for a single prompt execution."""
    prompt_id: str
    client_id: str
    start_time: str
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    retry_count: int = 0
    success: bool = False
    validation_score: Optional[float] = None
    validation_issues: int = 0
    output_words: int = 0
    citations_found: int = 0


@dataclass
class ClientMetrics:
    """Metrics for a complete client pipeline."""
    client_id: str
    client_name: str
    start_time: str
    status: str = "pending"  # success, failed, degraded, pending
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    prompts_succeeded: int = 0
    prompts_failed: int = 0
    prompts_degraded: int = 0
    total_llm_calls: int = 0
    total_retries: int = 0
    sources_ingested: int = 0
    avg_validation_score: Optional[float] = None


@dataclass
class PipelineMetrics:
    """Metrics for entire pipeline run."""
    run_id: str
    mode: str
    start_time: str
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    clients_total: int = 0
    clients_succeeded: int = 0
    clients_failed: int = 0
    clients_degraded: int = 0
    total_prompts_executed: int = 0
    total_llm_calls: int = 0
    total_retries: int = 0
    avg_validation_score: Optional[float] = None


class MetricsCollector:
    """Thread-safe metrics collection and export."""

    def __init__(self, metrics_file: Path, mode: str = "fast"):
        self.metrics_file = metrics_file
        self.mode = mode
        self.lock = threading.Lock()

        # Current run metrics
        self.run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.start_time = datetime.utcnow()
        self.client_metrics: Dict[str, ClientMetrics] = {}
        self.prompt_metrics: List[PromptMetrics] = []

        # Runtime counters
        self.llm_call_count = 0
        self.retry_count = 0

    def start_client(self, client_id: str, client_name: str):
        """Initialize metrics for client."""
        with self.lock:
            self.client_metrics[client_id] = ClientMetrics(
                client_id=client_id,
                client_name=client_name,
                start_time=datetime.utcnow().isoformat(),
                status="in_progress"
            )

    def end_client(self, client_id: str, status: str):
        """Finalize client metrics."""
        with self.lock:
            if client_id in self.client_metrics:
                cm = self.client_metrics[client_id]
                cm.end_time = datetime.utcnow().isoformat()
                cm.status = status

                # Calculate duration
                if cm.start_time:
                    start = datetime.fromisoformat(cm.start_time)
                    end = datetime.fromisoformat(cm.end_time)
                    cm.duration_seconds = (end - start).total_seconds()

                # Calculate average validation score
                client_prompts = [p for p in self.prompt_metrics if p.client_id == client_id]
                valid_scores = [p.validation_score for p in client_prompts if p.validation_score is not None]
                if valid_scores:
                    cm.avg_validation_score = sum(valid_scores) / len(valid_scores)

    def record_prompt_start(self, client_id: str, prompt_id: str) -> PromptMetrics:
        """Start tracking prompt execution."""
        with self.lock:
            pm = PromptMetrics(
                prompt_id=prompt_id,
                client_id=client_id,
                start_time=datetime.utcnow().isoformat()
            )
            self.prompt_metrics.append(pm)
            return pm

    def record_prompt_end(
        self,
        prompt_metric: PromptMetrics,
        success: bool,
        validation_score: Optional[float] = None,
        validation_issues: int = 0,
        output_words: int = 0,
        citations: int = 0,
        retry_count: int = 0
    ):
        """Finalize prompt metrics."""
        with self.lock:
            prompt_metric.end_time = datetime.utcnow().isoformat()
            prompt_metric.success = success
            prompt_metric.validation_score = validation_score
            prompt_metric.validation_issues = validation_issues
            prompt_metric.output_words = output_words
            prompt_metric.citations_found = citations
            prompt_metric.retry_count = retry_count

            # Calculate duration
            start = datetime.fromisoformat(prompt_metric.start_time)
            end = datetime.fromisoformat(prompt_metric.end_time)
            prompt_metric.duration_seconds = (end - start).total_seconds()

            # Update client metrics
            if prompt_metric.client_id in self.client_metrics:
                cm = self.client_metrics[prompt_metric.client_id]
                if success:
                    if validation_score and validation_score < 7.0:
                        cm.prompts_degraded += 1
                    else:
                        cm.prompts_succeeded += 1
                else:
                    cm.prompts_failed += 1
                cm.total_retries += retry_count

    def increment_llm_calls(self, count: int = 1):
        """Increment LLM API call counter."""
        with self.lock:
            self.llm_call_count += count

    def increment_retries(self, count: int = 1):
        """Increment retry counter."""
        with self.lock:
            self.retry_count += count

    def record_sources_ingested(self, client_id: str, count: int):
        """Record number of sources ingested for client."""
        with self.lock:
            if client_id in self.client_metrics:
                self.client_metrics[client_id].sources_ingested = count

    def export(self):
        """Export metrics to JSON file."""
        with self.lock:
            end_time = datetime.utcnow()
            duration = (end_time - self.start_time).total_seconds()

            # Calculate aggregate stats
            validation_scores = [
                p.validation_score for p in self.prompt_metrics
                if p.validation_score is not None
            ]
            avg_validation = sum(validation_scores) / len(validation_scores) if validation_scores else None

            # Count client statuses
            succeeded = sum(1 for c in self.client_metrics.values() if c.status == "success")
            failed = sum(1 for c in self.client_metrics.values() if c.status == "failed")
            degraded = sum(1 for c in self.client_metrics.values() if c.status == "degraded")

            # Build pipeline metrics
            pipeline = PipelineMetrics(
                run_id=self.run_id,
                mode=self.mode,
                start_time=self.start_time.isoformat(),
                end_time=end_time.isoformat(),
                duration_seconds=duration,
                clients_total=len(self.client_metrics),
                clients_succeeded=succeeded,
                clients_failed=failed,
                clients_degraded=degraded,
                total_prompts_executed=len(self.prompt_metrics),
                total_llm_calls=self.llm_call_count,
                total_retries=self.retry_count,
                avg_validation_score=avg_validation
            )

            # Export to JSON
            metrics_data = {
                "pipeline": asdict(pipeline),
                "clients": {cid: asdict(cm) for cid, cm in self.client_metrics.items()},
                "prompts": [asdict(pm) for pm in self.prompt_metrics]
            }

            try:
                # Atomic write
                temp_file = self.metrics_file.with_suffix('.tmp')
                temp_file.write_text(json.dumps(metrics_data, indent=2))
                temp_file.replace(self.metrics_file)
                logging.info(f"Metrics exported to {self.metrics_file}")
            except Exception as e:
                logging.error(f"Failed to export metrics: {e}")

    def print_summary(self):
        """Print human-readable metrics summary."""
        with self.lock:
            end_time = datetime.utcnow()
            duration = (end_time - self.start_time).total_seconds()
            minutes = int(duration // 60)
            seconds = int(duration % 60)

            succeeded = sum(1 for c in self.client_metrics.values() if c.status == "success")
            failed = sum(1 for c in self.client_metrics.values() if c.status == "failed")
            degraded = sum(1 for c in self.client_metrics.values() if c.status == "degraded")

            validation_scores = [
                p.validation_score for p in self.prompt_metrics
                if p.validation_score is not None
            ]
            avg_validation = sum(validation_scores) / len(validation_scores) if validation_scores else 0

            print("\n" + "=" * 71)
            print(f" METRICS SUMMARY - {self.mode.upper()} MODE")
            print("=" * 71)
            print(f" Run ID: {self.run_id}")
            print(f" Duration: {minutes}m {seconds}s")
            print(f" Clients: {len(self.client_metrics)} total")
            print(f"   ✓ Succeeded: {succeeded}")
            print(f"   ⚠ Degraded: {degraded}")
            print(f"   ✗ Failed: {failed}")
            print(f" Prompts Executed: {len(self.prompt_metrics)}")
            print(f" LLM API Calls: {self.llm_call_count}")
            print(f" Retries: {self.retry_count}")
            print(f" Avg Validation Score: {avg_validation:.1f}/10.0")
            print("=" * 71)

            # Per-client breakdown
            print(f"\n {'CLIENT':<25} | {'STATUS':<10} | {'DURATION':<10} | {'SCORE':<8}")
            print("-" * 71)
            for cid, cm in self.client_metrics.items():
                duration_str = f"{int(cm.duration_seconds or 0)}s" if cm.duration_seconds else "N/A"
                score_str = f"{cm.avg_validation_score:.1f}" if cm.avg_validation_score else "N/A"

                status_color = {
                    "success": "\033[92m",
                    "degraded": "\033[93m",
                    "failed": "\033[91m",
                }.get(cm.status, "\033[90m")

                print(f" {cm.client_name:<25} | {status_color}{cm.status.upper():<10}\033[0m | {duration_str:<10} | {score_str:<8}")

            print("=" * 71 + "\n")


# Global metrics instance
_metrics_instance: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Get global metrics instance."""
    global _metrics_instance
    if _metrics_instance is None:
        raise RuntimeError("Metrics not initialized. Call init_metrics() first.")
    return _metrics_instance


def init_metrics(metrics_file: Path, mode: str = "fast") -> MetricsCollector:
    """Initialize global metrics instance."""
    global _metrics_instance
    _metrics_instance = MetricsCollector(metrics_file, mode)
    return _metrics_instance
