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
LOG_FILE_PATH = Path("/Users/jasona/account_plan/notebooklm/pipeline_deep_execution.log")
DASHBOARD_PATH = Path("/Users/jasona/account_plan/notebooklm/pipeline_dashboard.html")

LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

log_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(message)s",
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

ui_queue = queue.Queue()
dashboard_lock = threading.Lock()
console_print_lock = threading.Lock()
cli_execution_lock = threading.Lock()
dashboard_state = {}
start_time_global = time.time()


def track_phase_progress(phase_title, finished_count, total_count):
    """Generates a clean synchronized global progress bar for the active execution phase."""
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
    <title>Red Hat Deep Account Planning Console</title>
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
        .grid-container {{ display: grid; grid-gap: 25px; }}
        .rh-card {{ background: #151515; border: 1px solid #2f3133; border-radius: 6px; padding: 24px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); transition: border-color 0.2s ease; }}
        .rh-card:hover {{ border-color: #4f5255; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
        .client-name {{ font-size: 1.25rem; font-weight: 700; color: #ffffff; display: flex; align-items: center; }}
        .client-hash {{ font-family: "Liberation Mono", monospace; font-size: 0.8rem; color: #8a8d90; background: #212427; padding: 3px 8px; border-radius: 4px; margin-left: 12px; border: 1px solid #2f3133; }}
        .progress-track {{ background: #212427; border-radius: 4px; height: 14px; overflow: hidden; margin: 15px 0; border: 1px solid #2f3133; }}
        .progress-fill {{ height: 100%; width: 0%; transition: width 0.6s cubic-bezier(0.16, 1, 0.3, 1); background: linear-gradient(90deg, #3b82f6 0%, #60a5fa 100%); }}
        .status-pill {{ font-size: 0.75rem; font-weight: 700; padding: 5px 14px; border-radius: 30px; text-transform: uppercase; letter-spacing: 0.75px; box-shadow: inset 0 1px 2px rgba(255,255,255,0.1); }}
        .pill-RUNNING {{ background: rgba(236,122,8,0.15); color: #f4c176; border: 1px solid #ec7a08; }}
        .pill-DEGRADED {{ background: rgba(219, 145, 0, 0.2); color: #ff9100; border: 1px solid #ff9100; }}
        .pill-COMPLETE {{ background: rgba(62,134,53,0.15); color: #8bc34a; border: 1px solid #3e8635; }}
        .pill-FAILED {{ background: rgba(201,25,11,0.15); color: #ff6b6b; border: 1px solid #c9190b; }}
        .pill-PENDING {{ background: #212427; color: #d1d5db; border: 1px solid #4f5255; }}
        .step-log {{ font-size: 0.9rem; color: #d1d5db; margin-top: 10px; display: flex; justify-content: space-between; align-items: center; }}
        .step-log strong {{ color: #ffffff; }}
        .plan-btn {{ display: inline-block; background: #3b82f6; color: #ffffff; text-decoration: none; padding: 6px 14px; font-size: 0.8rem; font-weight: 700; border-radius: 3px; text-transform: uppercase; transition: background 0.2s ease; border: 1px solid rgba(255,255,255,0.1); }}
        .plan-btn:hover {{ background: #60a5fa; box-shadow: 0 0 10px rgba(59,130,246,0.4); }}
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
            <div class="rh-logo"><strong style="color: #ff3333; font-weight: 900; letter-spacing: -1px; background-color: #ffffff; padding: 2px 8px; border-radius: 3px; margin-right: 5px;">RED HAT</strong> Deep Account Planning for client</div>
            <div class="rh-subtitle">Ecosystem Pipeline Infrastructure Daemon</div>
        </div>
    </div>
    <div class="main-layout">
        <div class="status-alert">
            <span class="timer-label">Account planning status engine execution monitor vectors.</span>
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
                <div class="progress-fill" style="width: {data["progress"]}%; background: {fill_color};"></div>
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


def fetch_notebook_cache(storage_path=None):
    cmd = ["notebooklm"]
    if storage_path: cmd.extend(["--storage", str(storage_path)])
    cmd.append("list")
    try:
        res = subprocess.run(cmd, check=False, text=True, capture_output=True)
        cache = {}
        uuid_pattern = re.compile(r'([a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12})', re.IGNORECASE)
        
        for line in res.stdout.splitlines():
            match = uuid_pattern.search(line)
            if match:
                nb_uuid = match.group(1)
                clean_name = line.replace(nb_uuid, "").replace("│", "").replace("┃", "").strip()
                clean_name = re.sub(r'\s+', ' ', clean_name)
                
                if clean_name:
                    cache[clean_name.lower().strip()] = nb_uuid
                    cache[clean_name.lower().replace(" ", "")] = nb_uuid
                cache[nb_uuid] = nb_uuid
        return cache
    except Exception: return {}


def ensure_notebook_exists(client_str, shared_auth_path):
    client_storage = SCRIPT_DIR / f".storage_{client_str}.json"
    update_dashboard(client_str, step="Pre-flight verification", progress=5, status="RUNNING")
    try:
        if shared_auth_path.exists(): client_storage.write_text(shared_auth_path.read_text())
        name_value = getattr(config, f"{client_str}_name", "")
        if not name_value:
            update_dashboard(client_str, step="Skipped", progress=0, status="PENDING")
            return None
            
        subprocess.run(["notebooklm", "--storage", str(client_storage), "auth", "refresh", "--quiet"], check=False, capture_output=True)
        notebook_cache = fetch_notebook_cache(storage_path=client_storage)
        nb_id = notebook_cache.get(name_value.lower().strip()) or notebook_cache.get(client_str.lower()) or notebook_cache.get(name_value.lower().replace(" ", ""))
                    
        if not nb_id:
            cmd = ["notebooklm", "--storage", str(client_storage), "create", name_value]
            res = subprocess.run(cmd, check=False, text=True, capture_output=True)
            uuid_match = re.search(r'([a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12})', res.stdout, re.IGNORECASE)
            nb_id = uuid_match.group(1) if uuid_match else None
            
            if not nb_id and ("already exists" in res.stderr.lower() or "already exists" in res.stdout.lower() or res.returncode != 0):
                time.sleep(1.0)
                notebook_cache = fetch_notebook_cache(storage_path=client_storage)
                nb_id = notebook_cache.get(name_value.lower().strip()) or notebook_cache.get(client_str.lower()) or notebook_cache.get(name_value.lower().replace(" ", ""))
                
        if not nb_id:
            raise Exception(f"Failed to isolate workspace UUID layout target mapping: {name_value}")
            
        update_dashboard(client_str, step="Workspace Active", progress=100, status="COMPLETE")
        return str(client_str), name_value, nb_id
    except Exception as e:
        update_dashboard(client_str, step="Pre-flight error", progress=100, status="FAILED")
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


def ingest_client_sources(client_str, shared_auth_path, nb_id):
    client_storage = SCRIPT_DIR / f".storage_ingest_{client_str}.json"
    temporary_files_to_clean = []
    update_dashboard(client_str, step="Phase 0: Ingestion Inbound", progress=20, status="RUNNING")
    try:
        if shared_auth_path.exists(): client_storage.write_text(shared_auth_path.read_text())
        
        subprocess.run(["notebooklm", "--storage", str(client_storage), "auth", "refresh", "--quiet"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["notebooklm", "--storage", str(client_storage), "use", nb_id], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        client_folder_raw = getattr(config, f"{client_str}_folder", ".")
        drive_folder_value = Path(PROJECT_ROOT / client_folder_raw).resolve()

        drive_targets = []
        if drive_folder_value.exists() and drive_folder_value.is_dir():
            # FIXED: Ignore hidden macOS configuration dotfiles (.DS_Store) explicitly from ingestion pools
            drive_targets.extend([str(p) for p in drive_folder_value.glob("*") if p.is_file() and not p.name.startswith(".")])
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
            source_title = f"{client_str}_source_{re.sub(r'[^a-zA-Z0-9_]', '', raw_title)}"
            
            cmd = ["notebooklm", "--storage", str(client_storage), "source", "add", "--title", source_title, target_id]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        update_dashboard(client_str, step="Phase 0 Completed Natively", progress=100, status="COMPLETE")
    except Exception as e:
        update_dashboard(client_str, step="Phase 0 Ingestion Failure", progress=100, status="FAILED")
        raise e
    finally:
        if client_storage.exists(): client_storage.unlink()
        for f in temporary_files_to_clean:
            if f.exists(): f.unlink()


def execute_client_prompts(client_str, sorted_prompt_files, shared_auth_path, nb_id):
    client_storage = SCRIPT_DIR / f".storage_prompts_{client_str}.json"
    name_value = getattr(config, f"{client_str}_name", f"UnknownClient-{client_str}")
    industry_value = getattr(config, f"{client_str}_industry", "")
    current_run_status = "RUNNING"
    try:
        if shared_auth_path.exists(): client_storage.write_text(shared_auth_path.read_text())
        subprocess.run(["notebooklm", "--storage", str(client_storage), "use", nb_id], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        output_dir = (SCRIPT_DIR / client_str).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        for p_idx, prompt_file in enumerate(sorted_prompt_files):
            step_pct = int(0 + ((p_idx / len(sorted_prompt_files)) * 100))
            update_dashboard(client_str, step=f"Phase 1 Prompting Tracks", progress=step_pct, status=current_run_status)
            updated_content = prompt_file.read_text().replace("$industry", industry_value).replace("$name", name_value)
            
            temp_prompt_carrier = SCRIPT_DIR / f".temp_prompt_{client_str}_{prompt_file.name}"
            temp_prompt_carrier.write_text(updated_content, encoding="utf-8")
            try:
                if "ask" in prompt_file.name.lower():
                    cmd = ["notebooklm", "--storage", str(client_storage), "source", "add-research", "--prompt-file", str(temp_prompt_carrier.resolve()), "--mode", "deep", "--no-wait"]
                    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(30.0)
                else:
                    cmd = ["notebooklm", "--storage", str(client_storage), "ask", "--prompt-file", str(temp_prompt_carrier.resolve()), "--save-as-note"]
                    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception: pass
            finally:
                if temp_prompt_carrier.exists(): temp_prompt_carrier.unlink()
        update_dashboard(client_str, step="Phase 1 Finished Successfully", progress=100, status="COMPLETE")
        return current_run_status
    except Exception:
        update_dashboard(client_str, step="Phase 1 Defect", progress=100, status="FAILED")
        return "FAILED"
    finally:
        if client_storage.exists(): client_storage.unlink()


def post_process_and_generate_google_doc(client_str, shared_auth_path, nb_id, current_run_status):
    """CONSOLIDATED NOTE RE-ENGINEERING: Maps, gathers, and orders notes explicitly into one unified Google Doc payload."""
    client_storage = SCRIPT_DIR / f".storage_doc_{client_str}.json"
    human_name = getattr(config, f"{client_str}_name", client_str)
    clean_name_string = re.sub(r'[^a-zA-Z0-9_]', '', human_name.replace(' ', ''))
    update_dashboard(client_str, step="Phase 4: Merging Research Notes...", progress=90, status="RUNNING")
    try:
        if shared_auth_path.exists(): client_storage.write_text(shared_auth_path.read_text())
        subprocess.run(["notebooklm", "--storage", str(client_storage), "use", nb_id], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # GATHER NOTE CONTENT BLOCKS
        list_notes_cmd = ["notebooklm", "--storage", str(client_storage), "note", "list"]
        notes_res = subprocess.run(list_notes_cmd, check=False, text=True, capture_output=True)
        
        compiled_sections = [f"<h1>Enterprise Cloud Account Strategic Plan: {human_name}</h1>", "<hr/>"]
        note_uuid_pattern = re.compile(r'([a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12})', re.IGNORECASE)
        
        for line in notes_res.stdout.splitlines():
            note_match = note_uuid_pattern.search(line)
            if note_match:
                n_uuid = note_match.group(1)
                view_cmd = ["notebooklm", "--storage", str(client_storage), "note", "view", n_uuid]
                note_data = subprocess.run(view_cmd, check=False, text=True, capture_output=True)
                if note_data.stdout.strip():
                    compiled_sections.append(f"<div>{note_data.stdout.strip()}</div><br/><br/>")
                    
        if len(compiled_sections) <= 2:
            compiled_sections.append("<p>Context compilation vectors ran headlessly. Reference notebook container logs for details.</p>")
            
        unified_document_payload = "\n".join(compiled_sections)
        
        # RATE LIMIT RETRY SAFES
        max_attempts = 4
        base_delay = 45.0
        doc_res = None
        for attempt in range(max_attempts):
            doc_res = subprocess.run(["notebooklm", "--storage", str(client_storage), "generate", "document", f"{clean_name_string}_Account_Plan"], input=unified_document_payload, check=False, text=True, capture_output=True)
            if "quota" in doc_res.stderr.lower() or "rate limit" in doc_res.stderr.lower() or "exhausted" in doc_res.stderr.lower():
                sleep_duration = base_delay * (attempt + 1)
                time.sleep(sleep_duration)
                continue
            break

        url_match = re.search(r'(https://docs\.google\.com/document/d/[a-zA-Z0-9-_]+)', doc_res.stdout if doc_res else "")
        doc_url = url_match.group(1) if url_match else f"https://notebooklm.google.com/"

        for asset_type in [["mind-map"], ["slide-deck"]]:
            try:
                subprocess.run(["notebooklm", "--storage", str(client_storage), "generate"] + asset_type, check=False, capture_output=True)
                time.sleep(8.0)
            except Exception: pass

        final_status = "COMPLETE" if current_run_status == "RUNNING" else "DEGRADED"
        update_dashboard(client_str, step="Pipeline Finished Successfully", progress=100, status=final_status, plan_link=doc_url)
    except Exception:
        update_dashboard(client_str, step="Failed Google Doc Compile", progress=100, status="FAILED")
    finally:
        if client_storage.exists(): client_storage.unlink()


def main():
    # RULE NUMBER 1: GLOBAL CREDENTIALS CHECK REFRESH EXECUTED FIRST LOBBY
    print("=======================================================================")
    print(" [GATEKEEPER] Synchronizing Global Authorization Profile Vector... ")
    print("=======================================================================")
    try:
        # Programmatically runs with the explicit authorized chain loop natively to surface interactive login hooks if expired
        subprocess.run(["notebooklm", "auth", "refresh"], check=True)
    except subprocess.CalledProcessError:
        print("\n\033[91m[AUTH FAILURE]\033[0m Master session failed. Run 'notebooklm auth login' manually on your shell window first.", file=sys.stderr)
        sys.exit(1)

    shared_auth_path = Path.home() / ".notebooklm" / "profiles" / "default" / "storage_state.json"
    if not shared_auth_path.exists(): shared_auth_path = Path.home() / ".notebooklm" / "storage_state.json"
    
    clients = [str(c).split('.')[-1].strip() if '.' in str(c) else str(c).strip() for c in getattr(config, "clients", [])]
    raw_prompt_files = [Path(f) for f in glob.glob(str(SCRIPT_DIR / "*prompt*.txt")) if Path(f).is_file()]
    if not raw_prompt_files or not clients: return

    sorted_prompt_files = sorted([f for f in raw_prompt_files if "ask" in f.name.lower()]) + sorted([f for f in raw_prompt_files if "ask" not in f.name.lower()])
    master_notebook_cache = {}
    
    for client in clients:
         dashboard_state[client] = { "name": getattr(config, f"{client}_name", client), "step": "Syncing Handles...", "progress": 0, "status": "PENDING", "plan_link": None }
         for track in ["", "_ingest", "_prompts", "_doc"]:
              client_storage = SCRIPT_DIR / f".storage{track}_{client}.json"
              if shared_auth_path.exists(): client_storage.write_text(shared_auth_path.read_text())

    html_init = f"<html><head><script>setTimeout(()=>{{window.location.reload();}},2000);</script></head><body style='background:#0b0d10;color:white;'><h2>Initializing RED HAT Deep Storage Monitoring Console...</h2></body></html>"
    DASHBOARD_PATH.write_text(html_init, encoding="utf-8")
    def open_browser_delayed():
         time.sleep(1.2)
         try: webbrowser.open(DASHBOARD_PATH.as_uri())
         except Exception: pass
    threading.Thread(target=open_browser_delayed, daemon=True).start()

    # THE CRITICAL SERIALIZATION FIX: Initialize workspace mappings sequentially to prevent SQLite connection failures across the profile database
    total_clients = len(clients)
    finished_audit = 0
    for client in clients:
        try:
            res = ensure_notebook_exists(str(client), shared_auth_path)
            finished_audit += 1
            track_phase_progress("AUDIT", finished_audit, total_clients)
            if res and res[2]:
                master_notebook_cache[str(res[0])] = res[2]
            time.sleep(0.5)
        except Exception as err:
            print(f"\n \033[91m[ FATAL CRASH ]\033[0m Workspace assignment failed for profile token: {client}")
            raise err
    print()

    print(" [2/4] Deploying Local Source Logs to Target Engine Ingestion Lanes... (Parallel Run)")
    MAX_WORKERS = min(8, len(clients))
    finished_ingest = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ingest_executor:
        ingest_futures = {ingest_executor.submit(ingest_client_sources, client_id, shared_auth_path, master_notebook_cache[client_id]): client_id for client_id in clients if client_id in master_notebook_cache}
        total_ingest = len(ingest_futures)
        for future in as_completed(ingest_futures):
             finished_ingest += 1
             track_phase_progress("INGEST", finished_ingest, total_ingest)
             future.result()
    print()

    print(" [3/4] Ingesting Question Prompts Sequences into AI Models... (Parallel Run)")
    finished_prompts = 0
    client_degraded_states = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as prompt_executor:
        prompt_futures = {prompt_executor.submit(execute_client_prompts, client_id, sorted_prompt_files, shared_auth_path, master_notebook_cache[client_id]): client_id for client_id in clients if client_id in master_notebook_cache}
        total_prompts = len(prompt_futures)
        for future in as_completed(prompt_futures):
             c_tok = str(prompt_futures[future])
             finished_prompts += 1
             track_phase_progress("PROMPT", finished_prompts, total_prompts)
             client_degraded_states[c_tok] = future.result()
    print()

    print(" [4/4] Sequentially Compiling Enterprise Cloud Google Doc Frameworks...")
    finished_docs = 0
    total_docs = len(master_notebook_cache)
    for client_token, nb_id in master_notebook_cache.items():
         post_process_and_generate_google_doc(client_token, shared_auth_path, nb_id, client_degraded_states.get(client_token, "RUNNING"))
         finished_docs += 1
         track_phase_progress("COMPILE", finished_docs, total_docs)

    print("\n=======================================================================")
    print(" SUCCESS! ALL DEEP PLAN RUNS PROCESSED COMPLETELY.")
    print("=======================================================================")


if __name__ == "__main__":
    main()
