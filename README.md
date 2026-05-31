Workspace Compilation Studio: Deployment & Operations Manual
System Classification
Architecture: Asynchronous Multi-Threaded Workspace Orchestrator

Target Platforms: Microsoft Windows 10/11, macOS 12+ (Intel/Apple Silicon), Linux (Debian, Ubuntu, RHEL, Fedora)

Upstream Dependency: NotebookLM Cloud API Engine via the notebooklm CLI binary wrapper

1. System Architecture & Overview
The Workspace Compilation Studio is an automation suite designed to provision, seed, analyze, and structure isolated workspaces within NotebookLM. Running operations across an asynchronous thread framework, this suite enables the simultaneous deployment of independent workspaces (e.g., Customer1 through Customer6) without blocking the central system thread, local GUI, or triggering race conditions.

1.1 Pipeline Operational Blueprints
The orchestrator is split into two specialized pipeline configurations to accommodate distinct organizational constraints, network boundaries, and rate-limiting profiles:

pipeline_fast.py (Fast Lane Tracking Engine): Optimized for rapid context assembly. It drops explicit mode flags when adding research files, forcing NotebookLM to run documents through its standard, high-velocity cloud indexing paths to maximize processing throughput.

pipeline_deep.py (Deep Research Resource Capping Engine): Optimized for extensive cross-web validation cycles. It explicitly triggers deep cloud research queries and monitors active status codes. To remain within context constraints, it applies an automated truncation logic filter that imports only the top N=25 cited website references as operational source assets.

2. Infrastructure Pre-Processing Lifecycle
Before launching either execution engine, source files must undergo a mandatory sanitization and data transformation loop on the local disk.

2.1 Google Drive Acquisition & Folder Topography
Source assets are maintained as compressed archive directories on Google Drive. Operators must strictly observe this data staging pipeline:

Identify and download all required client asset .zip bundles from your Google Drive storage account directly onto your local workstation.

Create a standard project root folder on your local disk named after the managing Account Executive's last name combined with the year (e.g., Smith_2026/).

Decompress and extract all downloaded customer zip structures directly into that parent folder space on your local machine (e.g., /Users/username/data/Smith_2026/Customer1/).

2.2 Automatic Document Normalization & Sanitization
The underlying automation environment enforces strict requirements: filenames must not contain whitespace characters, and documents must be formatted as raw PDFs. To avoid manual cleanups, run the included batch utilities:

Format Normalization (convert.sh): This automated shell wrapper launches a headless, background LibreOffice server context to recursively process your target folder, transforming raw extensions (.docx, .xlsx, .pptx) into readable PDF assets:

Bash
chmod +x convert.sh
./convert.sh /AbsolutePath/To/Smith_2026/
Filename Sanitization (san.sh): Run this shell script to scrub your directories. It sweeps through target folders and replaces spaces with uniform underscores (_), preventing path-parsing errors during CLI transmission:

Bash
chmod +x san.sh
./san.sh /AbsolutePath/To/Smith_2026/
3. Configuration Parameter Layout (vars.py)
The multi-threaded background handlers rely on a single control properties layout named vars.py sitting in the root project folder. This schema maps arbitrary profile indexes cleanly to localized system folders. It strips out legacy remote cloud identifiers and contains no hardcoded customer names:

Python
# vars.py - Global Environment Configuration Matrix
clients = ["Customer1", "Customer2", "Customer3", "Customer4", "Customer5", "Customer6"]

# Customer 1 Configuration Profile
Customer1_name = "Generic Customer One Operations LLC"
Customer1_industry = "Technology and Infrastructure Architecture"
Customer1_folder = "/AbsolutePath/To/Smith_2026/Customer1_Sanitized_PDF/"

# Customer 2 Configuration Profile
Customer2_name = "Generic Customer Two Enterprises"
Customer2_industry = "Global Logistics and Supply Chain Coordination"
Customer2_folder = "/AbsolutePath/To/Smith_2026/Customer2_Sanitized_PDF/"

# Customer 3 Configuration Profile
Customer3_name = "Generic Customer Three Corporation"
Customer3_industry = "Pharmaceutical Research and Biomedical Engineering"
Customer3_folder = "/AbsolutePath/To/Smith_2026/Customer3_Sanitized_PDF/"

# Customer 4 Configuration Profile
Customer4_name = "Generic Customer Four Systems"
Customer4_industry = "Financial Risk Analysis and Asset Management"
Customer4_folder = "/AbsolutePath/To/Smith_2026/Customer4_Sanitized_PDF/"

# Customer 5 Configuration Profile
Customer5_name = "Generic Customer Five Industrial Portfolio"
Customer5_industry = "Renewable Energy Systems and Grid Infrastructure"
Customer5_folder = "/AbsolutePath/To/Smith_2026/Customer5_Sanitized_PDF/"

# Customer 6 Configuration Profile
Customer6_name = "Generic Customer Six Holdings"
Customer6_industry = "Telecommunications and Aerospace Analytics"
Customer6_folder = "/AbsolutePath/To/Smith_2026/Customer6_Sanitized_PDF/"
4. Cross-Platform Environment Setup
4.1 Debian / Ubuntu Linux Environment Setup
Execute the following terminal commands to fulfill system headers, spin up virtual isolation layers, and compile packages:

Bash
sudo apt-get update && sudo apt-get install -y python3-dev python3-pip python3-tk libreoffice
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install google-api-python-client google-auth-oauthlib pandas openpyxl

4.2 macOS Environment Setup (Intel & Apple Silicon M1/M2/M3)
macOS default environments omit native Tkinter graphics layout bindings. Use Homebrew to establish reliable frameworks:

Bash
brew install python-tk python@3.12 libreoffice
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install google-api-python-client google-auth-oauthlib pandas openpyxl

4.3 Microsoft Windows Environment Setup
Install LibreOffice via official binaries, then initialize localized execution sandboxing structures using an administrative PowerShell console:

PowerShell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install google-api-python-client google-auth-oauthlib pandas openpyxl
5. Pipeline Execution Sequence
Before triggering operations, ensure a persistent cloud security handshake token is active by running notebooklm login in your terminal environment to secure authorization hooks. Once authorized, invoke your preferred engine version directly from your terminal shell:

5.1 Run Fast Mode Pipeline
To run high-velocity parallel workspace generations using native cloud compilation tracks:

Linux / macOS Terminal: python3 pipeline_fast.py

Windows PowerShell: python pipeline_fast.py

5.2 Run Deep Mode Pipeline
To trigger exhaustive deep web research loops restricted to the top 25 website reference nodes:

Linux / macOS Terminal: python3 pipeline_deep.py

Windows PowerShell: python pipeline_deep.py

5.3 Synchronized Refresh Monitoring Loop
Both automation architectures immediately launch an internal visualizer dashboard file named pipeline_dashboard.html using your default system web browser.

To ensure maximum system efficiency, this document uses a built-in JavaScript event controller. It maintains a hyper-responsive, 1-second refresh rate during the first 5 seconds to track workspace initialization steps, then scales back to a stable, 5-second auto-refresh frequency to minimize browser and disk overhead while the multi-threaded upload loops run. Detailed verbose logging outputs are written concurrently to pipeline_fast_execution.log or pipeline_deep_execution.log to aid system auditing.
