# Project APE - Setup Guide

**Quick Start Guide for New Users**

---

## Prerequisites

Before starting, ensure you have:

- ✅ Python 3.9 or higher
- ✅ Node.js 16 or higher
- ✅ Google account (personal Gmail recommended - **NOT** enterprise SSO account)
- ✅ Customer documents (PDFs, CSVs) organized by account
- ✅ ~30 minutes for initial setup

---

## Step-by-Step Setup

### Step 1: Install System Dependencies

#### macOS (Recommended)

```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.9+
brew install python@3.11

# Install Node.js 18+
brew install node@18
```

#### Red Hat Enterprise Linux (RHEL)

```bash
# Update system
sudo dnf update -y

# Install Python 3.9+
sudo dnf install -y python39 python39-pip

# Install Node.js 18+ from NodeSource
curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -
sudo dnf install -y nodejs
```

#### Windows

1. Download and install [Python 3.11](https://www.python.org/downloads/windows/)
   - ✅ Check "Add Python to PATH"
2. Download and install [Node.js 18 LTS](https://nodejs.org/)
   - ✅ Includes npm automatically

---

### Step 2: Install NotebookLM CLI

```bash
# Install globally
npm install -g notebooklm

# Verify installation
notebooklm --version
```

**Expected output:** `notebooklm version X.X.X`

**Troubleshooting:**
- If `command not found`, add npm global bin to PATH
- macOS: Add `export PATH="$PATH:$(npm bin -g)"` to `~/.zshrc`
- Windows: Restart terminal after Node.js installation

---

### Step 3: Clone/Download Project APE

```bash
# Option A: Clone from Git (if available)
git clone <repository-url> project-ape
cd project-ape/notebooklm

# Option B: Download and extract ZIP
cd project-ape/notebooklm
```

---

### Step 4: Install Python Dependencies

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# macOS/Linux:
source venv/bin/activate

# Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

**Expected output:**
```
Successfully installed requests-2.34.2 google-api-python-client-2.197.0 ...
```

---

### Step 5: Authenticate with NotebookLM

**IMPORTANT:** Use a **personal Gmail account** (NOT your work/enterprise account)

#### Why Personal Gmail?

❌ **Work/Enterprise Accounts:**
- Require SSO authentication
- Cannot run unattended
- Short session timeouts (~30-60 min)
- Will require re-login every hour

✅ **Personal Gmail:**
- No SSO required
- Runs unattended overnight
- Long session tokens (6+ hours)
- Auto-refresh works perfectly

#### Authentication Steps

```bash
# Logout if previously authenticated with work account
notebooklm logout

# Login with PERSONAL Gmail
notebooklm login
```

**Browser will open:**
1. Click "Sign in with Google"
2. Select your **PERSONAL** Gmail account (e.g., yourname@gmail.com)
3. Grant permissions
4. Close browser tab when prompted

**Verify authentication:**
```bash
notebooklm list
```

**Expected:** List of notebooks (may be empty if first time)

**If you see SSO/SAML errors:** You're using a work account - logout and use personal Gmail

---

### Step 6: Configure Your Clients

#### Copy Example Configuration

```bash
# Copy example file to vars.py
cp vars.example.py vars.py
```

#### Edit vars.py

Open `vars.py` in your editor and update:

**1. Update notification email:**
```python
notification_email = "your.email@company.com"
```

**2. Define your clients:**
```python
clients = [
    "acme_corp",
    "globex_industries",
]
```

**3. Configure each client:**
```python
# Acme Corporation
acme_corp_name = "Acme Corporation"
acme_corp_industry = "manufacturing"  # Must match INDUSTRY_FOCUS_AREAS
acme_corp_folder = "/path/to/customer/documents/Acme/"

# Globex Industries
globex_industries_name = "Globex Industries"
globex_industries_industry = "pharmaceuticals and healthcare"
globex_industries_folder = "/path/to/customer/documents/Globex/"
```

**4. Verify folder paths exist:**
```bash
# Check that folders contain PDFs/CSVs
ls -lh /path/to/customer/documents/Acme/
ls -lh /path/to/customer/documents/Globex/
```

---

### Step 7: Organize Customer Documents

**Folder Structure:**
```
/path/to/customer/documents/
├── Acme/
│   ├── annual_report_2023.pdf
│   ├── earnings_transcript_Q4.pdf
│   ├── customer_data.csv
│   └── presentation_deck.pdf
│
└── Globex/
    ├── financial_report.pdf
    ├── investor_presentation.pdf
    └── market_analysis.csv
```

**Best Practices:**
- ✅ Keep all documents in **one folder per client**
- ✅ Use **descriptive filenames**
- ✅ Include PDFs (annual reports, presentations, financial docs)
- ✅ Include CSVs (customer data, market data)
- ❌ Don't include password-protected PDFs
- ❌ Don't include PDFs > 100MB each

---

### Step 8: Test Configuration

```bash
# Validate configuration
python -c "import vars; print(f'✅ Loaded {len(vars.clients)} clients')"
```

**Expected output:**
```
✅ Loaded 2 clients
```

**If error:** Check vars.py syntax, ensure all required attributes defined

---

### Step 9: Run Your First Account Plan

#### Start with Fast Mode (Recommended for Testing)

```bash
# Run fast mode
python fast.py
```

**What happens:**
1. Dashboard opens in browser automatically
2. Script processes all clients in parallel (8 workers)
3. Real-time progress updates in dashboard
4. Estimated runtime: 15-25 minutes for 6 clients

**Monitor progress:**
- Dashboard: Auto-refreshes every 2 seconds
- Logs: `tail -f project_ape_execution.log`

**Expected completion:**
- All clients show "COMPLETE" status
- NotebookLM links appear in dashboard
- Mind maps and slide decks generated

---

### Step 10: Review Results

#### Open NotebookLM Workspace

1. Click "View in NotebookLM" link in dashboard
2. Review AI-generated notes:
   - Foundation Research
   - Industry Subsegment Analysis
   - Business Objectives
   - Competitive Landscape
   - Technology Partners
   - Red Hat Value Propositions
   - Solution Ideas
   - "How Might We" Statements
   - Team Onboarding Guide
   - Partner Briefing
   - Comprehensive Account Plan

#### Download Artifacts

- **Interactive Mind Map:** Click "Mind Map" in NotebookLM
- **Slide Deck:** Click "Slide Deck" in NotebookLM
- **Account Plan:** Download as Google Doc from NotebookLM

---

## Common Issues & Solutions

### Issue 1: "Authentication expired" errors

**Cause:** Using work/enterprise SSO account

**Solution:**
```bash
notebooklm logout
notebooklm login  # Use PERSONAL Gmail
```

See: `REDHAT_SSO_WORKAROUND.md`

---

### Issue 2: "Rate limited" errors (Deep Mode)

**Cause:** Google's deep research API has strict limits

**Solution:**
- ✅ Script automatically handles this (v3.0)
- ✅ Uses 1 worker, 120s delays, cooldown periods
- ⏳ Just let it run - it will retry automatically

See: `RATE_LIMIT_FIX.md`

---

### Issue 3: "No such file or directory" errors

**Cause:** Folder paths in vars.py don't exist

**Solution:**
```bash
# Verify paths exist
python -c "
import vars
for client in vars.clients:
    folder = getattr(vars, f'{client}_folder')
    print(f'{client}: {folder}')
    import os
    print(f'  Exists: {os.path.exists(folder)}')
"
```

Fix folder paths in vars.py

---

### Issue 4: Script hangs / no progress

**Cause:** Various (auth, network, API)

**Solution:**
```bash
# Check logs
tail -50 project_ape_execution.log

# Look for errors
grep -i "error\|failed\|critical" project_ape_execution.log

# Restart with resume flag
python fast.py --resume
```

---

### Issue 5: Dashboard not opening

**Cause:** Browser not launching automatically

**Solution:**
```bash
# Open manually
open project_ape_dashboard.html

# Or in browser:
file:///Users/yourname/path/to/project_ape_dashboard.html
```

---

## Advanced Configuration

### Use Deep Mode (Comprehensive Research)

**When to use:**
- High-stakes strategic accounts
- Need web citations and external research
- Can afford 2-hour runtime

**How to use:**
```bash
python deep_v3_optimized.py
```

**Important:**
- Uses 1 worker (sequential)
- ~20 minutes per client
- Includes web search and citations
- See `RATE_LIMIT_FIX.md` for tuning

---

### Environment Variable Overrides

**Customize at runtime without editing code:**

```bash
# Deep mode rate limiting
export DEEP_RATE_LIMIT_RPM=0.5
export DEEP_MAX_WORKERS=1
export DEEP_RESEARCH_BASE_DELAY=120.0

# Run deep mode
python deep_v3_optimized.py
```

**Available variables:** See `vars.example.py` bottom section

---

### Resume from Checkpoint

**If script crashes or is interrupted:**

```bash
# Resume where it left off
python fast.py --resume
```

**How it works:**
- State saved to `pipeline_state.json`
- Skips completed phases
- Continues from last checkpoint

---

### Clear State and Start Fresh

```bash
# Clear all state and start over
python fast.py --clear-state
```

---

## Next Steps

### After Successful Test Run

1. ✅ **Add more clients** - Update vars.py
2. ✅ **Try deep mode** - Run `python deep_v3_optimized.py`
3. ✅ **Customize prompts** - Edit `ask_*.txt` and `chat_*.txt` files
4. ✅ **Share notebooks** - Invite stakeholders in NotebookLM
5. ✅ **Schedule automation** - Set up cron job for overnight runs

### Recommended Workflow

**For new accounts:**
1. Add client to vars.py
2. Run fast mode first (validation)
3. Review output quality
4. Run deep mode if needed (comprehensive)
5. Share NotebookLM workspace with team

**For ongoing use:**
- Update documents in client folders
- Re-run to refresh analysis
- Quarterly updates recommended

---

## Support Resources

### Documentation

- **README.md** - Complete technical documentation
- **vars.example.py** - Configuration reference
- **REDHAT_SSO_WORKAROUND.md** - Authentication guide
- **RATE_LIMIT_FIX.md** - Deep mode troubleshooting
- **PROJECT_APE_EXECUTIVE_SUMMARY.md** - Business case and ROI

### Troubleshooting

- **Check logs:** `tail -f project_ape_execution.log`
- **Validate config:** `python -c "import vars"`
- **Test auth:** `notebooklm list`
- **View dashboard:** `open project_ape_dashboard.html`

### Getting Help

1. Check documentation in `notebooklm/` directory
2. Review logs for error messages
3. Verify configuration in vars.py
4. Check authentication status

---

## Checklist

Use this checklist for initial setup:

- [ ] Python 3.9+ installed
- [ ] Node.js 16+ installed
- [ ] NotebookLM CLI installed (`npm install -g notebooklm`)
- [ ] Virtual environment created and activated
- [ ] Python dependencies installed (`pip install -r requirements.txt`)
- [ ] Personal Gmail account ready (NOT work account)
- [ ] Authenticated with NotebookLM (`notebooklm login`)
- [ ] vars.py created (`cp vars.example.py vars.py`)
- [ ] Notification email updated in vars.py
- [ ] Client configurations added to vars.py
- [ ] Customer document folders created and populated
- [ ] Test run completed (`python fast.py`)
- [ ] Results reviewed in NotebookLM

---

## Estimated Time

- **Initial setup:** 30 minutes
- **Configuration:** 15 minutes
- **First test run (fast mode):** 20 minutes
- **Total:** ~65 minutes to first account plan

---

**Ready to start?** Follow Step 1 above!

**Questions?** See documentation or troubleshooting section.

---

*Last Updated: June 7, 2026*
