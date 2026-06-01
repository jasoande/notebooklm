Here is your updated, production-ready **`README.md`** layout consolidated into a single, comprehensive Markdown file.

Every major primary section title has been explicitly expanded in scale and volume using custom high-visibility typography blocks (`# # # █`). It completely documents the newly updated **delayed UI launch**, **prompt file-serialization fixes**, **Red Hat PatternFly dark interface guidelines**, and **bolded file-selection prompt rules**.

You can copy and paste this text directly into your repository:

```markdown
# # # █ SECTION 1: SYSTEM ARCHITECTURE & OVERVIEW
---

The Workspace Compilation Studio is an enterprise orchestration suite built to automate the provisioning, file ingestion, semantic deduplication, and component synthesis of isolated workspaces inside NotebookLM. Utilizing bounded thread workers via a `ThreadPoolExecutor`, the orchestration layer deploys up to six separate environments (`Customer1` through `Customer6`) concurrently without risking main-thread locks or race conditions.

### **1.1 Pipeline Operational Blueprints**
The orchestrator features two specialized configurations optimized for distinct infrastructure tracks:

* **`fast.py` (Fast Lane Tracking Engine):** Built for high-velocity linear generation. It strips explicit research mode flags to force NotebookLM to route inputs through standard cloud indexing lanes, utilizing an extended **90-second execution wait buffer** to absorb multi-tenant request spikes safely.
* **`deep.py` (Deep Research Resource Capping Engine):** Built for comprehensive cross-web semantic grounding. It forces the cloud search clusters into intensive multi-layered crawls via an extended **180-second tracking hold**. To maintain strict context compliance, it applies an automated truncation logic filter that imports only the top $N = 25$ cited website reference nodes per query.

### **1.2 UI Initialization & Delayed Launch Protocol**
To maximize environment reliability and ensure clean background tasks, the system runs all pre-flight routines (such as credential lookups, workspace cache checking, and workspace generation) silently inside the terminal console. **The Red Hat visual dashboard opens immediately AFTER all concurrent pre-creation and verification checks pass successfully.** This prevents premature browser launching while endpoints are warming up.

<br>

# # # █ SECTION 2: INFRASTRUCTURE PRE-PROCESSING LIFECYCLE
---

Target client data must follow a standard formatting and sanitization lifecycle on your local scratch space before invoking execution threads.

### **2.1 File Organization Hierarchy**
1. Fetch your profile `.zip` resource bundles directly from Google Drive.
2. Formulate an absolute local working drive parent context using your account team configuration syntax: `[AE_LastName]_[Year]` (e.g., `Venella_2026/`).
3. Decompress the archives directly inside this targeted parent block.

### **2.2 Normalization Automation Scripts**
Create and execute the following two clean-up scripts inside your root working drive to guarantee zero shell-argument expansion gaps or filename compatibility blocks within the backend sub-processes:

#### **Script A: Format Normalization (`convert.sh`)**
```bash
#!/usr/bin/env bash
# convert.sh: Headless Document Conversion Engine
if [ -z "$1" ]; then
    echo "Usage: ./convert.sh <target_directory>"
    exit 1
fi
TARGET_DIR="$1"
echo "==> Starting headless format conversion loop inside: $TARGET_DIR"
find "$TARGET_DIR" -type f \( -name "*.docx" -o -name "*.xlsx" -o -name "*.pptx" -o -name "*.doc" -o -name "*.xls" -o -name "*.ppt" \) | while read -r file; do
    echo "Converting asset: $file"
    libreoffice --headless --convert-to pdf --outdir "$(dirname "$file")" "$file" && rm "$file"
done
echo "==> Format normalization successfully finished."

```

#### **Script B: Filename Sanitization (`san.sh`)**

```bash
#!/usr/bin/env bash
# san.sh: Path Whitespace Sanitizer Utility
if [ -z "$1" ]; then
    echo "Usage: ./san.sh <target_directory>"
    exit 1
fi
TARGET_DIR="$1"
echo "==> Initiating filename whitespace serialization inside: $TARGET_DIR"
find "$TARGET_DIR" -depth -name "* *" | while read -r file; do
    dir="$(dirname "$file")"
    base="$(basename "$file")"
    new_base="${base// /_}"
    mv "$file" "$dir/$new_base"
    echo "Sanitized path title: $base -> $new_base"
done
echo "==> Filename scrub completed cleanly."

```

#### **Pre-Processing Invocation Commands**

```bash
chmod +x convert.sh san.sh
./convert.sh /Users/jasona/account_plan/Venella_2026/
./san.sh /Users/jasona/account_plan/Venella_2026/

```

# # # █ SECTION 3: ENVIRONMENT VARIABLES CONFIGURATION (`vars.py`)

---

The orchestration runtime requires a mapping file named `vars.py` positioned in the script root folder to direct thread pools to localized targets. This template handles up to 6 targets using completely anonymized properties and aligns specific object strings to match python mapping patterns perfectly:

```python
# vars.py - Global Environment Configuration Matrix (Venella 2026 Schema)
clients = ["merck_test", "blue_yonder_test", "organon_test", "panasonic_avionics_test", "hershey_test", "lord_abbett_test"]

# Merck Configuration
merck_test_name = "Merck Test"
merck_test_industry = "pharmaceuticals and healthcare"
merck_test_folder = "/Users/jasona/account_plan/Venella_2026/Merck/"

# Panasonic Avionics Configuration
panasonic_avionics_test_name = "Panasonic Avionics Test"
panasonic_avionics_test_industry = "electronics, technology, and manufacturing"
panasonic_avionics_test_folder = "/Users/jasona/account_plan/Venella_2026/Panasonic_Avionics/"

# Blue Yonder Configuration
blue_yonder_test_name = "Blue Yonder Test"
blue_yonder_test_industry = "AI-driven supply chain management"
blue_yonder_test_folder = "/Users/jasona/account_plan/Venella_2026/Blue_Yonder/"

# Hershey Configuration
hershey_test_name = "Hershey Test"
hershey_test_industry = "confectionery and snack food manufacturing"
hershey_test_folder = "/Users/jasona/account_plan/Venella_2026/Hershey/"

# Organon Configuration
organon_test_name = "Organon Test"
organon_test_industry = "pharmaceuticals and healthcare"
organon_test_folder = "/Users/jasona/account_plan/Venella_2026/Organon/"

# Lord Abbett Configuration
lord_abbett_test_name = "Lord Abbett Test"
lord_abbett_test_industry = "financial services"
lord_abbett_test_folder = "/Users/jasona/account_plan/Venella_2026/Lord_Abbett/"

```

# # # █ SECTION 4: CROSS-PLATFORM ENVIRONMENT SETUP

---

### **4.1 Linux (RHEL / Ubuntu / Debian) Setup Matrix**

```bash
sudo apt-get update && sudo apt-get install -y python3-dev python3-pip python3-tk libreoffice
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install "notebooklm-py" "notebooklm-py[browser]" "notebooklm-py[cookies]" tkinter pandas openpyxl google-api-python-client google-auth-oauthlib

```

### **4.2 macOS (Intel & Apple Silicon M1/M2/M3) Setup Matrix**

```bash
brew install python-tk python@3.12 libreoffice
python3.12 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install "notebooklm-py" "notebooklm-py[browser]" "notebooklm-py[cookies]" tkinter pandas openpyxl google-api-python-client google-auth-oauthlib

```

### **4.3 Microsoft Windows Terminal Setup Matrix**

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install "notebooklm-py" "notebooklm-py[browser]" "notebooklm-py[cookies]" tkinter pandas openpyxl google-api-python-client google-auth-oauthlib

```

# # # █ SECTION 5: PIPELINE EXECUTION SEQUENCE

---

Before launching runtime loops, ensure a persistent cloud security handshake token is active by running `notebooklm login` in your terminal shell. Once authenticated, run your chosen orchestration engine format:

### **5.1 Run Fast Mode Pipeline**

```bash
python fast.py

```

### **5.2 Run Deep Mode Pipeline**

```bash
python deep.py

```

### **5.3 Technical System Assertions & Telemetry Rules**

* **Multiline Escaping Resiliency:** Large or heavily structured template prompts (such as complex roleplay parameters or multi-layered questionnaires) are dynamically serialized to local disk files (`.temp_prompt_[client].txt`) during Phase 1 before execution. This entirely bypasses terminal text dropouts and shell argument exceptions.
* **PatternFly Telemetry Interface:** The tracking dashboard matches Red Hat PatternFly standards, featuring a dark slate palette (`#0b0d10`), a corporate red layout bar (`#cc0000`), a glowing **Fedora Blue** branding emblem (`#3c6eb4`), and an active status blinking pulse.
* **Large Font Pop-up Constraints:** When local upload dialog boxes require manual interaction during fallback sequences, the Tkinter modal injection applies an expanded, bold formatting structure to highlight the active **Client Name** explicitly.
* **Asynchronous Pacing Logic:** An internal JavaScript tracking element manages page refreshes dynamically. It runs a high-precision **1-second refresh during the first 5 seconds** of thread initialization, then shifts down to a low-overhead **5-second polling interval** to save rendering cycles while long-running cloud tasks complete.
* **Persistent Local Tracing Targets:**
* Fast Log: `/Users/jasona/account_plan/notebooklmpipeline_fast_execution.log`
* Deep Log: `/Users/jasona/account_plan/notebooklmpipeline_deep_execution.log`
* UI Mount: `/Users/jasona/account_plan/notebooklmpipeline_dashboard.html`



```

```
