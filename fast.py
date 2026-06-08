#!/usr/bin/env python3
"""
Project APE - Account Planning Engine
Fast Mode: High-throughput processing with concurrent pipeline execution

Quick Wins Implemented:
- State persistence with --resume flag
- Output validation framework
- Metrics tracking and export
- Prompt metadata parsing
"""
import argparse
import csv
import glob
import logging
import os
import re
import signal
import subprocess
import sys
import time
import random
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Import shared utilities
from common import (
    NotebookLMClient,
    DashboardManager,
    execute_with_backoff,
    log_subprocess_noise,
    normalize_name_string,
    validate_and_filter_urls,
    UUID_PATTERN,
    NON_ALPHANUM_PATTERN,
)
from state_manager import init_state, get_state
from validators import validate_output
from metrics import init_metrics, get_metrics

# ==============================================================================
# CONFIGURATION & SETUP
# ==============================================================================

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.append(str(SCRIPT_DIR))

try:
    import vars as config
except ImportError:
    print(f"Error: Could not find vars.py in {SCRIPT_DIR}", file=sys.stderr)
    sys.exit(1)

# Configuration
LOG_FILE_PATH = PROJECT_ROOT / getattr(config, "LOG_FILE_NAME", "project_ape_execution.log")
DASHBOARD_PATH = SCRIPT_DIR / getattr(config, "DASHBOARD_NAME", "project_ape_dashboard.html")
STATE_FILE = SCRIPT_DIR / "pipeline_state.json"
METRICS_FILE = SCRIPT_DIR / "pipeline_metrics.json"
MAX_WORKERS = getattr(config, "FAST_MODE_MAX_WORKERS", 8)
TIMINGS = getattr(config, "TIMINGS", {})
RETRY_CONFIG = getattr(config, "RETRY_CONFIG", {})

# Setup logging
LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, mode="w", encoding="utf-8")
    ]
)

# Global dashboard manager
dashboard = DashboardManager(DASHBOARD_PATH, mode="FAST")

# Global shutdown flag
shutdown_event = threading.Event()

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    print("\n\n⚠️  Interrupt received! Shutting down gracefully...")
    print("Stopping running tasks and cleaning up...")
    shutdown_event.set()
    logging.info("SHUTDOWN: User interrupt received")
    sys.exit(0)

# ==============================================================================
# CONFIGURATION VALIDATION
# ==============================================================================

def validate_configuration():
    """Validate vars.py configuration on startup."""
    if not getattr(config, "VALIDATE_CONFIG_ON_STARTUP", True):
        return

    clients = getattr(config, "clients", [])
    if not clients:
        print("Error: No clients configured in vars.py", file=sys.stderr)
        sys.exit(1)

    required_attrs = getattr(config, "REQUIRED_CLIENT_ATTRS", ["name", "industry", "folder"])

    for client in clients:
        client_id = client.split('.')[-1].strip() if '.' in client else client.strip()
        for attr in required_attrs:
            attr_name = f"{client_id}_{attr}"
            if not hasattr(config, attr_name):
                print(f"Error: Missing required attribute '{attr_name}' in vars.py", file=sys.stderr)
                sys.exit(1)

    logging.info("Configuration validation passed")


# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def convert_csv_to_structured_text(csv_path: Path) -> Path:
    """Convert CSV to structured text format for better LLM parsing."""
    try:
        txt_output_path = csv_path.with_suffix('.txt')
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
        logging.info(f"Converted CSV to structured text: {txt_output_path}")
        return txt_output_path
    except Exception as e:
        logging.error(f"CSV conversion failed for {csv_path}: {e}")
        return None


# ==============================================================================
# PIPELINE STAGES
# ==============================================================================

def ensure_notebook_exists(client_id: str, client_name: str, shared_auth_path: Path) -> tuple:
    """Ensure NotebookLM workspace exists, create if needed."""
    state = get_state()
    metrics = get_metrics()

    # Check if already completed
    if state.is_step_completed(client_id, "notebook_creation"):
        existing_id = state.get_notebook_id(client_id)
        logging.info(f"[{client_id}] Using existing notebook: {existing_id}")
        return client_id, client_name, existing_id

    state.mark_step_started(client_id, "notebook_creation")
    nb_client = NotebookLMClient(client_id, client_name, SCRIPT_DIR)
    storage_path = nb_client.get_storage_path("default")

    dashboard.update(client_id, client_name, step="Pre-flight verification", progress=5, status="RUNNING")

    try:
        # Copy shared auth
        if shared_auth_path.exists():
            storage_path.write_text(shared_auth_path.read_text())

        if not client_name:
            dashboard.update(client_id, client_name, step="Skipped (no name configured)", progress=0, status="PENDING")
            return None

        # Refresh auth
        nb_client.safe_auth_refresh(storage_path)
        metrics.increment_llm_calls()

        # Check cache for existing notebook
        notebook_cache = nb_client.fetch_notebook_cache(storage_path)
        normalized_target = normalize_name_string(client_name)

        # First check for exact match
        nb_id = notebook_cache.get(normalized_target)

        if not nb_id:
            # Check if ANY notebook matches this client name (prevent duplicates)
            # List all notebooks and check their actual titles
            list_res = execute_with_backoff(
                ["notebooklm", "--storage", str(storage_path), "list"],
                client_token=client_id
            )

            # Parse the list output to find exact title matches
            if list_res and list_res.returncode == 0:
                for line in list_res.stdout.splitlines():
                    # Check if this line contains the client name exactly
                    if client_name in line or f"{client_name} Test" in line:
                        uuid_match = UUID_PATTERN.search(line)
                        if uuid_match:
                            nb_id = uuid_match.group(1)
                            logging.info(f"[{client_id}] Found existing notebook with matching title: {nb_id}")
                            break

        if not nb_id:
            # Fuzzy match as fallback
            for cached_key, cached_uuid in notebook_cache.items():
                if normalized_target in cached_key or cached_key in normalized_target:
                    nb_id = cached_uuid
                    logging.info(f"[{client_id}] Found existing notebook via fuzzy match: {nb_id}")
                    break

        if not nb_id:
            # Create new notebook ONLY if none found
            logging.info(f"[{client_id}] No existing notebook found - creating new one: {client_name}")
            time.sleep(random.uniform(1.0, 2.0))  # OPTIMIZED: Reduced from 2-4s to 1-2s
            cmd = ["notebooklm", "--storage", str(storage_path), "create", client_name]
            res = execute_with_backoff(
                cmd,
                client_token=client_id,
                max_attempts=RETRY_CONFIG.get('max_attempts', 3),
                base_delay=RETRY_CONFIG.get('base_delay', 3.0)  # OPTIMIZED: Changed default from 30.0 to 3.0
            )
            metrics.increment_llm_calls()
            uuid_match = UUID_PATTERN.search(res.stdout if res else "")
            nb_id = uuid_match.group(1) if uuid_match else None

            if not nb_id:
                # Retry cache fetch
                time.sleep(2.0)
                notebook_cache = nb_client.fetch_notebook_cache(storage_path)
                nb_id = notebook_cache.get(normalized_target)
        else:
            logging.info(f"[{client_id}] Reusing existing notebook: {nb_id}")

        if not nb_id:
            raise Exception(f"Failed to create/find notebook: {client_name}")

        state.set_notebook_id(client_id, nb_id)
        state.mark_step_completed(client_id, "notebook_creation", {"notebook_id": nb_id})

        dashboard.update(
            client_id,
            client_name,
            step="Workspace Active",
            progress=15,
            status="RUNNING",
            notebook_id=nb_id
        )
        logging.info(f"[{client_id}] Notebook ready: {nb_id}")
        return client_id, client_name, nb_id

    except Exception as e:
        logging.error(f"[{client_id}] Notebook setup failed: {e}")
        state.mark_step_failed(client_id, "notebook_creation", str(e))
        dashboard.update(client_id, client_name, step="Pre-flight error", progress=100, status="FAILED")
        raise e
    finally:
        # Keep storage file to maintain auth across all operations for this client
        pass
        # if storage_path.exists():
        #     storage_path.unlink()


def ingest_sources(client_id: str, client_name: str, shared_auth_path: Path, nb_id: str):
    """
    Ingest consolidated PDF into NotebookLM workspace.

    New approach: Convert all files to PDFs, concatenate into {client_id}-One.pdf,
    then upload only that single consolidated PDF.
    """
    state = get_state()
    metrics = get_metrics()
    nb_client = NotebookLMClient(client_id, client_name, SCRIPT_DIR)

    # Check if already completed
    if state.is_step_completed(client_id, "source_ingestion"):
        logging.info(f"[{client_id}] Source ingestion already completed")
        return

    state.mark_step_started(client_id, "source_ingestion")
    storage_path = SCRIPT_DIR / f".storage_{client_id}.json"

    dashboard.update(client_id, client_name, step="Phase 0: PDF Consolidation", progress=15, status="RUNNING")

    try:
        if shared_auth_path.exists():
            storage_path.write_text(shared_auth_path.read_text())

        # Refresh auth before ingestion
        nb_client.safe_auth_refresh(storage_path, min_interval=60.0)

        # Use notebook
        execute_with_backoff(
            ["notebooklm", "--storage", str(storage_path), "use", nb_id, "--force"],
            client_token=client_id
        )

        # Get client folder
        folder_raw = getattr(config, f"{client_id}_folder", ".")
        folder_path = Path(PROJECT_ROOT / folder_raw).resolve()

        if not folder_path.exists():
            logging.error(f"[{client_id}] Folder not found: {folder_path}")
            dashboard.update(client_id, client_name, step="Folder not found", progress=45, status="FAILED")
            state.mark_step_failed(client_id, "source_ingestion", "Folder not found")
            return

        # Check if consolidated PDF already exists
        consolidated_pdf = folder_path / f"{client_id}-One.pdf"

        if not consolidated_pdf.exists():
            logging.info(f"[{client_id}] Consolidated PDF not found, creating...")
            dashboard.update(client_id, client_name, step="Converting files to PDF", progress=20, status="RUNNING")

            # Import and use PDF consolidator
            from pdf_consolidator import consolidate_client_pdfs

            success, pdf_path = consolidate_client_pdfs(client_id, str(folder_path))

            if not success or not pdf_path or not pdf_path.exists():
                logging.error(f"[{client_id}] PDF consolidation failed")
                dashboard.update(client_id, client_name, step="PDF consolidation failed", progress=45, status="FAILED")
                state.mark_step_failed(client_id, "source_ingestion", "PDF consolidation failed")
                return

            consolidated_pdf = pdf_path
            logging.info(f"[{client_id}] Created consolidated PDF: {consolidated_pdf.name}")
        else:
            logging.info(f"[{client_id}] Using existing consolidated PDF: {consolidated_pdf.name}")

        dashboard.update(client_id, client_name, step="Uploading consolidated PDF", progress=30, status="RUNNING")

        # Upload the single consolidated PDF
        source_title = f"{client_id}_consolidated_sources"

        add_res = execute_with_backoff(
            ["notebooklm", "--storage", str(storage_path), "source", "add",
             "--title", source_title, str(consolidated_pdf)],
            client_token=client_id
        )
        metrics.increment_llm_calls()
        metrics.record_sources_ingested(client_id, 1)

        # Extract source ID and wait for import
        source_id_match = UUID_PATTERN.search(add_res.stdout if add_res else "")
        if source_id_match:
            source_id = source_id_match.group(1)
            logging.info(f"[{client_id}] Waiting for consolidated PDF to be imported: {source_id[:8]}...")

            dashboard.update(client_id, client_name, step="Importing consolidated PDF", progress=35, status="RUNNING")

            execute_with_backoff(
                ["notebooklm", "--storage", str(storage_path), "source", "wait", source_id, "--timeout", "120"],
                client_token=client_id,
                cmd_timeout=135.0
            )
            logging.info(f"[{client_id}] Consolidated PDF successfully imported!")

        state.mark_step_completed(client_id, "source_ingestion", {
            "sources_count": 1,
            "consolidated_pdf": str(consolidated_pdf.name)
        })
        dashboard.update(client_id, client_name, step="Ingestion completed", progress=45, status="RUNNING")

    except Exception as e:
        logging.error(f"[{client_id}] Ingestion failed: {e}")
        import traceback
        traceback.print_exc()
        state.mark_step_failed(client_id, "source_ingestion", str(e))
        dashboard.update(client_id, client_name, step="Ingestion failure", progress=100, status="FAILED")
        raise e


def get_note_title(prompt_filename: str, client_name: str) -> str:
    """
    Map prompt filenames to descriptive note titles.

    Args:
        prompt_filename: Name of the prompt file (e.g., 'chat_prompt_05.txt')
        client_name: Client name for substitution

    Returns:
        Descriptive note title
    """
    title_map = {
        'chat_prompt_01.txt': f'{client_name} Business Objectives',
        'chat_prompt_02.txt': f'{client_name} Market & Competitive Analysis',
        'chat_prompt_03.txt': f'{client_name} Technology & Partner Ecosystem',
        'chat_prompt_04.txt': f'{client_name} Value Propositions',
        'chat_prompt_05.txt': f'{client_name} Solution Ideas',
        'chat_prompt_06.txt': f'{client_name} Strategic Partnerships',
        'chat_prompt_07.txt': f'{client_name} Red Hat Technology Fit',
        'chat_prompt_08.txt': f'{client_name} Partner Briefing',
        'chat_prompt_09.txt': f'{client_name} Team Onboarding Guide',
        'chat_prompt_10.txt': f'{client_name} Services Partner Onboarding',
        'chat_prompt_11.txt': f'{client_name} How Might We Statements',
        'chat_prompt_12.txt': f'{client_name} Comprehensive Account Plan',

        # ASK prompts
        'ask_prompt_01.txt': f'{client_name} Foundation Research',
        'ask_prompt_02.txt': f'{client_name} Industry Subsegments',
    }

    return title_map.get(prompt_filename, f'{client_name} Note')


def execute_prompts(client_id: str, client_name: str, shared_auth_path: Path, nb_id: str, prompt_files: list):
    """Execute all prompts for this client with validation."""
    state = get_state()
    metrics = get_metrics()
    # Use shared storage file for this client to maintain auth across all operations
    storage_path = SCRIPT_DIR / f".storage_{client_id}.json"
    industry = getattr(config, f"{client_id}_industry", "")
    has_failures = False
    nb_client = NotebookLMClient(client_id, client_name, SCRIPT_DIR)

    try:
        if shared_auth_path.exists():
            storage_path.write_text(shared_auth_path.read_text())

        # Initial auth refresh
        nb_client.safe_auth_refresh(storage_path, min_interval=60.0)

        execute_with_backoff(
            ["notebooklm", "--storage", str(storage_path), "use", nb_id, "--force"],
            client_token=client_id
        )

        for p_idx, prompt_file in enumerate(prompt_files):
            # Refresh auth before each prompt to prevent token expiry (every 4 minutes max)
            nb_client.safe_auth_refresh(storage_path, min_interval=240.0)

            prompt_id = prompt_file.stem

            # Check if already completed
            if state.is_step_completed(client_id, f"prompt_{prompt_id}"):
                logging.info(f"[{client_id}] Skipping completed prompt: {prompt_id}")
                continue

            state.mark_step_started(client_id, f"prompt_{prompt_id}")
            prompt_metric = metrics.record_prompt_start(client_id, prompt_id)

            progress = 45 + int((p_idx / len(prompt_files)) * 40)
            dashboard.update(
                client_id,
                client_name,
                step=f"Prompting: {prompt_file.name}",
                progress=progress,
                status="RUNNING"
            )

            # Variable substitution
            persona = getattr(config, "persona", "senior account solutions architect")
            content = prompt_file.read_text().replace("$industry", industry).replace("$name", client_name).replace("$persona", persona)
            temp_prompt = SCRIPT_DIR / f".temp_prompt_{client_id}_{prompt_file.name}"
            temp_prompt.write_text(content, encoding="utf-8")

            retry_count = 0
            try:
                # Check if this is an ask prompt (research)
                if "ask" in prompt_file.name.lower():
                    res = execute_with_backoff(
                        ["notebooklm", "--storage", str(storage_path), "source", "add-research",
                         "--prompt-file", str(temp_prompt), "--mode", "fast",
                         "--import-all", "--cited-only"],  # CRITICAL FIX: Auto-import discovered sources
                        client_token=client_id
                    )
                    metrics.increment_llm_calls()

                    # With --import-all --cited-only, sources are automatically imported by add-research
                    # No need for manual URL extraction and import
                    logging.info(f"[{client_id}] Research completed with auto-import of cited sources")

                    output_text = res.stdout
                else:
                    # Regular chat prompt - get descriptive note title
                    note_title = get_note_title(prompt_file.name, client_name)

                    res = execute_with_backoff(
                        ["notebooklm", "--storage", str(storage_path), "ask",
                         "--prompt-file", str(temp_prompt),
                         "--save-as-note", "--note-title", note_title],
                        client_token=client_id
                    )
                    metrics.increment_llm_calls()
                    output_text = res.stdout

                # Validate output
                validation_result = validate_output(prompt_id, output_text)

                # Record metrics
                citations = len(re.findall(r'\[Source:', output_text))
                words = len(output_text.split())

                # Check for catastrophic validation failure (score < 3.0)
                if validation_result.quality_score < 3.0:
                    logging.error(f"[{client_id}] Catastrophic validation failure for {prompt_id}: Score {validation_result.quality_score}/10")
                    logging.error(f"[{client_id}] Output length: {words} words, Citations: {citations}")
                    logging.error(f"[{client_id}] Validation summary: {validation_result.get_summary()}")
                    # Mark as failure but continue to next prompt
                    has_failures = True
                    state.add_warning(client_id, f"{prompt_id}: CATASTROPHIC VALIDATION FAILURE (score: {validation_result.quality_score}/10)")
                elif validation_result.quality_score < 7.0:
                    logging.warning(f"[{client_id}] Low validation score for {prompt_id}: {validation_result.quality_score}/10")

                metrics.record_prompt_end(
                    prompt_metric,
                    success=True,
                    validation_score=validation_result.quality_score,
                    validation_issues=len(validation_result.issues),
                    output_words=words,
                    citations=citations,
                    retry_count=retry_count
                )

                # Record state
                state.mark_step_completed(client_id, f"prompt_{prompt_id}", {
                    "validation_score": validation_result.quality_score,
                    "validation_summary": validation_result.get_summary()
                })

                # Add warnings to state if quality issues
                if validation_result.has_warnings():
                    for issue in validation_result.issues:
                        if issue.severity == "warning":
                            state.add_warning(client_id, f"{prompt_id}: {issue.message}")

            except RuntimeError as e:
                logging.error(f"[{client_id}] Prompt failed: {prompt_file.name} - {e}")
                has_failures = True
                retry_count += 1
                metrics.increment_retries()

                metrics.record_prompt_end(
                    prompt_metric,
                    success=False,
                    retry_count=retry_count
                )
                state.mark_step_failed(client_id, f"prompt_{prompt_id}", str(e), retry_count)

            finally:
                if temp_prompt.exists():
                    temp_prompt.unlink()

        return "FAILED" if has_failures else "SUCCESS"

    except Exception as e:
        logging.error(f"[{client_id}] Prompt execution failed: {e}")
        return "FAILED"
    finally:
        # Keep storage file to maintain auth across all operations for this client
        pass
        # if storage_path.exists():
        #     storage_path.unlink()


def remove_duplicate_sources(client_id: str, client_name: str, shared_auth_path: Path, nb_id: str):
    """Remove duplicate sources from NotebookLM workspace."""
    state = get_state()
    nb_client = NotebookLMClient(client_id, client_name, SCRIPT_DIR)

    # Check if already completed
    if state.is_step_completed(client_id, "deduplication"):
        logging.info(f"[{client_id}] Source deduplication already completed")
        return

    state.mark_step_started(client_id, "deduplication")
    # Use shared storage file for this client to maintain auth across all operations
    storage_path = SCRIPT_DIR / f".storage_{client_id}.json"

    dashboard.update(client_id, client_name, step="Removing duplicate sources...", progress=88, status="RUNNING")

    try:
        if shared_auth_path.exists():
            storage_path.write_text(shared_auth_path.read_text())

        # Refresh auth before deduplication
        nb_client.safe_auth_refresh(storage_path, min_interval=60.0)

        execute_with_backoff(
            ["notebooklm", "--storage", str(storage_path), "use", nb_id, "--force"],
            client_token=client_id
        )

        # List all sources
        list_res = execute_with_backoff(
            ["notebooklm", "--storage", str(storage_path), "source", "list"],
            client_token=client_id
        )

        # Parse sources and find duplicates
        source_map = {}  # title -> [source_ids]
        source_lines = list_res.stdout.strip().split('\n') if list_res.stdout else []

        for line in source_lines:
            # Extract source ID and title from line
            # Format typically: "source_id  |  title  |  type"
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                source_id = parts[0].strip()
                title = parts[1].strip().lower()

                if title not in source_map:
                    source_map[title] = []
                source_map[title].append(source_id)

        # Find and remove duplicates (keep first occurrence)
        duplicates_removed = 0
        for title, source_ids in source_map.items():
            if len(source_ids) > 1:
                # Keep first, remove rest
                for dup_id in source_ids[1:]:
                    try:
                        execute_with_backoff(
                            ["notebooklm", "--storage", str(storage_path), "source", "remove", dup_id],
                            client_token=client_id
                        )
                        duplicates_removed += 1
                        logging.info(f"[{client_id}] Removed duplicate source: {title} (ID: {dup_id})")
                    except Exception as e:
                        logging.warning(f"[{client_id}] Failed to remove duplicate {dup_id}: {e}")

        if duplicates_removed > 0:
            logging.info(f"[{client_id}] Removed {duplicates_removed} duplicate sources")
        else:
            logging.info(f"[{client_id}] No duplicate sources found")

        state.mark_step_completed(client_id, "deduplication", {"duplicates_removed": duplicates_removed})

    except Exception as e:
        logging.error(f"[{client_id}] Source deduplication failed: {e}")
        state.mark_step_failed(client_id, "deduplication", str(e))
    finally:
        # Keep storage file to maintain auth across all operations for this client
        pass
        # if storage_path.exists():
        #     storage_path.unlink()


# ==============================================================================
# EMAIL NOTIFICATION
# ==============================================================================

def generate_artifacts(client_id: str, client_name: str, shared_auth_path: Path, nb_id: str):
    """Generate mindmap and slideshow artifacts for the client."""
    state = get_state()
    storage_path = SCRIPT_DIR / f".storage_{client_id}.json"

    try:
        # Copy shared auth
        if shared_auth_path.exists():
            storage_path.write_text(shared_auth_path.read_text())

        # Set notebook context
        execute_with_backoff(
            ["notebooklm", "--storage", str(storage_path), "use", nb_id, "--force"],
            client_token=client_id
        )

        dashboard.update(client_id, client_name, step="Generating mindmap", progress=95, status="RUNNING")
        logging.info(f"[{client_id}] Generating mindmap...")

        # Generate mindmap (interactive version for modern UI)
        mindmap_res = execute_with_backoff(
            ["notebooklm", "--storage", str(storage_path), "generate", "mind-map",
             "--kind", "interactive", "--json"],
            client_token=client_id,
            cmd_timeout=120.0
        )
        logging.info(f"[{client_id}] Mindmap generated successfully")

        dashboard.update(client_id, client_name, step="Generating slideshow", progress=97, status="RUNNING")
        logging.info(f"[{client_id}] Generating slideshow...")

        # Generate slide deck
        slide_res = execute_with_backoff(
            ["notebooklm", "--storage", str(storage_path), "generate", "slide-deck",
             f"{client_name} Account Plan Presentation",
             "--format", "presenter", "--wait", "--timeout", "180", "--json"],
            client_token=client_id,
            cmd_timeout=200.0
        )
        logging.info(f"[{client_id}] Slideshow generated successfully")

        state.mark_step_completed(client_id, "artifact_generation", {
            "mindmap": "generated",
            "slideshow": "generated"
        })

    except Exception as e:
        logging.error(f"[{client_id}] Artifact generation failed: {e}")
        state.mark_step_failed(client_id, "artifact_generation", str(e))


def send_completion_email(client_results: dict):
    """Send email notification with NotebookLM links."""
    import json

    try:
        # Use email from config instead of trying to extract from auth
        user_email = getattr(config, "notification_email", None)

        if not user_email or user_email == "jason.anderson@example.com":
            logging.warning("notification_email not configured in vars.py - skipping email")
            print("\n⚠️  Email notification skipped - update 'notification_email' in vars.py")
            return

        # Build email body
        body_lines = ["Account Planning Engine - Execution Complete\n\n"]
        body_lines.append("Completed Account Plans:\n")
        body_lines.append("=" * 70 + "\n\n")

        for client_id, result in client_results.items():
            client_name = result.get("name", client_id)
            nb_url = result.get("url", "https://notebooklm.google.com/")
            status = result.get("status", "UNKNOWN")

            body_lines.append(f"• {client_name}\n")
            body_lines.append(f"  Status: {status}\n")
            body_lines.append(f"  NotebookLM URL: {nb_url}\n\n")

        body_lines.append("\n" + "=" * 70 + "\n")
        body_lines.append("Access your complete account plans in NotebookLM using the links above.\n")
        body_lines.append("\nAll research, notes, and the 'Comprehensive Account Plan' are available in each workspace.\n")

        email_body = "".join(body_lines)

        # Log email notification
        logging.info(f"=" * 70)
        logging.info(f"EMAIL NOTIFICATION PREPARED")
        logging.info(f"=" * 70)
        logging.info(f"To: {user_email}")
        logging.info(f"Subject: AI Account Plans")
        logging.info(f"\n{email_body}")
        logging.info(f"=" * 70)

        print(f"\n📧 Email notification prepared for: {user_email}")
        print(f"   Check logs for full email content")

    except Exception as e:
        logging.error(f"Error preparing email notification: {e}")


# ==============================================================================
# PIPELINE ORCHESTRATION
# ==============================================================================

def run_client_pipeline(client_id: str, client_name: str, shared_auth_path: Path, nb_id: str, prompt_files: list):
    """Execute complete pipeline for one client."""
    state = get_state()
    metrics = get_metrics()

    metrics.start_client(client_id, client_name)

    try:
        ingest_sources(client_id, client_name, shared_auth_path, nb_id)
        status = execute_prompts(client_id, client_name, shared_auth_path, nb_id, prompt_files)
        remove_duplicate_sources(client_id, client_name, shared_auth_path, nb_id)
        generate_artifacts(client_id, client_name, shared_auth_path, nb_id)
        dashboard.update(client_id, client_name, step="Complete - View in NotebookLM", progress=100, status="COMPLETE")

        # Determine final status
        failed_steps = state.get_failed_steps(client_id)
        if failed_steps:
            final_status = "failed"
        elif status == "SUCCESS":
            final_status = "success"
        else:
            final_status = "degraded"

        state.mark_client_completed(client_id, final_status)
        metrics.end_client(client_id, final_status)

    except Exception as e:
        logging.error(f"[{client_id}] Pipeline crashed: {e}")
        dashboard.update(client_id, client_name, step="Pipeline crash", progress=100, status="FAILED")
        state.mark_client_completed(client_id, "failed")
        metrics.end_client(client_id, "failed")
    finally:
        # Clean up client storage file after pipeline completes
        storage_path = SCRIPT_DIR / f".storage_{client_id}.json"
        if storage_path.exists():
            try:
                storage_path.unlink()
                logging.info(f"[{client_id}] Cleaned up storage file")
            except Exception:
                pass
        dashboard.increment_finished()


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Parse arguments
    parser = argparse.ArgumentParser(description="Project APE - Fast Mode")
    parser.add_argument("--resume", action="store_true", help="Resume from last saved state")
    parser.add_argument("--clear-state", action="store_true", help="Clear saved state and start fresh")
    args = parser.parse_args()

    print("=" * 71)
    print(" PROJECT APE - FAST MODE")
    print("=" * 71)

    # Initialize state and metrics
    state = init_state(STATE_FILE)
    metrics = init_metrics(METRICS_FILE, mode="fast")

    if args.clear_state:
        print(" Clearing saved state...")
        for client in state.get_all_clients():
            state.clear_client(client)

    if args.resume:
        print(" Resuming from saved state...")
        state.print_summary()

    # Validate configuration
    validate_configuration()

    # Authenticate - force fresh login
    print("\n🔐 Authenticating with NotebookLM...")
    print("    Please complete the login process in your browser...")

    try:
        # Force logout first to ensure clean state (ignore errors if not logged in)
        subprocess.run(["notebooklm", "logout"],
                      stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL)

        # Force fresh login
        result = subprocess.run(["notebooklm", "login"],
                               capture_output=True,
                               text=True)

        if result.returncode != 0:
            print("\n[AUTH ERROR] Login failed. Please try again.", file=sys.stderr)
            if result.stderr:
                print(f"Error details: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        print("✓ Authentication successful!\n")

    except FileNotFoundError:
        print("\n[ERROR] 'notebooklm' command not found. Please install it first.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[AUTH ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    shared_auth_path = Path.home() / ".notebooklm" / "profiles" / "default" / "storage_state.json"
    if not shared_auth_path.exists():
        shared_auth_path = Path.home() / ".notebooklm" / "storage_state.json"

    # Load clients and prompts
    clients = [c.split('.')[-1].strip() if '.' in c else c.strip() for c in getattr(config, "clients", [])]
    # Load prompt files from SCRIPT_DIR (notebooklm/)
    # Match actual prompt naming: ask_*.txt and chat_*.txt
    prompt_files = list(SCRIPT_DIR.glob("ask_*.txt")) + \
                   list(SCRIPT_DIR.glob("chat_*.txt"))

    if not clients or not prompt_files:
        print("Error: No clients or prompts configured", file=sys.stderr)
        sys.exit(1)

    # Sort prompts: ask first, then chat
    prompt_files = sorted([p for p in prompt_files if "ask" in p.name.lower()]) + \
                   sorted([p for p in prompt_files if "ask" not in p.name.lower()])

    logging.info(f"Loaded {len(clients)} clients and {len(prompt_files)} prompts")

    # Initialize dashboard
    dashboard.total_count = len(clients)
    for client in clients:
        client_name = getattr(config, f"{client}_name", client)
        state.initialize_client(client, client_name)
        dashboard.update(client, client_name, step="Queued", progress=0, status="QUEUED")

    # Open dashboard
    try:
        webbrowser.open(DASHBOARD_PATH.as_uri())
    except Exception:
        pass

    # Create notebooks in parallel (cache prevents duplicates)
    notebook_map = {}
    try:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(clients))) as executor:
            notebook_futures = {
                executor.submit(ensure_notebook_exists, client, getattr(config, f"{client}_name", client), shared_auth_path): client
                for client in clients
            }

            for future in as_completed(notebook_futures):
                if shutdown_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise KeyboardInterrupt("Shutdown requested")
                result = future.result()
                if result and result[2]:
                    notebook_map[result[0]] = result[2]

        # Run pipelines in parallel
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(clients))) as executor:
            futures = {
                executor.submit(
                    run_client_pipeline,
                    client,
                    getattr(config, f"{client}_name", client),
                    shared_auth_path,
                    notebook_map[client],
                    prompt_files
                ): client
                for client in clients if client in notebook_map
            }

            for future in as_completed(futures):
                if shutdown_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise KeyboardInterrupt("Shutdown requested")
                future.result()

    except KeyboardInterrupt:
        print("\n⚠️  Shutdown in progress... (this may take a few seconds)")
        logging.info("SHUTDOWN: Cleaning up executor threads")
        sys.exit(0)

    # Export metrics and state
    metrics.export()
    metrics.print_summary()
    state.print_summary()

    # Prepare and send email notification
    client_results = {}
    for client in clients:
        if client in notebook_map:
            client_name = getattr(config, f"{client}_name", client)
            nb_id = notebook_map[client]
            nb_url = f"https://notebooklm.google.com/notebook/{nb_id}"
            status = "COMPLETE" if client in notebook_map else "FAILED"

            client_results[client] = {
                "name": client_name,
                "url": nb_url,
                "status": status
            }

    # Send email with all results
    send_completion_email(client_results)

    print("\n" + "=" * 71)
    print(" PROJECT APE FAST MODE COMPLETE")
    print("=" * 71)
    print(f" Dashboard: {DASHBOARD_PATH}")
    print(f" Logs: {LOG_FILE_PATH}")
    print(f" Metrics: {METRICS_FILE}")
    print(f" State: {STATE_FILE}")
    print("=" * 71)
    print("\n To resume from last state: python fast.py --resume")
    print(" To start fresh: python fast.py --clear-state")
    print("=" * 71)


if __name__ == "__main__":
    main()
