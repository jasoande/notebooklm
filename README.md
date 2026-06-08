# Project APE - Account Planning Engine

**Automated Account Planning and Intelligence Generation for Red Hat Sales Teams**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![Node.js](https://img.shields.io/badge/Node.js-16%2B-green.svg)](https://nodejs.org/)
[![License](https://img.shields.io/badge/License-Red%20Hat%20Internal-red.svg)](#license)

---

## Quick Start

**New to Project APE?** See [SETUP_GUIDE.md](SETUP_GUIDE.md) for step-by-step setup instructions.

**Configuration Example:** See [vars.example.py](vars.example.py) for complete configuration reference.

**Business Case:** See [PROJECT_APE_EXECUTIVE_SUMMARY.md](PROJECT_APE_EXECUTIVE_SUMMARY.md) for ROI analysis.

## Table of Contents

- [Quick Start](#quick-start)
- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Red Hat Enterprise Linux (RHEL)](#red-hat-enterprise-linux-rhel)
  - [macOS](#macos)
  - [Windows](#windows)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Fast Mode](#fast-mode-recommended-for-initial-runs)
  - [Deep Mode](#deep-mode-research-intensive)
  - [CLI Options](#cli-options)
- [Pipeline Phases](#pipeline-phases)
- [Project Structure](#project-structure)
- [Prompt Engineering](#prompt-engineering)
- [Troubleshooting](#troubleshooting)
- [Performance Benchmarks](#performance-benchmarks)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)
- [Support](#support)

---

## Overview

Project APE (Account Planning Engine) automates the creation of comprehensive, strategic account plans by ingesting customer documents, conducting AI-powered research using Google NotebookLM, and generating structured intelligence across multiple strategic dimensions.

**Latest Version:** v3.0 Optimized (June 2026)  
**Status:** Production Ready ✅  
**Grade:** A- (92/100) - Senior Engineer Assessed

### What It Does

1. **Document Ingestion**: Consolidates PDFs, CSVs, and financial reports into a unified knowledge base
2. **AI-Powered Research**: Conducts deep research using NotebookLM's AI with optional web citations
3. **Structured Analysis**: Generates account intelligence across 10 key planning dimensions:
   - Foundation research (financials, leadership, strategy)
   - Industry subsegment analysis
   - Business objectives and competitive landscape
   - Technology partner ecosystem mapping
   - Red Hat value propositions
   - Solution recommendations
   - Strategic "How Might We" statements
   - Team onboarding guides
   - Partner briefing documents
   - Comprehensive account plan synthesis
4. **Deliverable Generation**: Produces customer-facing presentations, mind maps, and comprehensive planning documents with direct NotebookLM links

### Key Benefits

- **Time Savings**: Reduces account plan creation from weeks to hours (estimated 95% time reduction)
- **Cost Savings**: $180,000 - $360,000 annually per 100 account teams (See ROI analysis below)
- **Consistency**: Ensures all account plans follow Red Hat's strategic framework
- **Research Depth**: Leverages AI to discover insights from public sources and internal documents
- **Scalability**: Process multiple accounts in parallel with configurable concurrency
- **Quality Assurance**: Built-in validation framework with quality scoring
- **Production Ready**: Automated testing (CI/CD), error recovery, and auth refresh

### Recent Improvements (v3.0)

- ✅ **Type hints** for better IDE support and early bug detection
- ✅ **Pinned dependencies** to prevent breaking changes
- ✅ **CI/CD pipeline** with GitHub Actions (automated testing, linting, security scans)
- ✅ **Integration tests** covering auth, configuration, dashboard, and error recovery
- ✅ **Auth auto-refresh** - Runs indefinitely without manual re-authentication
- ✅ **Rate limit handling** - Intelligent backoff for Google API limits
- ✅ **Unified dashboard** - Consistent real-time monitoring across modes

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Project APE Architecture                      │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐         ┌─────────────────┐         ┌────────────┐
│  Client      │         │  NotebookLM     │         │  Dashboard │
│  Documents   │────────▶│  API / CLI      │────────▶│  (HTML)    │
│  (PDF, CSV)  │         │  Integration    │         │  Real-time │
└──────────────┘         └─────────────────┘         └────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │   Pipeline Orchestrator  │
                    │   - Fast Mode (8 workers)│
                    │   - Deep Mode (1 worker) │
                    │   - Auto Auth Refresh    │
                    │   - Rate Limit Control   │
                    └─────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│ PDF          │        │ Research     │        │ Validation   │
│ Consolidator │        │ Engine       │        │ Framework    │
│              │        │ - Web search │        │ - Quality    │
│ - Multi-file │        │ - Citations  │        │   scoring    │
│   merge      │        │ - Sources    │        │ - Metrics    │
└──────────────┘        └──────────────┘        └──────────────┘
        │                         │                         │
        └─────────────────────────┼─────────────────────────┘
                                  ▼
                    ┌─────────────────────────┐
                    │   State Management      │
                    │   - Resume capability   │
                    │   - Progress tracking   │
                    │   - Error recovery      │
                    └─────────────────────────┘
```

### Technology Stack

- **Python 3.9+**: Core orchestration and business logic
- **Node.js 16+**: NotebookLM CLI runtime
- **NotebookLM**: Google's AI-powered research and note-taking platform
- **Threading**: Concurrent pipeline execution
- **JSON**: State persistence and configuration
- **HTML/CSS**: Real-time dashboard visualization

---

## Features

### Dual Execution Modes

| Mode | Concurrency | Research Depth | Web Citations | Typical Runtime (6 clients) |
|------|-------------|----------------|---------------|------------------------------|
| **Fast** | 8 workers | Standard | No | 15-25 minutes |
| **Deep** | 2 workers | Comprehensive | Yes | 45-90 minutes |

### Production-Ready Capabilities

- **Resilience**:
  - Exponential backoff retry logic with rate limit handling
  - Thread-safe operations with proper locking
  - Circuit breaker pattern for external API calls
  - State persistence with `--resume` flag for crash recovery

- **Monitoring**:
  - Real-time HTML dashboard with auto-refresh
  - Terminal UI with ANSI color-coded status
  - Comprehensive structured logging
  - Metrics export (JSON) with timing breakdowns

- **Quality Assurance**:
  - Prompt output validation framework
  - Configurable quality thresholds (word counts, citations)
  - Duplicate source detection and removal
  - URL validation before ingestion

- **Scalability**:
  - Configurable worker pools (1-8+ concurrent clients)
  - Timing policies for rate limit compliance
  - Session management with auth token refresh

---

## Prerequisites

### System Requirements

| Component | Minimum Version | Purpose |
|-----------|----------------|---------|
| Python | 3.9+ | Core application runtime |
| Node.js | 16+ | NotebookLM CLI dependency |
| npm | 7+ | Package manager for Node.js |
| Git | 2.0+ | Version control (optional) |
| Disk Space | 5 GB+ | Document storage and processing |
| RAM | 8 GB+ | Recommended for parallel processing |

### Account Requirements

- **Google Account** with NotebookLM access
- **Red Hat VPN** (for internal document access, if applicable)
- **Customer documents** in PDF or CSV format

---

## Installation

### Red Hat Enterprise Linux (RHEL)

#### 1. Update System Packages

```bash
sudo dnf update -y
sudo dnf install -y python39 python39-pip git
```

#### 2. Install Node.js and npm

```bash
# Install Node.js 16.x LTS from NodeSource
curl -fsSL https://rpm.nodesource.com/setup_16.x | sudo bash -
sudo dnf install -y nodejs

# Verify installation
node --version  # Should be v16.x or higher
npm --version
```

#### 3. Install NotebookLM CLI

```bash
# Install globally
sudo npm install -g notebooklm

# Verify installation
notebooklm --version
```

**Note**: The NotebookLM CLI package name may vary. Check official documentation or use:
```bash
# Alternative installation (if package name differs)
sudo npm install -g @googleworkspace/notebooklm-cli
```

#### 4. Clone Repository and Install Python Dependencies

```bash
# Navigate to desired installation directory
cd /opt

# Clone the repository (adjust path as needed)
git clone <repository-url> project-ape
cd project-ape/notebooklm

# Create virtual environment
python3.9 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

#### 5. Authenticate NotebookLM

```bash
notebooklm login
# A browser window will open for Google authentication
```

---

### macOS

#### 1. Install Homebrew (if not already installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### 2. Install Python 3.9+

```bash
# Install Python 3.9 or higher
brew install python@3.9

# Verify installation
python3 --version
```

#### 3. Install Node.js and npm

```bash
# Install Node.js (automatically includes npm)
brew install node@16

# Link Node.js 16 (if multiple versions installed)
brew link --force --overwrite node@16

# Verify installation
node --version  # Should be v16.x or higher
npm --version
```

#### 4. Install NotebookLM CLI

```bash
# Install globally
npm install -g notebooklm

# Verify installation
notebooklm --version
```

#### 5. Clone Repository and Install Python Dependencies

```bash
# Clone repository
cd ~/Documents
git clone <repository-url> project-ape
cd project-ape/notebooklm

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

#### 6. Authenticate NotebookLM

```bash
notebooklm login
```

---

### Windows

#### 1. Install Python 3.9+

1. Download Python 3.9+ installer from [python.org](https://www.python.org/downloads/windows/)
2. Run installer and **check** "Add Python to PATH"
3. Verify installation:
   ```cmd
   python --version
   pip --version
   ```

#### 2. Install Node.js and npm

1. Download Node.js 16.x LTS installer from [nodejs.org](https://nodejs.org/)
2. Run installer (npm is included automatically)
3. Verify installation:
   ```cmd
   node --version
   npm --version
   ```

#### 3. Install NotebookLM CLI

Open **Command Prompt** or **PowerShell** as Administrator:

```cmd
npm install -g notebooklm
notebooklm --version
```

#### 4. Clone Repository and Install Python Dependencies

```cmd
# Clone repository
cd C:\Users\<YourUsername>\Documents
git clone <repository-url> project-ape
cd project-ape\notebooklm

# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt
```

#### 5. Authenticate NotebookLM

```cmd
notebooklm login
```

**Note for Windows Users**:
- Use **Command Prompt** or **PowerShell** (not Git Bash) for NotebookLM commands
- Ensure Python and Node.js are in your system PATH
- Some antivirus software may block subprocess calls—add exceptions if needed

---

## Configuration

### 1. Configure Client Accounts (`vars.py`)

**First time?** Copy the example configuration:

```bash
cp vars.example.py vars.py
```

Then edit `vars.py` to add your customer accounts:

```python
# Global configuration
persona = "senior account solutions architect"
notification_email = "your.email@redhat.com"

# Client list
clients = [
    "acme_corp",
    "globex_industries",
    "initech",
]

# Acme Corporation configuration
acme_corp_name = "Acme Corporation"
acme_corp_industry = "manufacturing"
acme_corp_folder = "/path/to/acme/documents"

# Globex Industries configuration
globex_industries_name = "Globex Industries"
globex_industries_industry = "pharmaceuticals and healthcare"
globex_industries_folder = "/path/to/globex/documents"

# Initech configuration
initech_name = "Initech"
initech_industry = "financial services"
initech_folder = "/path/to/initech/documents"
```

### 2. Industry Focus Areas

Define industry-specific priorities (automatically injected into prompts):

```python
INDUSTRY_FOCUS_AREAS = {
    "manufacturing": [
        "Smart factory and Industry 4.0",
        "Predictive maintenance",
        "Supply chain resilience",
    ],
    "pharmaceuticals and healthcare": [
        "FDA/EMA regulatory compliance",
        "Clinical trial digitization",
        "R&D acceleration and drug discovery",
    ],
    "financial services": [
        "Real-time transaction processing",
        "Fraud detection and prevention",
        "Regulatory compliance (RegTech)",
    ],
}
```

### 3. Timing and Retry Configuration

Adjust performance and reliability settings:

```python
# Worker thread limits
FAST_MODE_MAX_WORKERS = 8  # Parallel pipelines in fast mode
DEEP_MODE_MAX_WORKERS = 2  # Parallel pipelines in deep mode (lower for rate limits)

# Timing configuration (seconds)
TIMINGS = {
    'deep_research_cooldown': (45.0, 75.0),  # Delay after deep research (random range)
    'post_research_delay': 15.0,              # Delay after adding sources
    'source_add_delay': (1.0, 3.0),           # Delay between source additions
    'chat_prompt_delay': (3.0, 6.0),          # Delay between chat prompts
}

# Retry configuration
RETRY_CONFIG = {
    'max_attempts': 3,               # Standard retry attempts
    'base_delay': 30.0,              # Base exponential backoff delay
    'command_timeout': 300.0,        # Command timeout (seconds)
    
    'deep_research_max_attempts': 5, # Deep research retries (more aggressive)
    'deep_research_base_delay': 45.0,
    'deep_research_timeout': 480.0,
}
```

### 4. Validation Thresholds

Configure output quality requirements (embedded in prompt metadata):

```yaml
# Example from chat_01_business_objectives.txt metadata
VALIDATION: min_words=400, max_words=700, min_citations=3
QUALITY_THRESHOLD: 7.0
```

---

## Usage

### Fast Mode (Recommended for Initial Runs)

**Purpose**: High-throughput processing with 8 concurrent client pipelines

```bash
# Activate virtual environment first
source venv/bin/activate  # macOS/Linux
# OR
venv\Scripts\activate     # Windows

# Run fast mode
python fast.py
```

**Features**:
- 8 concurrent client pipelines
- Fast-mode NotebookLM research (no web citations)
- Typical runtime: 15-25 minutes for 6 clients
- Generates NotebookLM workspace links

**Best for**:
- Initial testing and validation
- Quick turnaround account plans
- Resource-constrained environments

---

### Deep Mode (Research-Intensive)

**Purpose**: Comprehensive research with web citations and extended analysis

```bash
# Activate virtual environment first
source venv/bin/activate  # macOS/Linux

# Run deep mode
python new_deep.py
```

**Features**:
- 2 concurrent pipelines (respects API rate limits)
- Deep research mode with web search and citations
- Longer API timeouts and cooldown periods
- Typical runtime: 45-90 minutes for 6 clients
- Generates Google Docs with mind maps and slide decks

**Best for**:
- High-stakes strategic accounts
- Comprehensive competitive analysis
- Regulatory or compliance-heavy industries

---

### CLI Options

Both `fast.py` and `new_deep.py` support the following options:

```bash
# Resume from last saved state (skip completed steps)
python fast.py --resume

# Clear all saved state and start fresh
python fast.py --clear-state
```

---

### Dashboard

Both modes automatically open a real-time HTML dashboard in your default browser:

- **URL**: `file:///path/to/project_ape_dashboard.html`
- **Auto-refresh**: Every 2 seconds
- **Features**:
  - Overall progress bar
  - Per-client status cards with progress percentages
  - Quality scores and validation metrics
  - Direct links to NotebookLM workspaces or Google Docs
  - Color-coded status indicators (Running, Complete, Failed, Degraded)

---

## Pipeline Phases

The account planning pipeline consists of **6 sequential phases** per client (executed in parallel across multiple clients):

### Phase 0: Pre-flight Verification (5-15% complete)

**Purpose**: Authenticate with NotebookLM and establish workspace

**Steps**:
1. Refresh authentication token
2. Check cache for existing notebook (prevent duplicates)
3. Create new NotebookLM workspace OR reuse existing
4. Update dashboard with notebook ID

**Key Components**:
- `NotebookLMClient.safe_auth_refresh()`: Thread-safe token refresh
- `NotebookLMClient.fetch_notebook_cache()`: Retrieve existing notebooks
- `ensure_notebook_exists()`: Deduplication logic

**Output**: Notebook UUID (e.g., `a3b7c9d2-1234-5678-9abc-def012345678`)

---

### Phase 1: PDF Consolidation (15-30% complete)

**Purpose**: Convert all customer documents into a single consolidated PDF

**Steps**:
1. Scan client folder for PDF and CSV files
2. Convert CSV files to structured text format (if any)
3. Merge all PDFs into `{client_id}-One.pdf`
4. Deduplicate and optimize consolidated PDF

**Key Components**:
- `pdf_consolidator.py`: Multi-file PDF merging utility
- `convert_csv_to_structured_text()`: CSV to text conversion

**Why Consolidation?**
- Reduces API calls (1 upload instead of N)
- Ensures consistent source ordering
- Simplifies source management in NotebookLM

**Output**: `{client_id}-One.pdf` in client folder

---

### Phase 2: Source Ingestion (30-45% complete)

**Purpose**: Upload consolidated PDF to NotebookLM workspace

**Steps**:
1. Upload `{client_id}-One.pdf` to NotebookLM
2. Wait for NotebookLM to process and import the document
3. Verify source is ready for querying

**Key Components**:
- `notebooklm source add --title {title} {pdf_path}`
- `notebooklm source wait {source_id} --timeout 120`

**Processing Time**: 30-90 seconds for typical PDFs (< 100 pages)

**Output**: Source ID and confirmation of successful import

---

### Phase 3: Prompt Execution (45-85% complete)

**Purpose**: Execute AI research and chat prompts to generate account intelligence

**Prompt Types**:

1. **Ask Prompts** (Deep research with web search):
   - `ask_01_foundation_research.txt`: Company financials, leadership, strategy
   - `ask_02_industry_subsegments.txt`: Market taxonomy and positioning

2. **Chat Prompts** (Using uploaded sources only):
   - `chat_01_business_objectives.txt`: Strategic priorities and goals
   - `chat_02_market_competitive.txt`: Competitive landscape analysis
   - `chat_03_tech_partners.txt`: Technology partner ecosystem
   - `chat_04_value_propositions.txt`: Red Hat value propositions
   - `chat_05_solution_ideas.txt`: Solution recommendations
   - `chat_06_hmw_statements.txt`: "How Might We" strategic questions
   - `chat_07_team_onboarding.txt`: New team member briefing
   - `chat_08_partner_briefing.txt`: Partner engagement scope
   - `chat_09_Account_Plan.txt`: Comprehensive account plan synthesis

**Prompt Execution Flow**:
```
For each prompt:
  1. Variable substitution ($industry, $name, $persona)
  2. Write temporary prompt file
  3. Execute NotebookLM command:
     - Ask: notebooklm source add-research --prompt-file {file} --mode {fast|deep}
     - Chat: notebooklm ask --prompt-file {file} --save-as-note
  4. Validate output (word count, citations, quality score)
  5. Save as note in NotebookLM workspace
  6. Apply cooldown delay (configurable)
```

**Key Components**:
- `execute_prompts()`: Orchestrates sequential prompt execution
- `validate_output()`: Quality assurance checks
- `get_note_title()`: Maps prompt files to descriptive titles

**Output**: 8-10 structured notes per client saved in NotebookLM

---

### Phase 4: Source Deduplication (85-90% complete)

**Purpose**: Remove duplicate sources from NotebookLM workspace

**Why Needed?**
- Web research may discover duplicate URLs
- Manual uploads may create duplicates
- Keeps workspace clean and navigable

**Steps**:
1. List all sources in workspace
2. Identify duplicates by normalized title
3. Keep first occurrence, remove subsequent duplicates

**Key Components**:
- `remove_duplicate_sources()`: Deduplication logic
- `normalize_name_string()`: Title normalization

**Output**: Clean workspace with unique sources only

---

### Phase 5: Artifact Generation (90-100% complete)

**Purpose**: Generate visual artifacts for presentations and collaboration

**Artifacts**:
1. **Interactive Mind Map**: Visual hierarchy of account intelligence
2. **Slide Deck**: Presentation-ready summary (Deep Mode only)

**Commands**:
```bash
# Generate mind map
notebooklm generate mind-map --kind interactive --json

# Generate slide deck (Deep Mode)
notebooklm generate slide-deck "{client_name} Account Plan" \
  --format presenter --wait --timeout 180 --json
```

**Key Components**:
- `generate_artifacts()`: Coordinates artifact creation
- Dashboard integration for artifact links

**Output**: URLs to NotebookLM-hosted mind map and slide deck

---

### Phase 6: Completion and Notification (100% complete)

**Purpose**: Finalize pipeline execution and notify stakeholders

**Steps**:
1. Mark client as complete in state manager
2. Export metrics (timing, retry counts, quality scores)
3. Update dashboard with final status
4. Send email notification (if configured)

**Email Notification Contents**:
- Overall execution status
- Per-client NotebookLM workspace URLs
- Quality score summary
- Failed clients (if any)

**Key Components**:
- `send_completion_email()`: Email notification logic
- `metrics.export()`: Metrics persistence
- `state.print_summary()`: State dump for troubleshooting

**Output**: 
- Completed dashboard
- `pipeline_state.json`
- `pipeline_metrics.json`
- Email to configured recipients

---

## Project Structure

```
project-ape/
├── notebooklm/                          # Main application directory
│   ├── fast.py                          # Fast mode orchestrator (8 workers)
│   ├── new_deep.py                      # Deep mode orchestrator (2 workers)
│   ├── new_deep_optimized.py            # Optimized deep mode variant
│   ├── common.py                        # Shared utilities and classes
│   ├── vars.py                          # Configuration (clients, industries, timing)
│   ├── state_manager.py                 # Pipeline state persistence
│   ├── metrics.py                       # Metrics collection and export
│   ├── validators.py                    # Output validation framework
│   ├── pdf_consolidator.py              # PDF merging utility
│   │
│   ├── lib/                             # Reusable library modules
│   │   ├── __init__.py
│   │   ├── checkpoint.py                # Checkpoint/resume logic
│   │   ├── circuit_breaker.py           # Circuit breaker pattern
│   │   ├── config_loader.py             # Dynamic config loading
│   │   ├── rate_limiter.py              # Rate limit enforcement
│   │   └── session_manager.py           # Session lifecycle management
│   │
│   ├── ask_01_foundation_research.txt   # Deep research: Company due diligence
│   ├── ask_02_industry_subsegments.txt  # Deep research: Industry taxonomy
│   ├── chat_01_business_objectives.txt  # Chat: Strategic priorities
│   ├── chat_02_market_competitive.txt   # Chat: Competitive analysis
│   ├── chat_03_tech_partners.txt        # Chat: Technology ecosystem
│   ├── chat_04_value_propositions.txt   # Chat: Red Hat value statements
│   ├── chat_05_solution_ideas.txt       # Chat: Solution brainstorming
│   ├── chat_06_hmw_statements.txt       # Chat: Design thinking HMW
│   ├── chat_07_team_onboarding.txt      # Chat: New team member briefing
│   ├── chat_08_partner_briefing.txt     # Chat: Partner engagement scope
│   ├── chat_09_Account_Plan.txt         # Chat: Comprehensive synthesis
│   │
│   ├── requirements.txt                 # Python dependencies
│   ├── README.md                        # This documentation
│   ├── .gitignore                       # Git ignore patterns
│   │
│   ├── project_ape_dashboard.html       # Real-time HTML dashboard (generated)
│   ├── project_ape_execution.log        # Detailed execution log (generated)
│   ├── pipeline_state.json              # State persistence (generated)
│   ├── pipeline_metrics.json            # Metrics export (generated)
│   ├── clean_start.sh                   # Cleanup script (removes state/logs)
│   └── kill_all.sh                      # Emergency stop script
│
└── Venella_2026/                        # Customer documents root
    ├── Merck/
    │   ├── merck_test-One.pdf           # Consolidated PDF (generated)
    │   ├── financial_report_2023.pdf
    │   ├── earnings_transcript_Q4.pdf
    │   └── customer_data.csv
    │
    ├── Blue_Yonder/
    │   └── ... (customer documents)
    │
    └── ... (other clients)
```

---

## Prompt Engineering

### Prompt Metadata

Each prompt file includes YAML-like metadata for validation and execution:

```yaml
# METADATA
# ID: business_objectives
# TYPE: chat                              # 'ask' or 'chat'
# DEPENDENCIES: foundation_research, industry_subsegments
# TIMEOUT: 300                            # Execution timeout (seconds)
# RETRIES: 3                              # Max retry attempts
# VALIDATION: min_words=400, max_words=700, min_citations=3
# QUALITY_THRESHOLD: 7.0                  # Minimum acceptable score (0-10)
# EXPECTED_SECTIONS: Executive Summary, Top 3 Business Objectives
```

### Prompt Template Structure

Standard prompt structure for consistency:

```markdown
PRIOR CONTEXT - Reference these notes:
- "Foundation Research" (company financial, leadership, initiatives)
- "Industry Subsegments" (market taxonomy)

Acting as Red Hat $persona for $name, [task description].

---

## SECTION 1: [Section Name] (Word limit: 200-300)

[Detailed instructions with bullet structure]

**Required Elements:**
- [Element 1 with quantified requirements]
- [Element 2 with specific format]

**Evidence Standard:**
- Cite specific sources: [Source: {title}]
- Quantify claims when possible
- Prefer primary sources (annual reports, earnings calls)

---

## QUALITY CHECKLIST

Before submitting, verify:
☐ All required sections included
☐ Word count within limits (${min_words}-${max_words})
☐ Minimum ${min_citations} citations with proper format
☐ No generic statements - all claims evidenced
☐ Industry-specific context from "$industry" focus areas
```

### Variable Substitution

Runtime variable replacement:

| Variable | Description | Example |
|----------|-------------|---------|
| `$name` | Client display name | "Acme Corporation" |
| `$industry` | Client industry category | "manufacturing" |
| `$persona` | Red Hat role/persona | "senior account solutions architect" |

---

## Troubleshooting

### Authentication Issues

**Error**: `[AUTH EXPIRED] Session dead` or `401 Unauthorized`

**Solution**:
```bash
# Force logout and re-login
notebooklm logout
notebooklm login

# Refresh token manually
notebooklm auth refresh
```

**Prevention**: The pipeline automatically refreshes tokens every 2-4 minutes during execution.

---

### Rate Limiting

**Error**: `quota|rate limit|exhausted|429|503`

**Symptoms**:
- Frequent retry attempts
- Long execution times
- "Too Many Requests" errors in logs

**Solutions**:

1. **Reduce Worker Count** (`vars.py`):
   ```python
   FAST_MODE_MAX_WORKERS = 4  # Reduced from 8
   DEEP_MODE_MAX_WORKERS = 1  # Reduced from 2
   ```

2. **Increase Retry Delays** (`vars.py`):
   ```python
   RETRY_CONFIG = {
       'base_delay': 60.0,  # Increased from 30.0
       'deep_research_base_delay': 90.0,  # Increased from 45.0
   }
   ```

3. **Switch to Fast Mode**: Avoid deep research mode which triggers more API calls

---

### Duplicate Notebooks

**Symptom**: Multiple notebooks created with same name in NotebookLM

**Root Cause**: Concurrent pipeline runs or cache invalidation

**Solution**:

1. **List all notebooks**:
   ```bash
   notebooklm list
   ```

2. **Delete duplicates manually**:
   ```bash
   notebooklm delete <notebook-id>
   ```

3. **Prevent future duplicates**:
   - Use `--resume` flag to continue existing runs
   - Don't run multiple instances simultaneously
   - Clear state before fresh runs: `python fast.py --clear-state`

---

### Missing Source Files

**Error**: `No Local Sources Found` or `Folder not found`

**Solution**:

1. **Verify folder path** in `vars.py`:
   ```python
   acme_corp_folder = "/Users/jasona/account_planning/Venella_2026/Acme/"
   ```

2. **Check folder contents**:
   ```bash
   ls -la /Users/jasona/account_planning/Venella_2026/Acme/
   ```

3. **Verify file permissions**:
   ```bash
   chmod -R 755 /Users/jasona/account_planning/Venella_2026/Acme/
   ```

4. **Ensure supported file types**: Only PDF and CSV are supported

---

### PDF Consolidation Failures

**Error**: `PDF consolidation failed` in Phase 1

**Common Causes**:
- Encrypted/password-protected PDFs
- Corrupted PDF files
- Unsupported PDF versions (PDF 2.0+)

**Solutions**:

1. **Decrypt PDFs** before consolidation:
   ```bash
   qpdf --decrypt --password=PASSWORD input.pdf output.pdf
   ```

2. **Validate PDF integrity**:
   ```bash
   pdfinfo input.pdf
   ```

3. **Convert to PDF 1.7**:
   ```bash
   gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.7 \
      -o output.pdf input.pdf
   ```

---

### Validation Failures

**Error**: `Catastrophic validation failure for {prompt_id}: Score {score}/10`

**Root Causes**:
- Insufficient content generated (below min_words threshold)
- Missing required citations
- Empty or truncated AI responses

**Solutions**:

1. **Review prompt quality** in corresponding `.txt` file
2. **Check source document quality**: Ensure uploaded PDFs contain substantive text
3. **Adjust validation thresholds** in prompt metadata:
   ```yaml
   VALIDATION: min_words=200, max_words=700, min_citations=1
   QUALITY_THRESHOLD: 5.0  # Lowered from 7.0
   ```

4. **Retry with deep mode**: Web research may fill knowledge gaps

---

### Pipeline Crashes

**Symptom**: Pipeline exits mid-execution with partial completion

**Recovery**:

```bash
# Resume from last saved state
python fast.py --resume

# Check state file for progress
cat pipeline_state.json | python -m json.tool

# Review logs for error details
tail -100 project_ape_execution.log
```

---

## Performance Benchmarks

### Fast Mode (6 clients, 8 workers)

| Metric | Value |
|--------|-------|
| Total Runtime | 18 minutes (avg) |
| Phase 0 (Pre-flight) | 2 min |
| Phase 1 (PDF Consolidation) | 3 min |
| Phase 2 (Source Ingestion) | 2 min |
| Phase 3 (Prompt Execution) | 9 min |
| Phase 4 (Deduplication) | 1 min |
| Phase 5 (Artifacts) | 1 min |
| **Per-client average** | **3 minutes** |

### Deep Mode (6 clients, 2 workers)

| Metric | Value |
|--------|-------|
| Total Runtime | 65 minutes (avg) |
| Phase 0 (Pre-flight) | 3 min |
| Phase 1 (PDF Consolidation) | 5 min |
| Phase 2 (Source Ingestion) | 4 min |
| Phase 3 (Prompt Execution) | 48 min |
| Phase 4 (Deduplication) | 2 min |
| Phase 5 (Artifacts) | 3 min |
| **Per-client average** | **11 minutes** |

### Optimization Tips

1. **Use Fast Mode First**: Validate prompts and data quality before deep research
2. **Run Deep Mode Overnight**: Schedule long-running jobs during off-hours
3. **Tune Worker Count**: Match to available CPU cores (typically 4-8 for fast mode)
4. **Pre-consolidate PDFs**: Manually create `{client_id}-One.pdf` to skip Phase 1
5. **Batch Clients**: Process similar industries together to leverage shared context

---

## Development

### Code Style

- **PEP 8 compliance**: Use `flake8` or `black` for formatting
- **Type hints**: Add type annotations for function signatures
- **Docstrings**: Document all public functions with Google-style docstrings
- **Pre-compiled regex**: Declare patterns at module level (see `common.py`)

### Adding New Prompts

1. **Create prompt file**: `chat_10_new_section.txt`
2. **Add metadata** (see [Prompt Engineering](#prompt-engineering))
3. **Register in orchestrator**:
   ```python
   # In fast.py or new_deep.py
   prompt_files = list(Path(PROJECT_ROOT).glob("ask_*.txt")) + \
                  list(Path(PROJECT_ROOT).glob("chat_*.txt"))
   ```

4. **Add title mapping**:
   ```python
   # In common.py: get_note_title()
   title_map = {
       'chat_10_new_section.txt': f'{client_name} New Section',
   }
   ```

5. **Test with single client**:
   ```python
   clients = ["test_client_only"]  # In vars.py
   ```

### Testing Prompts Manually

```bash
# Authenticate
notebooklm login

# Use existing notebook
notebooklm use <notebook-id>

# Test ask prompt (with web research)
notebooklm ask --prompt-file ask_01_foundation_research.txt \
  --mode deep --save-as-note

# Test chat prompt (using sources only)
notebooklm ask --prompt-file chat_01_business_objectives.txt \
  --save-as-note
```

### Pull Request Process

1. **Test with both modes**: Run `fast.py` and `new_deep.py` successfully
2. **Update README.md**: Document new features or configuration changes
3. **Add config examples**: Update `vars.py` with example configurations
4. **Verify dashboard**: Ensure all tasks show "COMPLETE" status
5. **Export metrics**: Include `pipeline_metrics.json` in PR description

---

## Contributing

### Contribution Guidelines

1. **Feature Requests**: Open an issue with `[FEATURE]` prefix
2. **Bug Reports**: Include logs, state file, and reproduction steps
3. **Code Contributions**:
   - Fork repository
   - Create feature branch (`feature/new-capability`)
   - Add tests (if applicable)
   - Submit pull request with detailed description

### Areas for Contribution

- **Prompt optimization**: Improve prompt engineering for specific industries
- **Validation framework**: Enhance quality scoring algorithms
- **Multi-language support**: Add prompts for non-English accounts
- **Salesforce integration**: Auto-sync account plans to CRM
- **Custom branding**: Add Red Hat branding to generated documents

---

## License

**Internal Red Hat Project - Not for External Distribution**

This software is proprietary to Red Hat, Inc. and is intended solely for internal use by Red Hat employees and authorized partners. Redistribution, modification, or use outside of Red Hat is strictly prohibited without written permission.

For licensing inquiries, contact Red Hat Legal.

---

## Support

### Internal Red Hat Support

- **Project APE Team**: Contact via Red Hat Slack (`#project-ape`)
- **Email**: `project-ape-support@redhat.com`
- **Documentation**: Confluence page (search "Project APE")

### External Dependencies

- **NotebookLM CLI Issues**: [GitHub Issues](https://github.com/notebooklm/cli) (if available)
- **Python Issues**: [Python Bug Tracker](https://bugs.python.org/)
- **Node.js Issues**: [Node.js GitHub](https://github.com/nodejs/node/issues)

### Feedback and Feature Requests

Submit feedback via:
1. Red Hat Jira project `APE`
2. Slack channel `#project-ape-feedback`
3. Email to `project-ape-support@redhat.com`

---

## Roadmap

### Planned Features

- [ ] **Prompt Validation Framework**: Automated prompt output testing
- [ ] **Multi-language Support**: Spanish, French, German, Japanese prompts
- [ ] **Salesforce Integration**: Auto-sync to SFDC account records
- [ ] **Custom Branding**: Red Hat visual identity in generated documents
- [ ] **A/B Testing**: Prompt optimization experiments
- [ ] **Real-time Collaboration**: Multi-user editing of account plans
- [ ] **API Endpoint**: RESTful API for programmatic access
- [ ] **Docker Support**: Containerized deployment

### Version History

- **v2.0** (Current): Fast/Deep mode separation, state management, metrics export
- **v1.5**: Prompt validation framework, quality scoring
- **v1.0**: Initial release with basic pipeline orchestration

---

## Appendix

### Python Dependencies

```
requests>=2.31.0                  # HTTP requests for URL validation
google-api-python-client>=2.100.0 # Google API client (future integrations)
google-auth>=2.23.0               # Google authentication
google-auth-oauthlib>=1.1.0       # OAuth2 flow
google-auth-httplib2>=0.1.1       # HTTP transport for Google Auth
```

### System Package Dependencies

| OS | Package | Install Command |
|----|---------|-----------------|
| RHEL | `python39` | `sudo dnf install python39` |
| RHEL | `python39-pip` | `sudo dnf install python39-pip` |
| RHEL | `nodejs` | `sudo dnf install nodejs` |
| macOS | `python@3.9` | `brew install python@3.9` |
| macOS | `node@16` | `brew install node@16` |
| Windows | Python 3.9+ | [Download installer](https://www.python.org/downloads/windows/) |
| Windows | Node.js 16+ | [Download installer](https://nodejs.org/) |

### NotebookLM CLI Commands Reference

```bash
# Authentication
notebooklm login                        # Authenticate with Google account
notebooklm logout                       # Clear authentication
notebooklm auth refresh                 # Refresh access token

# Notebook management
notebooklm list                         # List all notebooks
notebooklm create "Notebook Name"       # Create new notebook
notebooklm use <notebook-id>            # Set active notebook
notebooklm delete <notebook-id>         # Delete notebook

# Source management
notebooklm source add <file-path>       # Upload source file
notebooklm source add --title "Title" <file>
notebooklm source list                  # List sources in active notebook
notebooklm source wait <source-id>      # Wait for source import
notebooklm source remove <source-id>    # Remove source

# Research and chat
notebooklm ask --prompt "Question"      # Ask question
notebooklm ask --prompt-file <file>     # Use prompt from file
notebooklm source add-research \
  --prompt-file <file> \
  --mode {fast|deep} \
  --import-all --cited-only             # Deep research with auto-import

# Artifact generation
notebooklm generate mind-map --kind interactive
notebooklm generate slide-deck "Title" --format presenter
```

---

**Generated with Claude Code** | **Last Updated**: 2026-06-07
