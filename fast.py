#!/usr/bin/env python3
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
import tkinter as tk
from tkinter import filedialog
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# --- Fallback Check for Google API Dependencies ---
try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
except ImportError:
    print("Error: Missing required Google API dependencies. Run 'pip install google-api-python-client'", file=sys.stderr)
    sys.exit(1)

# --- Configuration & Setup ---
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

try:
    import vars as config
except ImportError:
    print(f"Error: Could not find vars.py in {SCRIPT_DIR}", file=sys.stderr)
    sys.exit(1)

# Configure dual logging handlers for verbose output file routing
LOG_FILE_PATH = SCRIPT_DIR / "pipeline_fast_execution.log"
DASHBOARD_PATH = SCRIPT_DIR / "pipeline_dashboard.html"

log_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s",
    datefmt="%H:%M:%S"
)

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler(LOG_FILE_PATH, mode="w", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(log_formatter)
root_logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

ui_queue = queue.Queue()

# --- Concurrency & UI Control Synchronization Locks ---
dashboard_lock = threading.Lock()
dashboard_state = {}


def update_dashboard(client_token, step=None, progress=None, status=None):
    """Thread-safe updates to the unified local HTML live tracking dashboard with adaptive JS auto-refresh."""
    client_name = getattr(config, f"{client_token}_name", client_token)
    if client_token not in dashboard_state:
        dashboard_state[client_token] = {
            "name": client_name,
            "step": "Initializing",
            "progress": 0,
            "status": "PENDING"
        }
    
    if step is not None: dashboard_state[client_token]["step"] = step
    if progress is not None: dashboard_state[client_token]["progress"] = progress
    if status is not None: dashboard_state[client_token]["status"] = status

    # Generate flat self-refreshing HTML layout sheet with variable metadata hooks
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Fast Pipeline Execution Studio</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #fafafa; color: #222; padding: 30px; }}
        .container {{ max-width: 900px; margin: 0 auto; background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-top: 4px solid #10b981; }}
        h2 {{ margin-top: 0; color: #0f172a; border-bottom: 1px solid #f1f5f9; padding-bottom: 10px; }}
        .client-card {{ background: #f8fafc; border: 1px solid #f1f5f9; border-radius: 8px; padding: 15px; margin-bottom: 15px; }}
        .card-header {{ display: flex; justify-content: space-between; font-weight: bold; margin-bottom: 8px; color: #0f172a; }}
        .progress-bar-bg {{ background: #e2e8f0; width: 100%; height: 12px; border-radius: 6px; overflow: hidden; margin-bottom: 8px; }}
        .progress-bar-fill {{ background: #10b981; height: 100%; transition: width 0.3s ease; }}
        .status-RUNNING {{ color: #dfa510; }}
        .status-COMPLETE {{ color: #10b981; }}
        .status-FAILED {{ color: #ef4444; }}
        .status-PENDING {{ color: #64748b; }}
        .meta {{ font-size: 0.85em; color: #64748b; }}
    </style>
    <script>
        window.addEventListener('DOMContentLoaded', () => {{
            let launchTime = localStorage.getItem('fast_pipeline_start');
            if (!launchTime) {{
                launchTime = Date.now();
                localStorage.setItem('fast_pipeline_start', launchTime);
            }}
            let intervals = (Date.now() - parseInt(launchTime) < 5000) ? 1000 : 5000;
            setTimeout(() => {{ window.location.reload(); }}, intervals);
        }});
    </script>
</head>
<body>
    <div class="container">
        <h2>Workspace Compilation Pipeline Dashboard (FAST MODE)</h2>
        <p class="meta">Adaptive Monitoring Log. Dashboard Location: <code style="background:#e2e8f0; padding:2px 5px; border-radius:4px;">{DASHBOARD_PATH}</code></p>
    </div>
    <div class="container" style="margin-top: 20px;">
    """
    for token, data in dashboard_state.items():
        fill_color = "#10b981"
        if data["status"] == "FAILED": fill_color = "#ef4444"
        if data["status"] == "RUNNING": fill_color = "#f59e0b"
        if data["status"] == "PENDING": fill_color = "#64748b"

        html_content += f"""
        <div class="client-card">
            <div class="card-header">
                <span>{data["name"]} <span class="meta">({token})</span></span>
                <span class="status-{data["status"]}">[{data["status"]}]</span>
            </div>
            <div class="progress-bar-bg">
                <div class="progress-bar-fill" style="width: {data["progress"]}%; background-color: {fill_color};"></div>
            </div>
            <div class="meta">Active Step: <strong>{data["step"]}</strong> ({data["progress"]}%)</div>
        </div>
        """
    html_content += "</div></body></html>"
    
    with dashboard_lock:
        try:
            DASHBOARD_PATH.write_text(html_content, encoding="utf-8")
        except IOError:
            pass


def run_cmd(cmd, check=True, text=True, capture_output=False, input_data=None):
    """Safely executes system commands with optional input injection."""
    logging.debug(f"Executing system command: {' '.join(cmd)}")
    try:
        res = subprocess.run(
            cmd,
            check=check,
            text=text,
            capture_output=capture_output,
            input=input_data,
        )
        if capture_output and res.stdout:
            logging.debug(f"Command stdout trace: {res.stdout.strip()}")
        return res
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with exit code {e.returncode}: {' '.join(cmd)}")
        if e.stderr:
            logging.error(f"Error details captured: {e.stderr.strip()}")
        raise e


def fetch_notebook_cache(storage_path=None):
    """Fetches the notebook list using an explicit storage path to bypass race conditions."""
    cmd = ["notebooklm"]
    if storage_path:
        cmd.extend(["--storage", str(storage_path)])
    cmd.append("list")

    try:
        res = run_cmd(cmd, capture_output=True)
        cache = {}
        for line in res.stdout.splitlines():
            clean_line = line.replace("│", "").replace("┃", "").strip()
            parts = clean_line.split()
            if len(parts) >= 2 and "-" in parts[0]:
                nb_id = parts[0]
                if "Owner" in parts:
                    name = " ".join(parts[1:parts.index("Owner")]).strip()
                else:
                    name = " ".join(parts[1:-2]).strip()
                cache[name] = nb_id
        return cache
    except Exception as e:
        logging.error(f"Failed to fetch notebook cache: {e}")
        return {}


def ensure_notebook_exists(client, shared_auth_path):
    """Worker task to ensure a notebook exists for a client before any UI prompts happen."""
    client_storage = SCRIPT_DIR / f".storage_{client}.json"
    update_dashboard(client, step="Pre-flight verification", progress=5, status="RUNNING")
    try:
        if shared_auth_path.exists():
            client_storage.write_text(shared_auth_path.read_text())
            time.sleep(0.1)

        name_value = getattr(config, f"{client}_name", "")
        if not name_value:
            update_dashboard(client, step="Skipped - No configuration matched", progress=0, status="PENDING")
            return None

        notebook_cache = fetch_notebook_cache(storage_path=client_storage)
        nb_id = notebook_cache.get(name_value)

        if not nb_id:
            logging.info(f"[{name_value}] Notebook missing. Pre-creating workspace now...")
            res = run_cmd(["notebooklm", "--storage", str(client_storage), "create", name_value], capture_output=True)
            
            uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', res.stdout, re.IGNORECASE)
            
            if uuid_match:
                nb_id = uuid_match.group(1)
                logging.info(f"[{name_value}] Successfully created notebook with verified ID: {nb_id}")
            else:
                time.sleep(2.0)
                notebook_cache = fetch_notebook_cache(storage_path=client_storage)
                nb_id = notebook_cache.get(name_value)
                
            if not nb_id:
                raise Exception(f"Failed to verify or parse notebook creation for: {name_value}")
        
        update_dashboard(client, step="Workspace Link Ready", progress=15, status="RUNNING")
        return client, name_value, nb_id
    except Exception as e:
        update_dashboard(client, step=f"Pre-flight error: {str(e)[:20]}", progress=100, status="FAILED")
        raise e
    finally:
        if client_storage.exists():
            try:
                client_storage.unlink()
            except Exception:
                pass


def extract_id_from_google_shortcut(file_path):
    """Parses local desktop sync pointer files (.gdoc/.gslides) and extracts raw Document IDs."""
    try:
        content = Path(file_path).read_text(errors='ignore')
        if '"doc_id"' in content or '"id"' in content:
            data = json.loads(content)
            doc_id = data.get("doc_id") or data.get("id") or data.get("resource_id")
            if doc_id:
                return doc_id
        url_match = re.search(r'https://docs\.google\.com/[^/]+/d/([a-zA-Z0-9-_]+)', content)
        if url_match:
            return url_match.group(1)
    except Exception:
        pass
    return None


def convert_sheet_shortcut_to_csv_text(file_path, client_storage):
    """Fallback context compiler to convert spreadsheets into flat CSV data for indexing."""
    try:
        import pandas as pd
        csv_path = Path(file_path).with_suffix('.csv')
        if os.path.exists(file_path.replace('.gsheet', '.xlsx')):
            df = pd.read_excel(file_path.replace('.gsheet', '.xlsx'))
            df.to_csv(csv_path, index=False)
            return csv_path
    except Exception:
        pass
    return None


def request_files_from_main_thread(client_name, timeout_secs=90):
    """Thread-safe bridge that sends a UI request to the main thread and awaits results."""
    response_queue = queue.Queue()
    ui_queue.put((client_name, timeout_secs, response_queue))
    return response_queue.get()


def try_upload_local_file_with_fallbacks(client_storage, target_id, source_title, name_value):
    """Uses verified standard click format targeting option parameters properly."""
    variations = [
        ["notebooklm", "--storage", str(client_storage), "source", "add", "--title", source_title, target_id],
        ["notebooklm", "--storage", str(client_storage), "source", "add", target_id],
    ]

    for cmd in variations:
        try:
            variant_label = " ".join(cmd[4:])
            res = run_cmd(cmd, capture_output=True)
            return res.stdout
        except subprocess.CalledProcessError:
            continue
    return None


def ingest_client_sources(client, shared_auth_path, nb_id):
    """PHASE 0: Handles collection, localization parsing, and remote upload of custom client knowledge assets."""
    client_storage = SCRIPT_DIR / f".storage_ingest_{client}.json"
    temporary_files_to_clean = []
    name_value = getattr(config, f"{client}_name", f"UnknownClient-{client}")
    tracked_tokens = []

    update_dashboard(client, step="Phase 0: Resolving Source Targets", progress=20, status="RUNNING")
    try:
        if shared_auth_path.exists():
            client_storage.write_text(shared_auth_path.read_text())
            time.sleep(random.uniform(0.05, 0.2))

        drive_folder_value = getattr(config, f"{client}_folder", None)

        manually_selected_sources = request_files_from_main_thread(name_value, timeout_secs=90)

        run_cmd(["notebooklm", "--storage", str(client_storage), "auth", "refresh", "--quiet"])
        run_cmd(["notebooklm", "--storage", str(client_storage), "use", nb_id])

        drive_targets = []
        if drive_folder_value:
            drive_targets.extend([t.strip() for t in str(drive_folder_value).split(",") if t.strip()])
        if manually_selected_sources:
            drive_targets.extend(manually_selected_sources)

        if not drive_targets:
            update_dashboard(client, step="Phase 0: Complete (No assets specified)", progress=40, status="RUNNING")
            return

        update_dashboard(client, step=f"Phase 0: Uploading {len(drive_targets)} source items", progress=30, status="RUNNING")

        for idx, target_id in enumerate(drive_targets):
            is_local = os.path.exists(target_id) and os.path.isfile(target_id)
            suffix = Path(target_id).suffix.lower() if is_local else ""

            if is_local and suffix == '.gsheet':
                converted_csv = convert_sheet_shortcut_to_csv_text(target_id, client_storage)
                if converted_csv and converted_csv.exists():
                    target_id = str(converted_csv)
                    is_local = True
                    suffix = '.csv'
                    temporary_files_to_clean.append(converted_csv)

            is_gdrive_shortcut = is_local and suffix in ['.gdoc', '.gslides', '.gdraw']
            raw_title = Path(target_id).stem if is_local else f"doc_{idx + 1}"
            clean_title = re.sub(r'[^a-zA-Z0-9_]', '', raw_title.replace(' ', '_'))
            source_title = f"{client}_source_{clean_title}"

            output_text = None

            if is_gdrive_shortcut:
                extracted_id = extract_id_from_google_shortcut(target_id)
                if extracted_id:
                    try:
                        res = run_cmd(["notebooklm", "--storage", str(client_storage), "source", "add-drive", extracted_id, source_title], capture_output=True)
                        output_text = res.stdout
                    except subprocess.CalledProcessError:
                        pass
            elif is_local:
                output_text = try_upload_local_file_with_fallbacks(client_storage, target_id, source_title, name_value)
            else:
                try:
                    res = run_cmd(["notebooklm", "--storage", str(client_storage), "source", "add-drive", target_id, source_title], capture_output=True)
                    output_text = res.stdout
                except subprocess.CalledProcessError:
                    pass

            if output_text:
                uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', output_text, re.IGNORECASE)
                wait_target = uuid_match.group(1) if uuid_match else source_title
                tracked_tokens.append(wait_target)

        if tracked_tokens:
            update_dashboard(client, step=f"Phase 0: Synced batch wait lock clearing...", progress=35, status="RUNNING")
            for token in tracked_tokens:
                try:
                    run_cmd(["notebooklm", "--storage", str(client_storage), "source", "wait", token])
                except subprocess.CalledProcessError:
                    pass

        update_dashboard(client, step="Phase 0: Ingestion Completed successfully", progress=40, status="RUNNING")
    except Exception as e:
        update_dashboard(client, step=f"Phase 0 Error: {str(e)[:20]}", progress=100, status="FAILED")
        raise e
    finally:
        if client_storage.exists():
            try:
                client_storage.unlink()
            except Exception:
                pass
        for temp_file in temporary_files_to_clean:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass


def execute_client_prompts(client, sorted_prompt_files, shared_auth_path, nb_id):
    """PHASE 1: Runs inference and sequencing prompts once global environment data ingestion completes."""
    client_storage = SCRIPT_DIR / f".storage_prompts_{client}.json"
    name_value = getattr(config, f"{client}_name", f"UnknownClient-{client}")
    industry_value = getattr(config, f"{client}_industry", "")

    update_dashboard(client, step="Phase 1: Sequential prompting cycle", progress=45, status="RUNNING")
    try:
        if shared_auth_path.exists():
            client_storage.write_text(shared_auth_path.read_text())
            time.sleep(0.1)

        run_cmd(["notebooklm", "--storage", str(client_storage), "use", nb_id])
        output_dir = SCRIPT_DIR / client
        output_dir.mkdir(parents=True, exist_ok=True)

        for p_idx, prompt_file in enumerate(sorted_prompt_files):
            step_pct = int(45 + ((p_idx / len(sorted_prompt_files)) * 25))
            update_dashboard(client, step=f"Phase 1: Processing {prompt_file.name}", progress=step_pct, status="RUNNING")
            
            prompt_content = prompt_file.read_text()
            updated_content = prompt_content.replace("$industry", industry_value).replace("$name", name_value)

            gqp = output_dir / prompt_file.name
            gqp.write_text(updated_content)

            if "ask" in gqp.name.lower():
                try:
                    logging.info(f"[{name_value}] Initiating fast web research agent loop from prompt file query: {gqp.name}")
                    run_cmd(["notebooklm", "--storage", str(client_storage), "source", "add-research", "--prompt-file", str(gqp.resolve()), "--no-wait"])
                    
                    logging.info(f"[{name_value}] Intercepting non-blocking telemetry loop via status features...")
                    timeout_limit = 60  
                    loop_idx = 0
                    
                    while loop_idx < timeout_limit:
                        status_res = run_cmd(["notebooklm", "--storage", str(client_storage), "research", "status"], capture_output=True)
                        status_text = status_res.stdout.upper()
                        
                        if "COMPLETED" in status_text or "IDLE" in status_text:
                            logging.info(f"[{name_value}] Cloud verified processing window closed successfully.")
                            break
                        elif any(term in status_text for term in ["PROCESSING", "INGESTING", "RUNNING", "PENDING", "SYNCHRONIZING"]):
                            update_dashboard(client, step=f"Phase 1: Web Research Ingesting...", progress=step_pct, status="RUNNING")
                            time.sleep(4.0)  
                            loop_idx += 1
                        else:
                            logging.warning(f"[{name_value}] Ambiguous status signature detected: {status_text or 'EMPTY'}.")
                            time.sleep(4.0)
                            loop_idx += 1
                            
                    logging.info(f"[{name_value}] Finalizing fast referenced asset tray synchronization syncing barrier...")
                    run_cmd(["notebooklm", "--storage", str(client_storage), "research", "wait", "--import-all", "--timeout", "30"])
                    time.sleep(1.0)
                except subprocess.CalledProcessError as e:
                    logging.error(f"[{name_value}] Web research indexing execution sequence failed: {e}")
            else:
                try:
                    logging.info(f"[{name_value}] Executing conversation sequence against linked profile memory target: {gqp.name}")
                    run_cmd(["notebooklm", "--storage", str(client_storage), "ask", updated_content, "--save-as-note"])
                    run_cmd(["notebooklm", "--storage", str(client_storage), "status"])
                except subprocess.CalledProcessError as e:
                    logging.error(f"[{name_value}] Ask chat dialogue context failed: {e}")

        update_dashboard(client, step="Phase 1: All prompts processed", progress=70, status="RUNNING")
    except Exception as e:
        update_dashboard(client, step=f"Phase 1 Error: {str(e)[:20]}", progress=100, status="FAILED")
        raise e
    finally:
        if client_storage.exists():
            try:
                client_storage.unlink()
                context_file = Path(str(client_storage) + ".context.json")
                if context_file.exists():
                    context_file.unlink()
            except Exception:
                pass


def clean_duplicate_sources(client, shared_auth_path, nb_id):
    """Scans the notebook source registry for a client and purges identical titles automatically without interactive blocks."""
    client_storage = SCRIPT_DIR / f".storage_clean_{client}.json"
    name_value = getattr(config, f"{client}_name", "")

    update_dashboard(client, step="Phase 2: Deduplication Sweep", progress=75, status="RUNNING")
    try:
        if shared_auth_path.exists():
            client_storage.write_text(shared_auth_path.read_text())
            time.sleep(0.1)

        run_cmd(["notebooklm", "--storage", str(client_storage), "use", nb_id])
        res = run_cmd(["notebooklm", "--storage", str(client_storage), "source", "list"], capture_output=True)

        seen_titles = set()
        duplicates_to_remove = []

        for line in res.stdout.splitlines():
            clean_line = line.replace("│", "").replace("┃", "").strip()
            parts = clean_line.split()

            if parts and parts[0] != "ID" and "-" in parts[0]:
                source_id = parts[0]
                source_title = " ".join(parts[1:-1]).strip() if "type" in parts[-1].lower() else " ".join(parts[1:]).strip()

                if source_title in seen_titles:
                    duplicates_to_remove.append((source_id, source_title))
                else:
                    seen_titles.add(source_title)

        if duplicates_to_remove:
            for source_id, source_title in duplicates_to_remove:
                try:
                    run_cmd(["notebooklm", "--storage", str(client_storage), "source", "delete", source_id], input_data="y\n")
                    time.sleep(0.5)
                except subprocess.CalledProcessError:
                    pass
            run_cmd(["notebooklm", "--storage", str(client_storage), "status"])

        update_dashboard(client, step="Phase 2: Workspace Workspace Deduplicated", progress=85, status="RUNNING")
    except Exception as e:
        update_dashboard(client, step=f"Phase 2 Error: {str(e)[:20]}", progress=100, status="FAILED")
        raise e
    finally:
        if client_storage.exists():
            try:
                client_storage.unlink()
            except Exception:
                pass


def post_process_assets(client, shared_auth_path, nb_id):
    """Fault-Tolerant Dynamic Asset Generation Block."""
    client_storage = SCRIPT_DIR / f".storage_asset_{client}.json"
    name_value = getattr(config, f"{client}_name", "")

    update_dashboard(client, step="Phase 3: Dynamic Asset Compilation", progress=88, status="RUNNING")
    try:
        if shared_auth_path.exists():
            client_storage.write_text(shared_auth_path.read_text())
            time.sleep(0.1)

        run_cmd(["notebooklm", "--storage", str(client_storage), "use", nb_id])

        # FIXED: Removed the _supportable lookup loops completely to run generation natively against local assets
        generation_commands = [
            (["mind-map"], "Mind Map Generation"),
            (["data-table", "compare key concepts"], "Tabular Matrix Definition"),
            (["slide-deck"], "Executive Slide Deck Representation"),
            (["infographic", "--orientation", "portrait"], "Portrait Infographic Mapping")
        ]

        for sub_args, label in generation_commands:
            try:
                cmd = ["notebooklm", "--storage", str(client_storage), "generate"] + sub_args
                run_cmd(cmd, check=True)
                time.sleep(1.0)
            except subprocess.CalledProcessError:
                pass

        update_dashboard(client, step="Pipeline Finished Successfully", progress=100, status="COMPLETE")
    except Exception as e:
        update_dashboard(client, step=f"Phase 3 Error: {str(e)[:20]}", progress=100, status="FAILED")
        raise e
    finally:
        if client_storage.exists():
            try:
                client_storage.unlink()
            except Exception:
                pass


def main():
    start_time = time.time()

    os.environ['fast_pipeline_start'] = str(int(time.time() * 1000))
    DASHBOARD_PATH.write_text("<h1>Initializing Fast Workspace Compilation Pipeline...</h1>", encoding="utf-8")
    try:
        webbrowser.open(DASHBOARD_PATH.as_uri())
    except Exception:
        pass

    logging.info("Stabilizing background browser interface profiles (5-second initialization sync loop)...")
    time.sleep(5.0)

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    shared_auth_path = Path.home() / ".notebooklm" / "profiles" / "default" / "storage_state.json"
    if not shared_auth_path.exists():
        shared_auth_path = Path.home() / ".notebooklm" / "storage_state.json"

    try:
        run_cmd(["notebooklm", "login"])
    except Exception:
        logging.critical("Initial login failed. Exiting execution loop.")
        sys.exit(1)

    clients = getattr(config, "clients", [])
    raw_prompt_files = [Path(f) for f in glob.glob(str(SCRIPT_DIR / "*prompt*.txt")) if Path(f).is_file()]

    if not raw_prompt_files or not clients:
        logging.warning("No prompt files or clients found to process.")
        return

    ask_files = [f for f in raw_prompt_files if "ask" in f.name.lower()]
    other_files = [f for f in raw_prompt_files if "ask" not in f.name.lower()]
    sorted_prompt_files = sorted(ask_files) + sorted(other_files)

    for client in clients:
        update_dashboard(client, step="Queued in staging environment", progress=0, status="PENDING")

    MAX_WORKERS = min(8, len(clients))

    # --- STEP 1: PRE-CREATE/VERIFY NOTEBOOKS CONCURRENTLY ---
    logging.info(f"Starting Pre-Flight Phase: Verifying/Creating notebooks for all {len(clients)} clients...")
    master_notebook_cache = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        notebook_futures = [executor.submit(ensure_notebook_exists, client, shared_auth_path) for client in clients]
        for future in as_completed(notebook_futures):
            try:
                result = future.result()
                if result:
                    client_token, human_name, verified_id = result
                    master_notebook_cache[client_token] = verified_id
            except Exception:
                pass

    # --- STEP 2: SPIN UP PIPELINE INGESTION BACKGROUND WORKERS ---
    logging.info(f"Starting Phase 0 Source Ingestion background workers in parallel...")
    ingest_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    futures = [
        ingest_executor.submit(ingest_client_sources, client, shared_auth_path, master_notebook_cache[client])
        for client in clients if client in master_notebook_cache
    ]

    # --- STEP 3: MAIN THREAD GUI WATCHDOG LOOP FOR INGESTION ---
    completed_count = 0
    total_expected = len(futures)

    while completed_count < total_expected:
        try:
            client_name, timeout_secs, response_queue = ui_queue.get(timeout=1.0)
            logging.info(f"[MainThread] Intercepted UI request. Opening file explorer exclusively for: [{client_name}]")

            selected_assets = []
            
            def handle_timeout():
                dialog_window.destroy()
                response_queue.put([])

            dialog_window = tk.Toplevel(root)
            dialog_window.withdraw()
            dialog_window.after(timeout_secs * 1000, handle_timeout)

            files = filedialog.askopenfilenames(
                parent=dialog_window,
                title=f"Select Files (PDF, Text, Shortcuts) strictly for: {client_name}",
                filetypes=[
                    ("Supported Files", "*.pdf *.txt *.docx *.gdoc *.gsheet"),
                    ("PDF Documents", "*.pdf"),
                    ("All Files", "*.*")
                ]
            )
            
            if files:
                selected_assets.extend(list(files))
                
            dialog_window.destroy()
            response_queue.put(selected_assets)

        except queue.Empty:
            finished_futures = [f for f in futures if f.done()]
            completed_count = len(finished_futures)
            continue

    ingest_executor.shutdown(wait=True)
    logging.info("==> Phase 0 Ingestion fully completed across all active workers.")

    # --- STEP 4: PHASE 1 SEQUENTIAL PROMPTING BARRIER ---
    logging.info("Starting Phase 1 Prompt Sequence execution targeting fast default lanes...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as prompt_executor:
        prompt_futures = [
            prompt_executor.submit(execute_client_prompts, client, sorted_prompt_files, shared_auth_path, master_notebook_cache[client])
            for client in clients if client in master_notebook_cache
        ]
        for future in as_completed(prompt_futures):
            try:
                future.result()
            except Exception:
                pass

    # --- STEP 5: PARALLEL CLEANUP INTERMEDIATE PHASE ---
    logging.info("Starting Parallel Source Deduplication Cleanup Phase...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        clean_futures = [
            executor.submit(clean_duplicate_sources, client, shared_auth_path, master_notebook_cache[client])
            for client in clients if client in master_notebook_cache
        ]
        for future in as_completed(clean_futures):
            try:
                future.result()
            except Exception:
                pass

    # --- STEP 6: CONCURRENT POST-PROCESS ASSETS ---
    logging.info("Starting Phase 2 Asset Generation across isolated threads...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        assets_futures = [
            executor.submit(post_process_assets, client, shared_auth_path, master_notebook_cache[client])
            for client in clients if client in master_notebook_cache
        ]
        for future in as_completed(assets_futures):
            try:
                future.result()
            except Exception:
                pass

    end_time = time.time()
    logging.info(f"All fast operations finished successfully in {int(end_time - start_time)} seconds.")


if __name__ == "__main__":
    main()
