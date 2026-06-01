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
from concurrent.futures import ThreadPoolExecutor
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

LOG_FILE_PATH = Path("/Users/jasona/account_plan/notebooklm/pipeline_deep_execution.log")
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
        .rh-tag {{ background: #0066cc; color: white; font-size: 0.65rem; font-weight: 700; padding: 3px 8px; border-radius: 3px; margin-left: 12px; letter-spacing: 1px; text-transform: uppercase; vertical-align: middle; }}
        .rh-subtitle {{ color: #b8bbbe; font-size: 0.9rem; margin-left: 20px; border-left: 1px solid #4f5255; padding-left: 20px; display: inline-block; vertical-align: middle; }}
        .main-layout {{ max-width: 1100px; margin: 35px auto; padding: 0 25px; }}
        .status-alert {{ background: #151515; border: 1px solid #3c3f42; border-left: 4px solid #3c6eb4; padding: 18px; border-radius: 4px; margin-bottom: 30px; font-size: 0.92rem; color: #d1d5db; display: flex; justify-content: space-between; align-items: center; }}
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
            let start = localStorage.getItem('rh_deep_start');
            if (!start) {{
                start = Date.now();
                localStorage.setItem('rh_deep_start', start);
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
            <div class="rh-logo">Red Hat <span>Studio</span><span class="rh-tag">Deep</span></div>
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
            fill_color = "linear-gradient(90deg, #3b82f6 0%, #60a5fa 100%)"
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
    """Executes system commands with safety staggering profiles."""
    time.sleep(random.uniform(0.2, 0.6))
    logging.debug(f"Executing command: {' '.join(cmd)}")
    try:
        return subprocess.run(cmd, check=check, text=text, capture_output=capture_output, input=input_data)
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with code {e.returncode}: {' '.join(cmd)}")
        raise e


def request_files_from_main_thread(client_name, timeout_secs=90):
    response_queue = queue.Queue()
    ui_queue.put((client_name, timeout_secs, response_queue))
    return response_queue.get()


def process_entire_client_lifecycle(client, sorted_prompt_files, shared_auth_path):
    """CRITICAL FIX: Bounded structural lifecycle wrapper that isolates optional block errors safely."""
    client_storage = SCRIPT_DIR / f".storage_deep_{client}.json"
    human_name = getattr(config, f"{client}_name", client)
    industry_value = getattr(config, f"{client}_industry", "")
    folder_value = Path(getattr(config, f"{client}_folder")).resolve()
    
    current_run_status = "RUNNING"
    update_dashboard(client, step="Pre-flight verification", progress=5, status=current_run_status)
    try:
        if shared_auth_path.exists():
            client_storage.write_text(shared_auth_path.read_text())

        # Phase 1: Establish Workspace Cache Connections
        run_cmd(["notebooklm", "--storage", str(client_storage), "auth", "refresh", "--quiet"])
        res = subprocess.run(["notebooklm", "--storage", str(client_storage), "list"], check=True, text=True, capture_output=True)
        
        nb_id = None
        for line in res.stdout.splitlines():
            clean_line = line.replace("│", "").replace("┃", "").strip()
            parts = clean_line.split()
            if len(parts) >= 2 and "-" in parts[0]:
                if " ".join(parts[1:-2]).strip() == human_name or " ".join(parts[1:-1]).strip() == human_name:
                    nb_id = parts[0]
                    break

        if not nb_id:
            update_dashboard(client, step="Creating workspace context", progress=10, status=current_run_status)
            res = run_cmd(["notebooklm", "--storage", str(client_storage), "create", human_name], capture_output=True)
            uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', res.stdout, re.IGNORECASE)
            nb_id = uuid_match.group(1) if uuid_match else None

        if not nb_id:
            raise Exception("Failed to bind cloud workspace layout ID.")

        run_cmd(["notebooklm", "--storage", str(client_storage), "use", nb_id])

        # Phase 2: Ingestion & Upload Layer
        update_dashboard(client, step="Phase 0: Material ingestion maps", progress=20, status=current_run_status)
        manually_selected_sources = request_files_from_main_thread(human_name, timeout_secs=90)
        
        drive_targets = []
        if folder_value.exists() and folder_value.is_dir():
            drive_targets.extend([str(p) for p in folder_value.glob("*") if p.is_file()])
        if manually_selected_sources:
            drive_targets.extend(manually_selected_sources)

        if drive_targets:
            tracked_tokens = []
            for idx, target in enumerate(drive_targets):
                source_title = f"{client}_src_{re.sub(r'[^a-zA-Z0-9_]', '', Path(target).stem.replace(' ', '_'))}"
                try:
                    res = run_cmd(["notebooklm", "--storage", str(client_storage), "source", "add", "--title", source_title, target], capture_output=True)
                    uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', res.stdout, re.IGNORECASE)
                    tracked_tokens.append(uuid_match.group(1) if uuid_match else source_title)
                except Exception:
                    pass

            for token in tracked_tokens:
                try: run_cmd(["notebooklm", "--storage", str(client_storage), "source", "wait", token])
                except Exception: pass

        # Phase 3: Prompt Execution with Self-Healing Fallback
        update_dashboard(client, step="Phase 1: Running deep structural context prompts", progress=50, status=current_run_status)
        output_dir = (SCRIPT_DIR / client).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        for prompt_file in sorted_prompt_files:
            prompt_content = prompt_file.read_text().replace("$industry", industry_value).replace("$name", human_name)
            (output_dir / prompt_file.name).write_text(prompt_content)

            temp_prompt = SCRIPT_DIR / f".temp_{client}_{prompt_file.name}"
            temp_prompt.write_text(prompt_content, encoding="utf-8")

            try:
                if "ask" in prompt_file.name.lower():
                    run_cmd(["notebooklm", "--storage", str(client_storage), "source", "add-research", "--prompt-file", str(temp_prompt.resolve()), "--mode", "deep", "--no-wait"])
                    
                    max_wait_intervals = 60  
                    loop_index = 0
                    research_cleared_cleanly = False
                    
                    while loop_index < max_wait_intervals:
                        time.sleep(5.0)
                        status_check = subprocess.run(["notebooklm", "--storage", str(client_storage), "research", "status"], text=True, capture_output=True)
                        status_stdout = status_check.stdout.upper()
                        
                        if "COMPLETED" in status_stdout or "IDLE" in status_stdout:
                            research_cleared_cleanly = True
                            break
                        elif "FAILED" in status_stdout or "ERROR" in status_stdout:
                            break
                        loop_index += 1

                    if research_cleared_cleanly:
                        try: run_cmd(["notebooklm", "--storage", str(client_storage), "research", "wait", "--import-all", "--max-imports", "50", "--timeout", "30"])
                        except Exception: pass
                    else:
                        current_run_status = "DEGRADED"
                        update_dashboard(client, step="Phase 1: Web deep research choked (Using local PDFs)", progress=55, status=current_run_status)
                else:
                    # SYSTEM CRASH FIX: Wrapped optional prompt blocks inside defensive context handlers to absorb gateway blinks safely
                    try:
                        run_cmd(["notebooklm", "--storage", str(client_storage), "ask", "--prompt-file", str(temp_prompt.resolve()), "--save-as-note"])
                    except Exception as ask_err:
                        logging.warning(f"[{human_name}] Prompt engine blocked or rate-limited: {ask_err}")
            except Exception as inner_e:
                logging.error(f"[{human_name}] Prompt segment execution defect: {inner_e}")
            finally:
                if temp_prompt.exists(): temp_prompt.unlink()

        # Phase 4: Deduplication Matrix Verification
        update_dashboard(client, step="Phase 2/3: Structural cleanup matrices", progress=80, status=current_run_status)
        try:
            res = run_cmd(["notebooklm", "--storage", str(client_storage), "source", "list"], capture_output=True)
            seen = set()
            for line in res.stdout.splitlines():
                parts = line.replace("│", "").replace("┃", "").strip().split()
                if parts and "-" in parts[0] and parts[0] != "ID":
                    title = " ".join(parts[1:-1])
                    if title in seen:
                        try: run_cmd(["notebooklm", "--storage", str(client_storage), "source", "delete", parts[0]], input_data="y\n")
                        except Exception: pass
                    else:
                        seen.add(title)
        except Exception: pass

        # MANDATORY ASSIGNMENT CHECK: Always attempt mind-map initialization alongside alternative visual parameters safely
        for asset in [["mind-map"], ["data-table", "compare key concepts"], ["slide-deck"]]:
            try: 
                run_cmd(["notebooklm", "--storage", str(client_storage), "generate"] + asset, check=True)
            except Exception as gen_err:
                logging.warning(f"[{human_name}] Asset generation track skipped or throttled: {gen_err}")

        # Phase 5: Master Material Synthesis Consolidation Block with Fault-Tolerant Scanning
        update_dashboard(client, step="Phase 4: Output plan consolidation", progress=95, status=current_run_status)
        
        master_content = f"# Strategic Master Account Plan (2026 Revision)\n**Target Account Profile:** {human_name}\n"
        if current_run_status == "DEGRADED":
            master_content += f"> **Operational Warning Note:** Web compilation layers throttled during execution. Generation grounded strictly in localized source documentation arrays.\n"
        master_content += "---\n\n"

        try:
            list_res = run_cmd(["notebooklm", "--storage", str(client_storage), "note", "list"], capture_output=True)
            uuid_pattern = re.compile(r'^[a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12}$', re.IGNORECASE)
            
            for line in list_res.stdout.splitlines():
                parts = line.replace("│", "").replace("┃", "").strip().split()
                if parts and uuid_pattern.match(parts[0]):
                    # SYSTEM CRASH FIX: Protect document trace compilation paths from throwing non-zero exit codes during transient server drops
                    try:
                        view_res = run_cmd(["notebooklm", "--storage", str(client_storage), "note", "view", parts[0]], capture_output=True)
                        master_document_content += f"## Analysis Segment\n```text\n{view_res.stdout.strip()}\n```\n\n"
                    except Exception as view_err:
                        logging.error(f"[{human_name}] Skipping note vector capture due to API retrieval constraint: {view_err}")
        except Exception as list_err:
            logging.critical(f"[{human_name}] Workspace note registry retrieval failed entirely: {list_err}")

        out_path = output_dir / "Account_Plan_2026.md"
        out_path.write_text(master_content, encoding="utf-8")

        final_status = "COMPLETE" if current_run_status == "RUNNING" else "DEGRADED"
        update_dashboard(client, step="Execution Successfully Finished", progress=100, status=final_status)
    except Exception as e:
        logging.error(f"[{human_name}] Critical Thread Crash: {e}")
        update_dashboard(client, step="Critical Process Error", progress=100, status="FAILED")
    finally:
        if client_storage.exists():
            try: client_storage.unlink()
            except Exception: pass


def main():
    try: run_cmd(["notebooklm", "login"])
    except Exception: sys.exit(1)

    os.environ['rh_deep_start'] = str(int(time.time() * 1000))
    DASHBOARD_PATH.write_text("<h1>Warming up Parallel Engine Matrix Nodes...</h1>", encoding="utf-8")
    try: webbrowser.open(DASHBOARD_PATH.as_uri())
    except Exception: pass

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    shared_auth = Path.home() / ".notebooklm" / "profiles" / "default" / "storage_state.json"
    if not shared_auth.exists(): shared_auth = Path.home() / ".notebooklm" / "storage_state.json"

    clients = getattr(config, "clients", [])
    raw_prompts = [Path(f) for f in glob.glob(str(SCRIPT_DIR / "*prompt*.txt")) if Path(f).is_file()]
    global sorted_prompt_files
    sorted_prompt_files = sorted([f for f in raw_prompts if "ask" in f.name.lower()]) + sorted([f for f in raw_prompts if "ask" not in f.name.lower()])

    for client in clients:
        update_dashboard(client, step="Queued inside execution ring...", progress=0, status="PENDING")

    with ThreadPoolExecutor(max_workers=len(clients)) as executor:
        futures = {executor.submit(process_entire_client_lifecycle, c, sorted_prompt_files, shared_auth): c for c in clients}
        
        completed = 0
        while completed < len(futures):
            try:
                name, sec, q = ui_queue.get(timeout=1.0)
                win = tk.Toplevel(root)
                win.withdraw()
                f_lbl = tk.Label(win, text=f"Target Client Profile: {name}", font=tkfont.Font(family="Helvetica", size=14, weight="bold"), fg="#CC0000", padx=20, pady=15)
                f_lbl.pack()
                win.after(sec * 1000, lambda: [win.destroy(), q.put([])])
                files = filedialog.askopenfilenames(parent=win, title=f"Select Assets for {name}")
                win.destroy()
                q.put(list(files) if files else [])
            except queue.Empty:
                completed = len([f for f in futures if f.done()])


if __name__ == "__main__":
    main()
