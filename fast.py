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
import tkinter.font as tkfont
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

# STABILITY FIX: Hardened explicit absolute path mappings for logging assets
LOG_FILE_PATH = Path("/Users/jasona/account_plan/notebooklm/pipeline_fast_execution.log")
DASHBOARD_PATH = Path("/Users/jasona/account_plan/notebooklm/pipeline_dashboard.html")

# STABILITY FIX: Force physical directory initialization onto local disk to prevent FileHandler initialization crashes
LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

log_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s",
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

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

ui_queue = queue.Queue()
dashboard_lock = threading.Lock()
dashboard_state = {}


def update_dashboard(client_token, step=None, progress=None, status=None):
    """Thread-safe updates to the high-fidelity Red Hat themed visualization layer."""
    client_name = getattr(config, f"{client_token}_name", client_token)
    with dashboard_lock:
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

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Red Hat Systems Engine Console</title>
    <style>
        body {{ font-family: "RedHatText", "Overpass", "Helvetica Neue", Arial, sans-serif; background-color: #0b0d10; color: #f5f5f7; margin: 0; padding: 0; -webkit-font-smoothing: antialiased; }}
        .rh-banner {{ background: linear-gradient(135deg, #151515 0%, #252525 100%); color: #ffffff; padding: 15px 35px; display: flex; align-items: center; justify-content: space-between; border-bottom: 4px solid #cc0000; box-shadow: 0 4px 20px rgba(0,0,0,0.4); }}
        .brand-wrapper {{ display: flex; align-items: center; }}
        .rh-logo-svg {{ height: 45px; width: auto; margin-right: 20px; vertical-align: middle; }}
        .rh-logo {{ font-weight: 800; font-size: 1.5rem; letter-spacing: -0.5px; text-transform: uppercase; display: inline-block; vertical-align: middle; }}
        .rh-logo span {{ color: #cc0000; }}
        .rh-tag {{ background: #cc0000; color: white; font-size: 0.65rem; font-weight: 700; padding: 3px 8px; border-radius: 3px; margin-left: 12px; letter-spacing: 1px; text-transform: uppercase; vertical-align: middle; }}
        .rh-subtitle {{ color: #b8bbbe; font-size: 0.9rem; margin-left: 20px; border-left: 1px solid #4f5255; padding-left: 20px; display: inline-block; vertical-align: middle; }}
        .main-layout {{ max-width: 1100px; margin: 35px auto; padding: 0 25px; }}
        .status-alert {{ background: #151515; border: 1px solid #3c3f42; border-left: 4px solid #cc0000; padding: 18px; border-radius: 4px; margin-bottom: 30px; font-size: 0.92rem; color: #d1d5db; display: flex; justify-content: space-between; align-items: center; }}
        .engine-pulse {{ width: 10px; height: 10px; background-color: #3e8635; border-radius: 50%; display: inline-block; margin-right: 8px; box-shadow: 0 0 8px #3e8635; animation: pulse 2s infinite; }}
        @keyframes pulse {{ 0% {{ opacity: 0.4; }} 50% {{ opacity: 1; }} 100% {{ opacity: 0.4; }} }}
        .grid-container {{ display: grid; grid-gap: 25px; }}
        .rh-card {{ background: #151515; border: 1px solid #2f3133; border-radius: 6px; padding: 24px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); transition: border-color 0.2s ease; }}
        .rh-card:hover {{ border-color: #4f5255; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
        .client-name {{ font-size: 1.25rem; font-weight: 700; color: #ffffff; display: flex; align-items: center; }}
        .client-hash {{ font-family: "Liberation Mono", monospace; font-size: 0.8rem; color: #8a8d90; background: #212427; padding: 3px 8px; border-radius: 4px; margin-left: 12px; border: 1px solid #2f3133; }}
        .progress-track {{ background: #212427; border-radius: 4px; height: 14px; overflow: hidden; margin: 15px 0; border: 1px solid #2f3133; }}
        .progress-fill {{ height: 100%; width: 0%; transition: width 0.6s cubic-bezier(0.16, 1, 0.3, 1); background: linear-gradient(90deg, #cc0000 0%, #ff3333 100%); }}
        .status-pill {{ font-size: 0.75rem; font-weight: 700; padding: 5px 14px; border-radius: 30px; text-transform: uppercase; letter-spacing: 0.75px; box-shadow: inset 0 1px 2px rgba(255,255,255,0.1); }}
        .pill-RUNNING {{ background: rgba(236,122,8,0.15); color: #f4c176; border: 1px solid #ec7a08; }}
        .pill-DEGRADED {{ background: rgba(219, 145, 0, 0.2); color: #ffab40; border: 1px solid #ff9100; }}
        .pill-COMPLETE {{ background: rgba(62,134,53,0.15); color: #8bc34a; border: 1px solid #3e8635; }}
        .pill-FAILED {{ background: rgba(201,25,11,0.15); color: #ff6b6b; border: 1px solid #c9190b; }}
        .pill-PENDING {{ background: #212427; color: #d1d5db; border: 1px solid #4f5255; }}
        .step-log {{ font-size: 0.9rem; color: #d1d5db; margin-top: 10px; display: flex; justify-content: space-between; }}
        .step-log strong {{ color: #ffffff; }}
    </style>
    <script>
        window.addEventListener('DOMContentLoaded', () => {{
            let start = localStorage.getItem('rh_fast_start');
            if (!start) {{
                start = Date.now();
                localStorage.setItem('rh_fast_start', start);
            }}
            let delay = (Date.now() - parseInt(start) < 5000) ? 1000 : 5000;
            setTimeout(() => {{ window.location.reload(); }}, delay);
        }});
    </script>
</head>
<body>
    <div class="rh-banner">
        <div class="brand-wrapper">
            <svg class="rh-logo-svg" viewBox="0 0 128 128" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M113.7 75.3c-1.8-4.5-5.3-8.2-9.6-10.4-1.2-4.8-3.4-9.3-6.6-13.1-4.2-5.1-9.9-8.8-16.3-10.4 1.3-4.8 1.4-9.9.2-14.7C79 17 69.1 11.2 58.7 11.4c-4.9.1-9.6 1.6-13.8 4.2-5.4 3.4-9.3 8.7-10.9 14.8-4.8.9-9.1 3.2-12.5 6.7-4.1 4.2-6.5 9.8-6.9 15.6-2.1.8-4 2-5.5 3.6-2.5 2.7-3.8 6.3-3.6 10 .3 5.4 2.8 10.4 7 13.8 6.2 5.1 14.1 7.8 22.1 7.6 19.3-.5 38.6-.8 57.9-.5 7.1.1 14.2-.9 20.8-3.2 5.6-1.9 10.1-5.9 12.3-11.2 1.4-3.5 1.4-7.3.1-10.7zM58.7 16.4c7.6-.1 14.8 4.2 18.2 11 1 2 1.6 4.2 1.8 6.4-5.3-.9-10.8-1.2-16.2-.9-7.2.4-14.4 1.5-21.4 3.3 1-5 3.8-9.4 7.9-12.4 3.6-2.6 7.9-4.2 12.4-4.2-1.9.1-1.9.1 0 0zm-33.1 42c.2-4.2 1.9-8.2 4.9-11.2 2.6-2.6 6.1-4.2 9.7-4.5 7.4-4.8 16.2-7.5 25.1-8 8-.5 16 .2 23.8 2.1 3.5.9 6.8 2.2 9.9 4 2.6 3.1 4.4 6.8 5.3 10.8-7.5-1.1-15-1.4-22.6-1.1-11.6.5-23 2.7-34.1 6.5-7.7 2.6-15.1 6-22 10.2v-8.8zM92 90.3c-17.7-.3-35.3-.1-53 .4-7.1.2-14.2-.6-21-3.1-2.6-1-4.7-2.9-6-5.3-1.1-2.1-1.4-4.6-1-7 1-6 5-11 10.6-13.3 7.8-4.7 16.2-8.5 24.9-11.4 11-3.6 22.4-5.8 33.9-6.3 7.8-.3 15.6.1 23.3 1.3 5.4.8 10.4 3 14.6 6.4 4 3.3 6.6 8 7.3 13.2.8 5.6-1.1 11.2-5.1 15.1-5.1 4.7-11.8 7.3-18.5 7.4l-.1 2.6z" fill="#CC0000"/>
            </svg>
            <div class="rh-logo">Red Hat <span>Studio</span><span class="rh-tag">Fast</span></div>
            <div class="rh-subtitle">Ecosystem Pipeline Infrastructure Daemon</div>
        </div>
    </div>
    <div class="main-layout">
        <div class="status-alert">
            <span><span class="engine-pulse"></span><strong>Orchestrator Operational Status:</strong> Active thread clusters deploying cloud workspace blueprints.</span>
            <span style="font-size: 0.8rem; color: #8a8d90;">Telemetry Mount: <code>{DASHBOARD_PATH}</code></span>
        </div>
        <div class="grid-container">
    """
        for token, data in dashboard_state.items():
            fill_color = "linear-gradient(90deg, #cc0000 0%, #ff3333 100%)"
            if data["status"] == "COMPLETE": fill_color = "linear-gradient(90deg, #3e8635 0%, #5ba94c 100%)"
            if data["status"] == "FAILED": fill_color = "linear-gradient(90deg, #c9190b 0%, #ef4444 100%)"
            if data["status"] == "RUNNING": fill_color = "linear-gradient(90deg, #ec7a08 0%, #f59e0b 100%)"
            if data["status"] == "DEGRADED": fill_color = "linear-gradient(90deg, #ff9100 0%, #ffab40 100%)"

            html_content += f"""
            <div class="rh-card">
                <div class="card-header">
                    <span class="client-name">{data["name"]} <span class="client-hash">{token}</span></span>
                    <span class="status-pill pill-{data["status"]}">{data["status"]}</span>
                </div>
                <div class="progress-track">
                    <div class="progress-fill" style="width: {data["progress"]}%; background: {fill_color};"></div>
                </div>
                <div class="step-log">
                    <span>Current Execution: <strong>{data["step"]}</strong></span>
                    <span style="color: #8a8d90;">{data["progress"]}%</span>
                </div>
            </div>
        """
        html_content += "</div></div></body></html>"
        try:
            DASHBOARD_PATH.write_text(html_content, encoding="utf-8")
        except IOError:
            pass


def run_cmd(cmd, check=True, text=True, capture_output=False, input_data=None):
    """Executes system commands with safety staggering profiles to prevent API throttling."""
    time.sleep(random.uniform(0.2, 0.5))
    logging.debug(f"Executing command: {' '.join(cmd)}")
    try:
        return subprocess.run(cmd, check=check, text=text, capture_output=capture_output, input=input_data)
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with code {e.returncode}: {' '.join(cmd)}")
        raise e


def fetch_notebook_cache(storage_path=None):
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
            else:
                time.sleep(2.0)
                notebook_cache = fetch_notebook_cache(storage_path=client_storage)
                nb_id = notebook_cache.get(name_value)

            if not nb_id:
                raise Exception(f"Failed to verify notebook creation for: {name_value}")

        update_dashboard(client, step="Workspace Link Ready", progress=15, status="RUNNING")
        return client, name_value, nb_id
    except Exception as e:
        update_dashboard(client, step="Pre-flight configuration error", progress=100, status="FAILED")
        raise e
    finally:
        if client_storage.exists():
            try: client_storage.unlink()
            except Exception: pass


def extract_id_from_google_shortcut(file_path):
    try:
        content = Path(file_path).read_text(errors='ignore')
        if '"doc_id"' in content or '"id"' in content:
            data = json.loads(content)
            doc_id = data.get("doc_id") or data.get("id") or data.get("resource_id")
            if doc_id: return doc_id
        url_match = re.search(r'https://docs\.google\.com/[^/]+/d/([a-zA-Z0-9-_]+)', content)
        if url_match: return url_match.group(1)
    except Exception: pass
    return None


def convert_sheet_shortcut_to_csv_text(file_path, client_storage):
    try:
        import pandas as pd
        csv_path = Path(file_path).with_suffix('.csv')
        if os.path.exists(file_path.replace('.gsheet', '.xlsx')):
            df = pd.read_excel(file_path.replace('.gsheet', '.xlsx'))
            df.to_csv(csv_path, index=False)
            return csv_path
    except Exception: pass
    return None


def request_files_from_main_thread(client_name, timeout_secs=90):
    response_queue = queue.Queue()
    ui_queue.put((client_name, timeout_secs, response_queue))
    return response_queue.get()


def try_upload_local_file_with_fallbacks(client_storage, target_id, source_title, name_value):
    variations = [
        ["notebooklm", "--storage", str(client_storage), "source", "add", "--title", source_title, target_id],
        ["notebooklm", "--storage", str(client_storage), "source", "add", target_id],
    ]
    for cmd in variations:
        try:
            res = run_cmd(cmd, capture_output=True)
            return res.stdout
        except subprocess.CalledProcessError: continue
    return None


def ingest_client_sources(client, shared_auth_path, nb_id):
    client_storage = SCRIPT_DIR / f".storage_ingest_{client}.json"
    temporary_files_to_clean = []
    name_value = getattr(config, f"{client}_name", f"UnknownClient-{client}")
    tracked_tokens = []

    update_dashboard(client, step="Phase 0: Resolving Source Targets", progress=20, status="RUNNING")
    try:
        if shared_auth_path.exists():
            client_storage.write_text(shared_auth_path.read_text())
            time.sleep(random.uniform(0.05, 0.2))

        drive_folder_value = Path(getattr(config, f"{client}_folder")).resolve()
        manually_selected_sources = request_files_from_main_thread(name_value, timeout_secs=90)

        run_cmd(["notebooklm", "--storage", str(client_storage), "auth", "refresh", "--quiet"])
        run_cmd(["notebooklm", "--storage", str(client_storage), "use", nb_id])

        drive_targets = []
        if drive_folder_value.exists() and drive_folder_value.is_dir():
            drive_targets.extend([str(p) for p in drive_folder_value.glob("*") if p.is_file()])
        if manually_selected_sources:
            drive_targets.extend(manually_selected_sources)

        if not drive_targets:
            update_dashboard(client, step="Phase 0: Complete (No assets specified)", progress=40, status="RUNNING")
            return

        update_dashboard(client, step=f"Phase 0: Uploading {len(drive_targets)} items", progress=30, status="RUNNING")

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
                    except subprocess.CalledProcessError: pass
            elif is_local:
                output_text = try_upload_local_file_with_fallbacks(client_storage, target_id, source_title, name_value)
            else:
                try:
                    res = run_cmd(["notebooklm", "--storage", str(client_storage), "source", "add-drive", target_id, source_title], capture_output=True)
                    output_text = res.stdout
                except subprocess.CalledProcessError: pass

            if output_text:
                uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', output_text, re.IGNORECASE)
                wait_target = uuid_match.group(1) if uuid_match else source_title
                tracked_tokens.append(wait_target)

        if tracked_tokens:
            update_dashboard(client, step="Phase 0: Synced batch wait lock clearing...", progress=35, status="RUNNING")
            for token in tracked_tokens:
                try: run_cmd(["notebooklm", "--storage", str(client_storage), "source", "wait", token])
                except subprocess.CalledProcessError: pass

        update_dashboard(client, step="Phase 0: Ingestion Completed", progress=40, status="RUNNING")
    except Exception as e:
        update_dashboard(client, step="Phase 0 Ingestion Failure", progress=100, status="FAILED")
        raise e
    finally:
        if client_storage.exists():
            try: client_storage.unlink()
            except Exception: pass
        for temp_file in temporary_files_to_clean:
            if temp_file.exists():
                try: temp_file.unlink()
                except Exception: pass


def execute_client_prompts(client, sorted_prompt_files, shared_auth_path, nb_id):
    client_storage = SCRIPT_DIR / f".storage_prompts_{client}.json"
    name_value = getattr(config, f"{client}_name", f"UnknownClient-{client}")
    industry_value = getattr(config, f"{client}_industry", "")

    current_run_status = "RUNNING"
    update_dashboard(client, step="Phase 1: Sequential prompting cycle", progress=45, status=current_run_status)
    try:
        if shared_auth_path.exists():
            client_storage.write_text(shared_auth_path.read_text())
            time.sleep(0.1)

        run_cmd(["notebooklm", "--storage", str(client_storage), "use", nb_id])
        output_dir = (SCRIPT_DIR / client).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        for p_idx, prompt_file in enumerate(sorted_prompt_files):
            step_pct = int(45 + ((p_idx / len(sorted_prompt_files)) * 25))
            update_dashboard(client, step=f"Phase 1: Processing {prompt_file.name}", progress=step_pct, status=current_run_status)

            prompt_content = prompt_file.read_text()
            updated_content = prompt_content.replace("$industry", industry_value).replace("$name", name_value)

            gqp = output_dir / prompt_file.name
            gqp.write_text(updated_content)

            temp_prompt_carrier = SCRIPT_DIR / f".temp_prompt_{client}_{prompt_file.name}"
            temp_prompt_carrier.write_text(updated_content, encoding="utf-8")
            
            try:
                if "ask" in gqp.name.lower():
                    logging.info(f"[{name_value}] Initiating fast web research agent loop from prompt file query: {gqp.name}")
                    run_cmd(["notebooklm", "--storage", str(client_storage), "source", "add-research", "--prompt-file", str(temp_prompt_carrier.resolve()), "--no-wait"])

                    timeout_limit = 24  # 24 * 5s = 120s max buffer hold
                    loop_idx = 0
                    research_cleared_cleanly = False
                    
                    while loop_idx < timeout_limit:
                        time.sleep(5.0)
                        status_res = subprocess.run(["notebooklm", "--storage", str(client_storage), "research", "status"], text=True, capture_output=True)
                        status_text = status_res.stdout.upper()

                        if "COMPLETED" in status_text or "IDLE" in status_text:
                            research_cleared_cleanly = True
                            break
                        elif "FAILED" in status_text or "ERROR" in status_text:
                            break
                        loop_idx += 1

                    if research_cleared_cleanly:
                        try: run_cmd(["notebooklm", "--storage", str(client_storage), "research", "wait", "--import-all", "--timeout", "30"])
                        except Exception: pass
                    else:
                        current_run_status = "DEGRADED"
                        update_dashboard(client, step="Phase 1: Web research choked (Using local PDFs)", progress=55, status=current_run_status)
                else:
                    try:
                        run_cmd(["notebooklm", "--storage", str(client_storage), "ask", "--prompt-file", str(temp_prompt_carrier.resolve()), "--save-as-note"])
                    except Exception as ask_err:
                        logging.warning(f"[{name_value}] Prompt note ingestion throttled dynamically: {ask_err}")
            except Exception as inner_e:
                logging.error(f"[{name_value}] Prompt segment execution defect: {inner_e}")
            finally:
                if temp_prompt_carrier.exists():
                    temp_prompt_carrier.unlink()

        update_dashboard(client, step="Phase 1: Prompts processed", progress=70, status=current_run_status)
        return current_run_status
    except Exception as e:
        update_dashboard(client, step="Phase 1 Prompt Processing Defect", progress=100, status="FAILED")
        raise e
    finally:
        if client_storage.exists():
            try: client_storage.unlink()
            except Exception: pass


def clean_duplicate_sources(client, shared_auth_path, nb_id):
    client_storage = SCRIPT_DIR / f".storage_clean_{client}.json"
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
                except subprocess.CalledProcessError: pass

        update_dashboard(client, step="Phase 2: Registry Deduplicated", progress=80, status="RUNNING")
    except Exception as e:
        update_dashboard(client, step="Phase 2 Cleanup Failure", progress=100, status="FAILED")
        raise e
    finally:
        if client_storage.exists():
            try: client_storage.unlink()
            except Exception: pass


def combine_notes_in_cloud(client, shared_auth_path, nb_id):
    """PHASE 2.5: Fetches all generated analysis notes inside the workspace and compiles them into a Master_Account_Plan note item inside the live cloud platform."""
    client_storage = SCRIPT_DIR / f".storage_cloud_combine_{client}.json"
    human_name = getattr(config, f"{client}_name", client)
    update_dashboard(client, step="Phase 2.5: Initializing Cloud Note Combination Layer", progress=82, status="RUNNING")
    try:
        if shared_auth_path.exists():
            client_storage.write_text(shared_auth_path.read_text())
            time.sleep(0.1)

        run_cmd(["notebooklm", "--storage", str(client_storage), "use", nb_id])
        list_res = run_cmd(["notebooklm", "--storage", str(client_storage), "note", "list"], capture_output=True)
        uuid_pattern = re.compile(r'^[a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12}$', re.IGNORECASE)
        
        note_ids = []
        for line in list_res.stdout.splitlines():
            parts = line.replace("│", "").replace("┃", "").strip().split()
            if parts and uuid_pattern.match(parts[0]):
                note_ids.append(parts[0])
                
        if not note_ids:
            logging.warning(f"[{human_name}] No matching note structures discovered to synthesize inside cloud lanes.")
            return

        compiled_cloud_content = f"=== UNIFIED MASTER STRATEGIC ACCOUNT PLAN ENGINE ===\\n"
        compiled_cloud_content += f"Account Identification Target: {human_name}\\n\\n"

        for idx, note_id in enumerate(note_ids):
            try:
                view_res = run_cmd(["notebooklm", "--storage", str(client_storage), "note", "view", note_id], capture_output=True)
                # Clean and sanitize the layout data payload string structure for dynamic input injection tracks
                escaped_note_body = view_res.stdout.replace('"', '\\"').replace("'", "\\'").replace("\n", "\\n")
                compiled_cloud_content += f"--- STRATEGIC OBJECTIVE CHAPTER {idx + 1} ---\\n{escaped_note_body}\\n\\n"
            except Exception:
                pass

        # SYSTEM UPGRADE: Upload the synthesized strategic notes context layer cleanly back into NotebookLM as an absolute native text file option tracking note element
        run_cmd(["notebooklm", "--storage", str(client_storage), "ask", f"Save the following text precisely as a single note titled 'Master_Account_Plan': {compiled_cloud_content}", "--save-as-note"])
        logging.info(f"[{human_name}] Master_Account_Plan note successfully created inside cloud workspace registry.")
        update_dashboard(client, step="Phase 2.5: Cloud Master Note Synthesized", progress=86, status="RUNNING")
        
    except Exception as e:
        logging.error(f"[{human_name}] Error synthesizing unified cloud workspace note structure: {e}")
    finally:
        if client_storage.exists():
            try: client_storage.unlink()
            except Exception: pass


def post_process_assets(client, shared_auth_path, nb_id):
    """Fault-Tolerant Dynamic Asset Generation Block."""
    client_storage = SCRIPT_DIR / f".storage_asset_{client}.json"
    update_dashboard(client, step="Phase 3: Dynamic Asset Compilation", progress=88, status="RUNNING")
    try:
        if shared_auth_path.exists():
            client_storage.write_text(shared_auth_path.read_text())
            time.sleep(0.1)

        run_cmd(["notebooklm", "--storage", str(client_storage), "use", nb_id])
        generation_commands = [
            (["mind-map"], "Mind Map Generation"),
            (["data-table", "compare key concepts"], "Tabular Matrix Definition"),
            (["slide-deck"], "Executive Slide Deck Representation")
        ]

        for sub_args, label in generation_commands:
            try:
                cmd = ["notebooklm", "--storage", str(client_storage), "generate"] + sub_args
                run_cmd(cmd, check=True)
                time.sleep(1.0)
            except subprocess.CalledProcessError as gen_err:
                logging.warning(f"[{client}] Optional layout asset generation trace throttled: {gen_err}")

    except Exception as e:
        logging.error(f"[{client}] Phase 3 Asset Compilation Defect: {e}")
    finally:
        if client_storage.exists():
            try: client_storage.unlink()
            except Exception: pass


def consolidate_workspace_notes(client, shared_auth_path, nb_id, current_run_status):
    """PHASE 4: Fetches all compiled note assets within a workspace and synthesizes them into a unified markdown file."""
    client_storage = SCRIPT_DIR / f".storage_consolidate_{client}.json"
    human_name = getattr(config, f"{client}_name", client)
    output_plan_path = (SCRIPT_DIR / client / "Account_Plan_2026.md").resolve()

    update_dashboard(client, step="Phase 4: Compiling Consolidated Master Account Plan", progress=95, status=current_run_status)
    try:
        if shared_auth_path.exists():
            client_storage.write_text(shared_auth_path.read_text())
            time.sleep(0.1)

        run_cmd(["notebooklm", "--storage", str(client_storage), "use", nb_id])
        list_res = run_cmd(["notebooklm", "--storage", str(client_storage), "note", "list"], capture_output=True)
        uuid_pattern = re.compile(r'^[a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12}$', re.IGNORECASE)

        master_document_content = f"# Strategic Master Account Plan (2026 Revision)\n"
        master_document_content += f"**Target Organization Account Profile:** {human_name}\n"
        if current_run_status == "DEGRADED":
            master_document_content += f"> **Operational Warning Note:** Web compilation layers throttled during execution. Generation grounded strictly in localized source documentation arrays.\n"
        master_document_content += f"---\n\n"

        for line in list_res.stdout.splitlines():
            parts = line.replace("│", "").replace("┃", "").strip().split()
            if parts and uuid_pattern.match(parts[0]):
                try:
                    view_res = run_cmd(["notebooklm", "--storage", str(client_storage), "note", "view", parts[0]], capture_output=True)
                    master_document_content += f"## Analysis Segment\n```text\n{view_res.stdout.strip()}\n```\n\n"
                    time.sleep(0.2)
                except Exception: pass

        output_plan_path.parent.mkdir(parents=True, exist_ok=True)
        output_plan_path.write_text(master_document_content, encoding="utf-8")
        logging.info(f"[{human_name}] Consolidated execution plan written: {output_plan_path}")
        
        final_status = "COMPLETE" if current_run_status == "RUNNING" else "DEGRADED"
        update_dashboard(client, step="Pipeline Finished Successfully", progress=100, status=final_status)
    except Exception as e:
        logging.error(f"[{human_name}] Error compiling multi-note strategy file: {e}")
        update_dashboard(client, step="Phase 4 Strategy Generation Defect", progress=100, status="FAILED")
    finally:
        if client_storage.exists():
            try: client_storage.unlink()
            except Exception: pass


def main():
    start_time = time.time()

    try:
        run_cmd(["notebooklm", "login"])
    except Exception:
        logging.critical("Initial authentication loop dropped. Script termination invoked.")
        sys.exit(1)

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    shared_auth_path = Path.home() / ".notebooklm" / "profiles" / "default" / "storage_state.json"
    if not shared_auth_path.exists():
        shared_auth_path = Path.home() / ".notebooklm" / "storage_state.json"

    clients = getattr(config, "clients", [])
    raw_prompt_files = [Path(f) for f in glob.glob(str(SCRIPT_DIR / "*prompt*.txt")) if Path(f).is_file()]

    if not raw_prompt_files or not clients:
        logging.warning("No operational assets found inside variables definitions.")
        return

    ask_files = [f for f in raw_prompt_files if "ask" in f.name.lower()]
    other_files = [f for f in raw_prompt_files if "ask" not in f.name.lower()]
    sorted_prompt_files = sorted(ask_files) + sorted(other_files)

    # --- STEP 1: PRE-CREATE/VERIFY NOTEBOOKS CONCURRENTLY ---
    logging.info(f"Starting Pre-Flight Phase: Verifying/Creating notebooks for all {len(clients)} clients...")
    master_notebook_cache = {}

    with ThreadPoolExecutor(max_workers=min(8, len(clients))) as executor:
        notebook_futures = [executor.submit(ensure_notebook_exists, client, shared_auth_path) for client in clients]
        for future in as_completed(notebook_futures):
            try:
                res = future.result()
                if res: master_notebook_cache[res[0]] = res[2]
            except Exception: pass

    os.environ['rh_fast_start'] = str(int(time.time() * 1000))
    for client in clients:
        update_dashboard(client, step="Pre-flight validation finished. Routing to thread blocks.", progress=15, status="PENDING")

    try: webbrowser.open(DASHBOARD_PATH.as_uri())
    except Exception: pass

    logging.info("Notebook validation barrier cleared successfully. Spawning background ingestion streams...")
    time.sleep(2.0)

    # --- STEP 2: SPIN UP PIPELINE INGESTION BACKGROUND WORKERS ---
    MAX_WORKERS = min(8, len(clients))
    ingest_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    futures = [
        ingest_executor.submit(ingest_client_sources, client, shared_auth_path, master_notebook_cache[client])
        for client in clients if client in master_notebook_cache
    ]

    completed_count = 0
    total_expected = len(futures)

    while completed_count < total_expected:
        try:
            client_name, timeout_secs, response_queue = ui_queue.get(timeout=1.0)
            selected_assets = []

            def handle_timeout():
                dialog_window.destroy()
                response_queue.put([])

            dialog_window = tk.Toplevel(root)
            dialog_window.withdraw()

            bold_font = tkfont.Font(family="Helvetica", size=14, weight="bold")

            label = tk.Label(
                dialog_window,
                text=f"Target Client Profile Context: {client_name}",
                font=bold_font,
                fg="#CC0000",
                padx=20,
                pady=15
            )
            label.pack()

            dialog_window.after(timeout_secs * 1000, handle_timeout)

            files = filedialog.askopenfilenames(
                parent=dialog_window,
                title=f"Select Structural Content Assets for: {client_name}",
                filetypes=[("Supported Context Materials", "*.pdf *.txt *.docx *.gdoc *.gsheet"), ("All Files", "*.*")]
            )
            if files: selected_assets.extend(list(files))
            dialog_window.destroy()
            response_queue.put(selected_assets)
        except queue.Empty:
            completed_count = len([f for f in futures if f.done()])
            continue

    ingest_executor.shutdown(wait=True)

    # Sequence Client Lifecycle Phases Sequentially Across Threads but isolated per client space profiles safely
    client_degraded_states = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as prompt_executor:
        prompt_futures = {
            prompt_executor.submit(execute_client_prompts, client, sorted_prompt_files, shared_auth_path, master_notebook_cache[client]): client
            for client in clients if client in master_notebook_cache
        }
        for future in as_completed(prompt_futures):
            c_tok = prompt_futures[future]
            try: client_degraded_states[c_tok] = future.result()
            except Exception: client_degraded_states[c_tok] = "RUNNING"

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        clean_futures = [
            executor.submit(clean_duplicate_sources, client, shared_auth_path, master_notebook_cache[client])
            for client in clients if client in master_notebook_cache
        ]
        for future in as_completed(clean_futures): pass

    # --- REGISTRY REQUIREMENT: Dynamic Cloud Synthesis Integration Trigger Phase ---
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as combine_executor:
        combine_futures = [
            combine_executor.submit(combine_notes_in_cloud, client, shared_auth_path, master_notebook_cache[client])
            for client in clients if client in master_notebook_cache
        ]
        for future in as_completed(combine_futures): pass

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        assets_futures = [
            executor.submit(post_process_assets, client, shared_auth_path, master_notebook_cache[client])
            for client in clients if client in master_notebook_cache
        ]
        for future in as_completed(assets_futures): pass

    # --- STEP 3: CONCURRENT STRATEGIC NOTE SYNTHESIS CONSOLIDATION (PHASE 4) ---
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        consolidation_futures = [
            executor.submit(consolidate_workspace_notes, client, shared_auth_path, master_notebook_cache[client], client_degraded_states.get(client, "RUNNING"))
            for client in clients if client in master_notebook_cache
        ]
        for future in as_completed(consolidation_futures): pass

    end_time = time.time()
    logging.info(f"Fast execution completed inside {int(end_time - start_time)} seconds.")


if __name__ == "__main__":
    main()
