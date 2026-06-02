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

LOG_FILE_PATH = Path("/Users/jasona/account_plan/notebooklm/pipeline_fast_execution.log")
DASHBOARD_PATH = Path("/Users/jasona/account_plan/notebooklm/pipeline_dashboard.html")
LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

log_formatter = logging.Formatter(fmt="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
if root_logger.hasHandlers(): root_logger.handlers.clear()

file_handler = logging.FileHandler(LOG_FILE_PATH, mode="w", encoding="utf-8")
file_handler.setFormatter(log_formatter)
root_logger.addHandler(file_handler)

dashboard_lock = threading.Lock()
console_print_lock = threading.Lock()
cli_execution_lock = threading.Lock()
dashboard_state = {}
start_time_global = time.time()


def track_phase_progress(phase_title, finished_count, total_count):
    with console_print_lock:
        width = 25
        pct = int((finished_count / total_count) * 100) if total_count > 0 else 100
        filled_length = int(round(width * pct / 100))
        bar = '█' * filled_length + '░' * (width - filled_length)
        sys.stdout.write(f"\r\033[96m[ {phase_title:<7} ]\033[0m Phase Progress: |\033[91m{bar}\033[0m| \033[92m{pct:>3}%\033[0m completed ({finished_count}/{total_count} tasks done)")
        sys.stdout.flush()


def update_dashboard(client_token, step=None, progress=None, status=None, plan_link=None):
    client_name = getattr(config, f"{client_token}_name", client_token)
    global start_time_global
    elapsed = int(time.time() - start_time_global)
    timer_string = f"{elapsed // 60}m {elapsed % 60}s"

    with dashboard_lock:
        if client_token not in dashboard_state:
            dashboard_state[client_token] = {"name": client_name, "step": "Initializing", "progress": 0, "status": "PENDING", "plan_link": None}
        if step is not None: dashboard_state[client_token]["step"] = step
        if progress is not None: dashboard_state[client_token]["progress"] = progress
        if status is not None: dashboard_state[client_token]["status"] = status
        if plan_link is not None: dashboard_state[client_token]["plan_link"] = plan_link

        all_done = all(d["status"] in ["COMPLETE", "FAILED", "DEGRADED"] for d in dashboard_state.values())
        html_content = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Red Hat Fast Console</title><style>body {{ font-family: "Helvetica Neue", Arial, sans-serif; background-color: #0b0d10; color: #f5f5f7; margin: 0; padding: 0; }} .rh-banner {{ background: #151515; color: #ffffff; padding: 20px 35px; border-bottom: 4px solid #cc0000; }} .main-layout {{ max-width: 1100px; margin: 35px auto; padding: 0 25px; }} .status-alert {{ background: #151515; padding: 18px; border-left: 4px solid #cc0000; margin-bottom: 30px; }} .grid-container {{ display: grid; grid-gap: 25px; }} .rh-card {{ background: #151515; border: 1px solid #2f3133; padding: 24px; border-radius: 6px; }} .progress-track {{ background: #212427; height: 14px; border-radius: 4px; overflow: hidden; margin: 15px 0; }} .progress-fill {{ height: 100%; background: #cc0000; transition: width 0.4s ease; }} .plan-btn {{ display: inline-block; background: #3b82f6; color: white; text-decoration: none; padding: 6px 14px; font-size: 0.8rem; font-weight: bold; border-radius: 3px; }}</style><script>window.addEventListener('DOMContentLoaded', () => {{ if (!{str(all_done).lower()}) setTimeout(() => window.location.reload(), 3000); }});</script></head><body><div class="rh-banner"><h2>RED HAT Fast Account Planning Console</h2></div><div class="main-layout"><div class="status-alert">Execution Monitor Runtime: <strong>{timer_string}</strong></div><div class="grid-container">"""
        for token, data in dashboard_state.items():
            html_content += f"""<div class="rh-card"><h3>{data["name"]} ({token})</h3><span style="float:right;">{data["status"]}</span><div class="progress-track"><div class="progress-fill" style="width: {data["progress"]}%;"></div></div><div>Status: <strong>{data["step"]}</strong></div>{"<br/><a class='plan-btn' href='" + data["plan_link"] + "' target='_blank'>Open Plan</a>" if data["plan_link"] else ""}</div>"""
        html_content += "</div></div></body></html>"
        DASHBOARD_PATH.write_text(html_content, encoding="utf-8")


def fetch_notebook_cache(storage_path):
    try:
        res = subprocess.run(["notebooklm", "--storage", str(storage_path), "list"], check=False, text=True, capture_output=True)
        cache = {}
        uuid_pattern = re.compile(r'([a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12})', re.IGNORECASE)
        for line in res.stdout.splitlines():
            match = uuid_pattern.search(line)
            if match:
                nb_uuid = match.group(1)
                clean_name = line.replace(nb_uuid, "").replace("│", "").replace("┃", "").strip()
                clean_name = re.sub(r'\s+', ' ', clean_name).lower().strip()
                if clean_name:
                    cache[clean_name] = nb_uuid
                    cache[clean_name.replace(" ", "")] = nb_uuid
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
            
        notebook_cache = fetch_notebook_cache(client_storage)
        nb_id = notebook_cache.get(name_value.lower().strip()) or notebook_cache.get(name_value.lower().replace(" ", ""))
                    
        if not nb_id:
            res = subprocess.run(["notebooklm", "--storage", str(client_storage), "create", name_value], check=False, text=True, capture_output=True)
            uuid_match = re.search(r'([a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12})', res.stdout, re.IGNORECASE)
            nb_id = uuid_match.group(1) if uuid_match else None
            
            if not nb_id:
                time.sleep(1.0)
                notebook_cache = fetch_notebook_cache(client_storage)
                nb_id = notebook_cache.get(name_value.lower().strip())
                
        if not nb_id: raise Exception(f"Failed to isolate workspace UUID: {name_value}")
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
    update_dashboard(client_str, step="Phase 0: Ingestion", progress=20, status="RUNNING")
    try:
        if shared_auth_path.exists(): client_storage.write_text(shared_auth_path.read_text())
        subprocess.run(["notebooklm", "--storage", str(client_storage), "use", nb_id], check=True, stdout=subprocess.DEVNULL)
        
        # --- FIXED VARIABLE LOOKUP MATCH ENGINE ---
        clean_key = client_str.replace("_test", "")
        web_targets = getattr(config, f"{client_str}_websites", None) or getattr(config, f"{clean_key}_websites", [])
        
        for url in web_targets:
            if str(url).strip().startswith("http"):
                subprocess.run(["notebooklm", "--storage", str(client_storage), "source", "add", str(url).strip()], check=True, stdout=subprocess.DEVNULL)

        client_folder_raw = getattr(config, f"{client_str}_folder", ".")
        drive_folder_value = Path(PROJECT_ROOT / client_folder_raw).resolve()
        if drive_folder_value.exists() and drive_folder_value.is_dir():
            for p in drive_folder_value.glob("*"):
                if p.is_file() and not p.name.startswith("."):
                    target_id = str(p)
                    if p.suffix.lower() == '.csv':
                        structural_txt = convert_raw_csv_to_structured_text(target_id)
                        if structural_txt:
                            target_id = str(structural_txt)
                            temporary_files_to_clean.append(structural_txt)
                    
                    sanitized_title = re.sub(r'[^a-zA-Z0-9]', '_', p.stem)
                    sanitized_title = re.sub(r'_+', '_', sanitized_title).strip('_')
                    subprocess.run(["notebooklm", "--storage", str(client_storage), "source", "add", "--title", f"{client_str}_{sanitized_title}", target_id], check=True, stdout=subprocess.DEVNULL)

        update_dashboard(client_str, step="Ingestion Complete", progress=100, status="COMPLETE")
    except Exception as e:
        update_dashboard(client_str, step="Ingestion Failure", progress=100, status="FAILED")
        raise e
    finally:
        if client_storage.exists(): client_storage.unlink()
        for f in temporary_files_to_clean:
            if f.exists(): f.unlink()


def execute_client_prompts(client_str, sorted_prompt_files, shared_auth_path, nb_id):
    client_storage = SCRIPT_DIR / f".storage_prompts_{client_str}.json"
    name_value = getattr(config, f"{client_str}_name", client_str)
    industry_value = getattr(config, f"{client_str}_industry", "")
    try:
        if shared_auth_path.exists(): client_storage.write_text(shared_auth_path.read_text())
        subprocess.run(["notebooklm", "--storage", str(client_storage), "use", nb_id], check=True, stdout=subprocess.DEVNULL)
        
        for p_idx, prompt_file in enumerate(sorted_prompt_files):
            update_dashboard(client_str, step=f"Prompting: Note {p_idx+1}/{len(sorted_prompt_files)}", progress=int((p_idx/len(sorted_prompt_files))*100), status="RUNNING")
            updated_content = prompt_file.read_text().replace("$industry", industry_value).replace("$name", name_value)
            
            temp_prompt = SCRIPT_DIR / f".temp_prompt_{client_str}_{prompt_file.name}"
            temp_prompt.write_text(updated_content, encoding="utf-8")
            try:
                if "ask" in prompt_file.name.lower():
                    subprocess.run(["notebooklm", "--storage", str(client_storage), "source", "add-research", "--prompt-file", str(temp_prompt.resolve()), "--mode", "fast", "--no-wait"], check=True, stdout=subprocess.DEVNULL)
                    time.sleep(15.0)
                else:
                    subprocess.run(["notebooklm", "--storage", str(client_storage), "ask", "--prompt-file", str(temp_prompt.resolve()), "--save-as-note"], check=True, stdout=subprocess.DEVNULL)
            finally:
                if temp_prompt.exists(): temp_prompt.unlink()
        update_dashboard(client_str, step="Prompting Complete", progress=100, status="COMPLETE")
        return "RUNNING"
    except Exception:
        update_dashboard(client_str, step="Prompting Defect", progress=100, status="FAILED")
        return "FAILED"
    finally:
        if client_storage.exists(): client_storage.unlink()


def post_process_and_generate_markdown(client_str, shared_auth_path, nb_id, current_run_status):
    client_storage = SCRIPT_DIR / f".storage_doc_{client_str}.json"
    human_name = getattr(config, f"{client_str}_name", client_str)
    output_plan_path = SCRIPT_DIR / f"{client_str}_Account_Plan.md"
    update_dashboard(client_str, step="Compiling Local Markdown Plan...", progress=90, status="RUNNING")
    try:
        if shared_auth_path.exists(): client_storage.write_text(shared_auth_path.read_text())
        subprocess.run(["notebooklm", "--storage", str(client_storage), "use", nb_id], check=True, stdout=subprocess.DEVNULL)
        
        notes_res = subprocess.run(["notebooklm", "--storage", str(client_storage), "note", "list"], check=False, text=True, capture_output=True)
        markdown_sections = [f"# Enterprise Cloud Account Strategic Plan: {human_name}", f"**Generated Location:** `{output_plan_path}`", "---", ""]
        note_uuid_pattern = re.compile(r'([a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12})', re.IGNORECASE)
        
        for line in notes_res.stdout.splitlines():
            match = note_uuid_pattern.search(line)
            if match:
                note_data = subprocess.run(["notebooklm", "--storage", str(client_storage), "note", "view", match.group(1)], check=False, text=True, capture_output=True)
                if note_data.stdout.strip():
                    markdown_sections.append(note_data.stdout.strip())
                    markdown_sections.append("\n\n---\n\n")
                    
        if len(markdown_sections) <= 4:
            markdown_sections.append("## Automated Summary Plan Profile")
            sum_res = subprocess.run(["notebooklm", "--storage", str(client_storage), "ask", "Provide a comprehensive summary of all uploaded files."], check=False, text=True, capture_output=True)
            markdown_sections.append(sum_res.stdout.strip() if sum_res.stdout.strip() else "Empty source profiles directory.")

        output_plan_path.write_text("\n".join(markdown_sections), encoding="utf-8")
        for asset in [["mind-map"], ["slide-deck"]]:
            subprocess.run(["notebooklm", "--storage", str(client_storage), "generate"] + asset, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(5.0)

        update_dashboard(client_str, step="Pipeline Finished Successfully", progress=100, status="COMPLETE", plan_link=output_plan_path.as_uri())
    except Exception:
        update_dashboard(client_str, step="Failed Markdown Compile", progress=100, status="FAILED")
    finally:
        if client_storage.exists(): client_storage.unlink()


def main():
    print("=======================================================================")
    print(" [GATEKEEPER] Synchronizing Global Authentication Profiles... ")
    print("=======================================================================")
    try: subprocess.run(["notebooklm", "auth", "refresh"], check=True)
    except subprocess.CalledProcessError:
        print("\n\033[91m[AUTH EXPIRED]\033[0m Session dead. Run 'notebooklm auth login' on your shell first.", file=sys.stderr)
        sys.exit(1)

    shared_auth_path = Path.home() / ".notebooklm" / "profiles" / "default" / "storage_state.json"
    if not shared_auth_path.exists(): shared_auth_path = Path.home() / ".notebooklm" / "storage_state.json"
    
    clients = [str(c).split('.')[-1].strip() if '.' in str(c) else str(c).strip() for c in getattr(config, "clients", [])]
    raw_prompt_files = [Path(f) for f in glob.glob(str(SCRIPT_DIR / "*prompt*.txt")) if Path(f).is_file()]
    if not raw_prompt_files or not clients: return
    sorted_prompt_files = sorted([f for f in raw_prompt_files if "ask" in f.name.lower()]) + sorted([f for f in raw_prompt_files if "ask" not in f.name.lower()])
    master_notebook_cache = {}
    
    for client in clients: update_dashboard(client, step="Syncing Handles...", progress=0, status="PENDING")
    try: webbrowser.open(DASHBOARD_PATH.as_uri())
    except Exception: pass

    # THE CRITICAL SERIALIZATION FIX: Prevents concurrent state collisions natively
    total_clients = len(clients)
    finished_audit = 0
    for client in clients:
        res = ensure_notebook_exists(str(client), shared_auth_path)
        finished_audit += 1
        track_phase_progress("AUDIT", finished_audit, total_clients)
        if res and res[2]: master_notebook_cache[str(res[0])] = res[2]
        time.sleep(0.4)
    print()

    print(" [2/4] Deploying Local Source Logs to Target Engine Ingestion Lanes... (Parallel Run)")
    finished_ingest = 0
    with ThreadPoolExecutor(max_workers=min(8, len(clients))) as ingest_executor:
        ingest_futures = {ingest_executor.submit(ingest_client_sources, cid, shared_auth_path, master_notebook_cache[cid]): cid for cid in clients if cid in master_notebook_cache}
        for future in as_completed(ingest_futures):
             finished_ingest += 1
             track_phase_progress("INGEST", finished_ingest, len(ingest_futures))
             future.result()
    print()

    print(" [3/4] Ingesting Question Prompts Sequences into AI Models... (Parallel Run)")
    finished_prompts = 0
    client_degraded_states = {}
    with ThreadPoolExecutor(max_workers=min(8, len(clients))) as prompt_executor:
        prompt_futures = {prompt_executor.submit(execute_client_prompts, cid, sorted_prompt_files, shared_auth_path, master_notebook_cache[cid]): cid for cid in clients if cid in master_notebook_cache}
        for future in as_completed(prompt_futures):
             c_tok = str(prompt_futures[future])
             finished_prompts += 1
             track_phase_progress("PROMPT", finished_prompts, len(prompt_futures))
             client_degraded_states[c_tok] = future.result()
    print()

    print(" [4/4] Sequentially Compiling Local Strategy Markdown Profiles...")
    finished_docs = 0
    for client_token, nb_id in master_notebook_cache.items():
         post_process_and_generate_markdown(client_token, shared_auth_path, nb_id, client_degraded_states.get(client_token, "RUNNING"))
         finished_docs += 1
         track_phase_progress("COMPILE", finished_docs, len(master_notebook_cache))
    print("\n=======================================================================\n SUCCESS! ALL PIPELINE WORKFLOWS EXECUTED COMPLETELY.\n=======================================================================")

if __name__ == "__main__":
    main()
