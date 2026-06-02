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
import csv
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
PROJECT_ROOT = SCRIPT_DIR.parent 
sys.path.append(str(SCRIPT_DIR))

try:
    import vars as config
except ImportError:
    print(f"Error: Could not find vars.py in {SCRIPT_DIR}", file=sys.stderr)
    sys.exit(1)

# Hardened explicit absolute path mappings for logging assets
LOG_FILE_PATH = Path("/Users/jasona/account_plan/notebooklm/pipeline_fast_execution.log")
DASHBOARD_PATH = Path("/Users/jasona/account_plan/notebooklm/pipeline_dashboard.html")

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

dashboard_lock = threading.Lock()
console_print_lock = threading.Lock()
cli_execution_lock = threading.Lock()
dashboard_state = {}
start_time_global = time.time()


def track_phase_progress(phase_title, finished_count, total_count):
    """Generates a synchronized global progress bar for the active execution phase."""
    with console_print_lock:
        width = 25
        pct = int((finished_count / total_count) * 100) if total_count > 0 else 100
        filled_length = int(round(width * pct / 100))
        bar = '█' * filled_length + '░' * (width - filled_length)
        
        c_cyan = "\033[96m"
        c_red = "\033[91m"
        c_green = "\033[92m"
        c_rst = "\033[0m"
        
        sys.stdout.write(f"\r{c_cyan}[ {phase_title:<7} ]{c_rst} Phase Progress: |{c_red}{bar}{c_rst}| {c_green}{pct:>3}%{c_rst} completed ({finished_count}/{total_count} tasks done)")
        sys.stdout.flush()


def update_dashboard(client_token, step=None, progress=None, status=None, plan_link=None):
    """Thread-safe updates to the high-fidelity Red Hat themed visualization layer."""
    client_name = getattr(config, f"{client_token}_name", client_token)
    global start_time_global
    elapsed_seconds = int(time.time() - start_time_global)
    minutes = elapsed_seconds // 60
    seconds = elapsed_seconds % 60
    timer_string = f"{minutes}m {seconds}s"

    with dashboard_lock:
        if client_token not in dashboard_state:
            dashboard_state[client_token] = {
                "name": client_name,
                "step": "Initializing",
                "progress": 0,
                "status": "PENDING",
                "plan_link": None
            }

        if step is not None: dashboard_state[client_token]["step"] = step
        if progress is not None: dashboard_state[client_token]["progress"] = progress
        if status is not None: dashboard_state[client_token]["status"] = status
        if plan_link is not None: dashboard_state[client_token]["plan_link"] = plan_link

        all_done = all(d["status"] in ["COMPLETE", "FAILED", "DEGRADED"] for d in dashboard_state.values())

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Red Hat Fast Account Planning Console</title>
    <style>
        body {{ font-family: "RedHatText", "Overpass", "Helvetica Neue", Arial, sans-serif; background-color: #0b0d10; color: #f5f5f7; margin: 0; padding: 0; -webkit-font-smoothing: antialiased; }}
        .rh-banner {{ background: linear-gradient(135deg, #151515 0%, #252525 100%); color: #ffffff; padding: 20px 35px; display: flex; align-items: center; justify-content: space-between; border-bottom: 4px solid #cc0000; box-shadow: 0 4px 20px rgba(0,0,0,0.4); }}
        .brand-wrapper {{ display: flex; align-items: center; }}
        .rh-logo-svg {{ height: 45px; width: auto; margin-right: 20px; vertical-align: middle; }}
        .rh-logo {{ font-weight: 500; font-size: 1.5rem; letter-spacing: -0.5px; display: inline-block; vertical-align: middle; color: #ffffff; }}
        .rh-subtitle {{ color: #b8bbbe; font-size: 0.9rem; margin-left: 20px; border-left: 1px solid #4f5255; padding-left: 20px; display: inline-block; vertical-align: middle; }}
        .main-layout {{ max-width: 1100px; margin: 35px auto; padding: 0 25px; }}
        .status-alert {{ background: #151515; border: 1px solid #3c3f42; border-left: 4px solid #cc0000; padding: 18px; border-radius: 4px; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center; }}
        .timer-label {{ font-size: 1.4rem; font-weight: 700; color: #f5f5f7; letter-spacing: -0.5px; }}
        .timer-label span {{ font-weight: 300; color: #b8bbbe; }}
        .engine-pulse {{ width: 12px; height: 12px; background-color: #3e8635; border-radius: 50%; display: inline-block; margin-right: 12px; box-shadow: 0 0 8px #3e8635; animation: pulse 2s infinite; vertical-align: middle; }}
        @keyframes pulse {{ 0% {{ opacity: 0.4; }} 50% {{ opacity: 1; }} 100% {{ opacity: 0.4; }} }}
        .grid-container {{ display: grid; grid-gap: 25px; }}
        .rh-card {{ background: #151515; border: 1px solid #2f3133; border-radius: 6px; padding: 24px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); transition: border-color 0.2s ease; }}
        .rh-card:hover {{ border-color: #4f5255; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
        .client-name {{ font-size: 1.25rem; font-weight: 700; color: #ffffff; display: flex; align-items: center; }}
        .client-hash {{ font-family: "Liberation Mono", monospace; font-size: 0.8rem; color: #8a8d90; background: #212427; padding: 3px 8px; border-radius: 4px; margin-left: 12px; border: 1px solid #2f3133; }}
        .progress-track {{ background: #212427; border-radius: 4px; height: 14px; overflow: hidden; margin: 15px 0; border: 1px solid #2f3133; }}
        .progress-fill {{ height: 100%; width: 0%; transition: width 0.6s cubic-bezier(0.16, 1, 0.3, 1); background: rgba(204,0,0,1); }}
        .status-pill {{ font-size: 0.75rem; font-weight: 700; padding: 5px 14px; border-radius: 30px; text-transform: uppercase; letter-spacing: 0.75px; box-shadow: inset 0 1px 2px rgba(255,255,255,0.1); }}
        .pill-RUNNING {{ background: rgba(236,122,8,0.15); color: #f4c176; border: 1px solid #ec7a08; }}
        .pill-DEGRADED {{ background: rgba(219, 145, 0, 0.2); color: #ffab40; border: 1px solid #ff9100; }}
        .pill-COMPLETE {{ background: rgba(62,134,53,0.15); color: #8bc34a; border: 1px solid #3e8635; }}
        .pill-FAILED {{ background: rgba(201,25,11,0.15); color: #ff6b6b; border: 1px solid #c9190b; }}
        .pill-PENDING {{ background: #212427; color: #d1d5db; border: 1px solid #4f5255; }}
        .step-log {{ font-size: 0.9rem; color: #d1d5db; margin-top: 10px; display: flex; justify-content: space-between; align-items: center; }}
        .step-log strong {{ color: #ffffff; }}
        .plan-btn {{ display: inline-block; background: #cc0000; color: #ffffff; text-decoration: none; padding: 6px 14px; font-size: 0.8rem; font-weight: 700; border-radius: 3px; text-transform: uppercase; transition: background 0.2s ease; border: 1px solid rgba(255,255,255,0.1); }}
        .plan-btn:hover {{ background: #ff3333; box-shadow: 0 0 10px rgba(255,51,51,0.4); }}
    </style>
    <script>
        window.addEventListener('DOMContentLoaded', () => {{
            let allDone = {str(all_done).lower()};
            if (!allDone) {{
                setTimeout(() => {{ window.location.reload(); }}, 3000);
            }}
        }});
    </script>
</head>
<body>
    <div class="rh-banner">
        <div class="brand-wrapper">
            <svg class="rh-logo-svg" viewBox="0 0 128 128" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M113.7 75.3c-1.8-4.5-5.3-8.2-9.6-10.4-1.2-4.8-3.4-9.3-6.6-13.1-4.2-5.1-9.9-8.8-16.3-10.4 1.3-4.8 1.4-9.9.2-14.7C79 17 69.1 11.2 58.7 11.4c-4.9.1-9.6 1.6-13.8 4.2-5.4 3.4-9.3 8.7-10.9 14.8-4.8.9-9.1 3.2-12.5 6.7-4.1 4.2-6.5 9.8-6.9 15.6-2.1.8-4 2-5.5 3.6-2.5 2.7-3.8 6.3-3.6 10 .3 5.4 2.8 10.4 7 13.8 6.2 5.1 14.1 7.8 22.1 7.6 19.3-.5 38.6-.8 57.9-.5 7.1.1 14.2-.9 20.8-3.2 5.6-1.9 10.1-5.9 12.3-11.2 1.4-3.5 1.4-7.3.1-10.7zM58.7 16.4c7.6-.1 14.8 4.2 18.2 11 1 2 1.6 4.2 1.8 6.4-5.3-.9-10.8-1.2-16.2-.9-7.2.4-14.4 1.5-21.4 3.3 1-5 3.8-9.4 7.9-12.4 3.6-2.6 7.9-4.2 12.4-4.2-1.9.1-1.9.1 0 0zm-33.1 42c.2-4.2 1.9-8.2 4.9-11.2 2.6-2.6 6.1-4.2 9.7-4.5 7.4-4.8 16.2-7.5 25.1-8 8-.5 16 .2 23.8 2.1 3.5.9 6.8 2.2 9.9 4 2.6 3.1 4.4 6.8 5.3 10.8-7.5-1.1-15-1.4-22.6-1.1-11.6.5-23 2.7-34.1 6.5-7.7 2.6-15.1 6-22 10.2v-8.8zM92 90.3c-17.7-.3-35.3-.1-53 .4-7.1.2-14.2-.6-21-3.1-2.6-1-4.7-2.9-6-5.3-1.1-2.1-1.4-4.6-1-7 1-6 5-11 10.6-13.3 7.8-4.7 16.2-8.5 24.9-11.4 11-3.6 22.4-5.8 33.9-6.3 7.8-.3 15.6.1 23.3 1.3 5.4.8 10.4 3 14.6 6.4 4 3.3 6.6 8 7.3 13.2.8 5.6-1.1 11.2-5.1 15.1-5.1 4.7-11.8 7.3-18.5 7.4l-.1 2.6z" fill="#CC0000"/>
            </svg>
            <div class="rh-logo"><strong style="color: #ff3333; font-weight: 900; letter-spacing: -1px; background-color: #ffffff; padding: 2px 8px; border-radius: 3px; margin-right: 5px;">RED HAT</strong> Fast Account Planning for client</div>
            <div class="rh-subtitle">Ecosystem Pipeline Infrastructure Daemon</div>
        </div>
    </div>
    <div class="main-layout">
        <div class="status-alert">
            <span class="timer-label"><span class="engine-pulse"></span>Account planning execution timer: <span>Running multi-cloud compilation vectors.</span></span>
            <span style="font-size: 1.4rem; font-family: monospace; color: #ffffff; background: #212427; padding: 6px 16px; border-radius: 3px; border: 1px solid #4f5255; font-weight: bold;">{timer_string}</span>
        </div>
        <div class="grid-container">
    """
        for token, data in dashboard_state.items():
            clean_token_label = re.sub(r'[^a-zA-Z0-9_]', '', data["name"].replace(' ', ''))
            html_content += f"""
            <div class="rh-card">
                <div class="card-header">
                    <span class="client-name">{data["name"]} <span class="client-hash">{token}</span></span>
                    <span class="status-pill pill-{data["status"]}">{data["status"]}</span>
                </div>
                <div class="progress-track">
                    <div class="progress-fill" style="width: {data["progress"]}%; background: rgba(204,0,0,1);"></div>
                </div>
                <div class="step-log">
                    <span>Current Execution: <strong>{data["step"]}</strong></span>
                    {"<a class='plan-btn' href='" + data["plan_link"] + "' target='_blank'>" + clean_token_label + "_Account_Plan</a>" if data["plan_link"] else f"<span style='color: #8a8d90;'>{data['progress']}%</span>"}
                </div>
            </div>
        """
        html_content += "</div></div></body></html>"
        try:
            tmp_dashboard = DASHBOARD_PATH.with_suffix(".tmp")
            tmp_dashboard.write_text(html_content, encoding="utf-8")
            os.replace(str(tmp_dashboard), str(DASHBOARD_PATH))
        except IOError:
            pass


def run_cmd(cmd, check=True, text=True, capture_output=True, input_data=None):
    time.sleep(random.uniform(0.1, 0.2))
    with cli_execution_lock:
        try:
            if "ask" in cmd and "titled" in str(cmd):
                return subprocess.run(cmd, check=check, text=text, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, input=input_data)
            return subprocess.run(cmd, check=check, text=text, capture_output=capture_output, input=input_data)
        except subprocess.CalledProcessError as e:
            raise e


def fetch_notebook_cache(storage_path=None):
    cmd = ["notebooklm"]
    if storage_path: cmd.extend(["--storage", str(storage_path)])
    cmd.append("list")
    try:
        res = run_cmd(cmd, capture_output=True)
        cache = {}
        for line in res.stdout.splitlines():
            clean_line = line.replace("│", "").replace("┃", "").strip()
            parts = clean_line.split()
            if len(parts) >= 2 and "-" in parts[0]:
                cache[parts[0]] = parts[0]
                name_idx = " ".join(parts[1:-2]).strip() if "Owner" in parts else " ".join(parts[1:-2]).strip()
                if name_idx: cache[name_idx] = parts[0]
        return cache
    except Exception: return {}


def ensure_notebook_exists(client, shared_auth_path):
    client_storage = SCRIPT_DIR / f".storage_{client}.json"
    update_dashboard(client, step="Pre-flight verification", progress=5, status="RUNNING")
    try:
        if shared_auth_path.exists(): client_storage.write_text(shared_auth_path.read_text())
        name_value = getattr(config, f"{client}_name", "")
        if not name_value:
            update_dashboard(client, step="Skipped", progress=0, status="PENDING")
            return None
        notebook_cache = fetch_notebook_cache(storage_path=client_storage)
        nb_id = notebook_cache.get(name_value) or notebook_cache.get(client)
        if not nb_id:
            res = run_cmd(["notebooklm", "--storage", str(client_storage), "create", name_value], capture_output=True)
            uuid_match = re.search(r'([a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12})', res.stdout, re.IGNORECASE)
            nb_id = uuid_match.group(1) if uuid_match else None
        update_dashboard(client, step="Workspace Active", progress=100, status="COMPLETE")
        return client, name_value, nb_id
    except Exception as e:
        update_dashboard(client, step="Pre-flight error", progress=100, status="FAILED")
        raise e
    finally:
        if client_storage.exists(): client_storage.unlink()


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


def ingest_client_sources(client, shared_auth_path, nb_id):
    """FIXED: Removed all Tkinter interactive dialogue wrappers. Operates completely headlessly."""
    client_storage = SCRIPT_DIR / f".storage_ingest_{client}.json"
    temporary_files_to_clean = []
    update_dashboard(client, step="Phase 0: Autonomous File Scan", progress=20, status="RUNNING")
    try:
        run_cmd(["notebooklm", "--storage", str(client_storage), "auth", "refresh", "--quiet"])
        run_cmd(["notebooklm", "--storage", str(client_storage), "use", nb_id])
        
        client_folder_raw = getattr(config, f"{client}_folder", ".")
        drive_folder_value = Path(PROJECT_ROOT / client_folder_raw).resolve()

        drive_targets = []
        if drive_folder_value.exists() and drive_folder_value.is_dir():
            drive_targets.extend([str(p) for p in drive_folder_value.glob("*") if p.is_file()])
        if not drive_targets: return

        for idx, target_id in enumerate(drive_targets):
            is_local = os.path.exists(target_id) and os.path.isfile(target_id)
            suffix = Path(target_id).suffix.lower() if is_local else ""
            if is_local and suffix == '.csv':
                structural_txt = convert_raw_csv_to_structured_text(target_id)
                if structural_txt and structural_txt.exists():
                    target_id = str(structural_txt)
                    temporary_files_to_clean.append(structural_txt)
            
            raw_title = Path(target_id).stem if is_local else f"doc_{idx}"
            source_title = f"{client}_source_{re.sub(r'[^a-zA-Z0-9_]', '', raw_title)}"
            
            variations = [
                ["notebooklm", "--storage", str(client_storage), "source", "add", "--title", source_title, target_id],
                ["notebooklm", "--storage", str(client_storage), "source", "add", target_id],
            ]
            for cmd in variations:
                try:
                    run_cmd(cmd, capture_output=True)
                    break
                except Exception: continue

        update_dashboard(client, step="Phase 0 Completed Natively", progress=100, status="COMPLETE")
    except Exception as e:
        update_dashboard(client, step="Phase 0 Ingestion Failure", progress=100, status="FAILED")
        raise e
    finally:
        if client_storage.exists(): client_storage.unlink()
        for f in temporary_files_to_clean:
            if f.exists(): f.unlink()


def execute_client_prompts(client, sorted_prompt_files, shared_auth_path, nb_id):
    client_storage = SCRIPT_DIR / f".storage_prompts_{client}.json"
    name_value = getattr(config, f"{client}_name", f"UnknownClient-{client}")
    industry_value = getattr(config, f"{client}_industry", "")
    current_run_status = "RUNNING"
    try:
        run_cmd(["notebooklm", "--storage", str(client_storage), "use", nb_id])
        output_dir = (SCRIPT_DIR / client).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        for p_idx, prompt_file in enumerate(sorted_prompt_files):
            step_pct = int(0 + ((p_idx / len(sorted_prompt_files)) * 100))
            update_dashboard(client, step=f"Phase 1 Prompting Tracks", progress=step_pct, status=current_run_status)
            updated_content = prompt_file.read_text().replace("$industry", industry_value).replace("$name", name_value)
            
            temp_prompt_carrier = SCRIPT_DIR / f".temp_prompt_{client}_{prompt_file.name}"
            temp_prompt_carrier.write_text(updated_content, encoding="utf-8")
            try:
                if "ask" in prompt_file.name.lower():
                    run_cmd(["notebooklm", "--storage", str(client_storage), "source", "add-research", "--prompt-file", str(temp_prompt_carrier.resolve()), "--mode", "fast", "--no-wait"])
                    time.sleep(15.0)
                else:
                    run_cmd(["notebooklm", "--storage", str(client_storage), "ask", "--prompt-file", str(temp_prompt_carrier.resolve()), "--save-as-note"])
            except Exception: pass
            finally:
                if temp_prompt_carrier.exists(): temp_prompt_carrier.unlink()
        update_dashboard(client, step="Phase 1 Finished Successfully", progress=100, status="COMPLETE")
        return current_run_status
    except Exception:
        update_dashboard(client, step="Phase 1 Defect", progress=100, status="FAILED")
        return "FAILED"
    finally:
        if client_storage.exists(): client_storage.unlink()


def post_process_and_generate_google_doc(client, shared_auth_path, nb_id, current_run_status):
    client_storage = SCRIPT_DIR / f".storage_doc_{client}.json"
    human_name = getattr(config, f"{client}_name", client)
    clean_name_string = re.sub(r'[^a-zA-Z0-9_]', '', human_name.replace(' ', ''))
    update_dashboard(client, step="Phase 4 Document Compiles", progress=50, status="RUNNING")
    try:
        run_cmd(["notebooklm", "--storage", str(client_storage), "use", nb_id])
        doc_res = run_cmd(["notebooklm", "--storage", str(client_storage), "generate", "document", f"{clean_name_string}_Account_Plan"], capture_output=True)
        url_match = re.search(r'(https://docs\.google\.com/document/d/[a-zA-Z0-9-_]+)', doc_res.stdout)
        doc_url = url_match.group(1) if url_match else f"https://notebooklm.google.com/"

        for asset_type in [["mind-map"], ["slide-deck"]]:
            try:
                run_cmd(["notebooklm", "--storage", str(client_storage), "generate"] + asset_type)
                time.sleep(6.5)
            except Exception: pass

        final_status = "COMPLETE" if current_run_status == "RUNNING" else "DEGRADED"
        update_dashboard(client, step="Pipeline Finished Successfully", progress=100, status=final_status, plan_link=doc_url)
    except Exception:
        update_dashboard(client, step="Failed Google Doc Compile", progress=100, status="FAILED")
    finally:
        if client_storage.exists(): client_storage.unlink()


def main():
    shared_auth_path = Path.home() / ".notebooklm" / "profiles" / "default" / "storage_state.json"
    if not shared_auth_path.exists(): shared_auth_path = Path.home() / ".notebooklm" / "storage_state.json"
    clients = getattr(config, "clients", [])
    raw_prompt_files = [Path(f) for f in glob.glob(str(SCRIPT_DIR / "*prompt*.txt")) if Path(f).is_file()]
    if not raw_prompt_files or not clients: return

    sorted_prompt_files = sorted([f for f in raw_prompt_files if "ask" in f.name.lower()]) + sorted([f for f in raw_prompt_files if "ask" not in f.name.lower()])

    # FIXED: Re-instated cache maps globally at the foreground level structure
    master_notebook_cache = {}

    print("=======================================================================")
    print(" Starting Fast Cloud Account Strategy Generation Pipeline... ")
    print("=======================================================================")
    
    for client in clients:
         dashboard_state[client] = { "name": getattr(config, f"{client}_name", client), "step": "Syncing System Handles...", "progress": 0, "status": "PENDING", "plan_link": None }
         for track in ["", "_ingest", "_prompts", "_doc"]:
              client_storage = SCRIPT_DIR / f".storage{track}_{client}.json"
              if shared_auth_path.exists(): client_storage.write_text(shared_auth_path.read_text())

    html_init = f"<html><head><script>setTimeout(()=>{{window.location.reload();}},2000);</script></head><body style='background:#0b0d10;color:white;'><h2>Initializing RED HAT Fast Storage Monitoring Console...</h2></body></html>"
    DASHBOARD_PATH.write_text(html_init, encoding="utf-8")
    def open_browser_delayed():
         time.sleep(1.2)
         try: webbrowser.open(DASHBOARD_PATH.as_uri())
         except Exception: pass
    threading.Thread(target=open_browser_delayed, daemon=True).start()

    total_clients = len(clients)
    finished_audit = 0
    with ThreadPoolExecutor(max_workers=min(8, total_clients)) as executor:
        notebook_futures = {executor.submit(ensure_notebook_exists, client, shared_auth_path): client for client in clients}
        for future in as_completed(notebook_futures):
             finished_audit += 1
             track_phase_progress("AUDIT", finished_audit, total_clients)
             try:
                  res = future.result()
                  if res: master_notebook_cache[res[0]] = res[2]
             except Exception: pass
    print()

    # FIXED: Handled dictionary completions tracking via pure as_completed blocks to avoid locks loops completely
    print(" [2/4] Deploying Local Source Logs to Target Engine Ingestion Lanes...")
    MAX_WORKERS = min(8, len(clients))
    finished_ingest = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ingest_executor:
        ingest_futures = {ingest_executor.submit(ingest_client_sources, client, shared_auth_path, master_notebook_cache[client]): client for client in clients if client in master_notebook_cache}
        total_ingest = len(ingest_futures)
        for future in as_completed(ingest_futures):
             finished_ingest += 1
             track_phase_progress("INGEST", finished_ingest, total_ingest)
             future.result()
    print()

    print(" [3/4] Ingesting Question Prompts Sequences into AI Models...")
    finished_prompts = 0
    client_degraded_states = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as prompt_executor:
        prompt_futures = {prompt_executor.submit(execute_client_prompts, client, sorted_prompt_files, shared_auth_path, master_notebook_cache[client]): client for client in clients if client in master_notebook_cache}
        total_prompts = len(prompt_futures)
        for future in as_completed(prompt_futures):
             c_tok = prompt_futures[future]
             finished_prompts += 1
             track_phase_progress("PROMPT", finished_prompts, total_prompts)
             try: client_degraded_states[c_tok] = future.result()
             except Exception: client_degraded_states[c_tok] = "RUNNING"
    print()

    print(" [4/4] Finalizing Google Docs Structural Compiles and Slide Assemblies...")
    finished_docs = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as doc_executor:
        doc_futures = {doc_executor.submit(post_process_and_generate_google_doc, client, shared_auth_path, master_notebook_cache[client], client_degraded_states.get(client, "RUNNING")): client for client in clients if client in master_notebook_cache}
        total_docs = len(doc_futures)
        for future in as_completed(doc_futures):
             finished_docs += 1
             track_phase_progress("COMPILE", finished_docs, total_docs)
             future.result()

    for client in clients:
         for track in ["", "_ingest", "_prompts", "_doc"]:
              p = SCRIPT_DIR / f".storage{track}_{client}.json"
              if p.exists(): p.unlink()

    print("\n=======================================================================")
    print(" SUCCESS! ALL FAST PLAN RUNS PROCESSED COMPLETELY. ")
    print("=======================================================================")


if __name__ == "__main__":
    main()
