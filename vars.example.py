# ==============================================================================
# PROJECT APE - ACCOUNT PLANNING ENGINE
# Example Configuration File
# ==============================================================================
#
# INSTRUCTIONS:
# 1. Copy this file to vars.py:
#    cp vars.example.py vars.py
#
# 2. Update the configuration values below with your actual clients
#
# 3. Update notification_email with your email address
#
# 4. For each client, provide:
#    - Client token (lowercase, underscores)
#    - Display name
#    - Industry (must match INDUSTRY_FOCUS_AREAS keys)
#    - Folder path (containing customer PDFs/CSVs)
#
# ==============================================================================

# ==============================================================================
# GLOBAL ORCHESTRATION CONFIGURATION
# ==============================================================================

# Persona/Role for all prompts (used as $persona in prompt templates)
# Examples: "senior account solutions architect", "account executive", "solutions consultant"
persona = "senior account solutions architect"

# Vendor/Company name for all prompts (used as $vendor in prompt templates)
# This makes prompts reusable for any company - not just Red Hat
# Examples: "Red Hat", "Acme Solutions", "Global Tech Corp"
vendor = "Red Hat"

# Email address for completion notifications
# UPDATE THIS with your actual email address
notification_email = "your.email@company.com"

# List of client tokens to process
# Each token must have corresponding configuration below (name, industry, folder)
clients = [
    "acme_corp",
    "globex_industries",
    "initech",
]

# --- Global Pipeline File Names (Resolved relative to PROJECT_ROOT) ---
LOG_FILE_NAME = "project_ape_execution.log"
DASHBOARD_NAME = "project_ape_dashboard.html"

# ==============================================================================
# EXECUTION MODES
# ==============================================================================

# Research Mode: "fast" or "deep"
# - fast: Uses fast-mode research, higher concurrency (8 workers)
# - deep: Uses deep research with web citations, lower concurrency (1 worker)
research_mode = "fast"

# Worker Thread Limits
# Fast mode: Higher concurrency for speed
# Deep mode: Sequential execution to respect Google API rate limits
FAST_MODE_MAX_WORKERS = 8
DEEP_MODE_MAX_WORKERS = 1  # Keep at 1 for deep mode

# ==============================================================================
# TIMING CONFIGURATION (seconds)
# ==============================================================================

TIMINGS = {
    # Deep research mode cooldown (after each deep research call)
    'deep_research_cooldown': (45.0, 75.0),  # Random range for jitter

    # Post-research delay (after adding research sources)
    'post_research_delay': 15.0,

    # Source addition delay (between adding sources)
    'source_add_delay': (1.0, 3.0),

    # General chat prompt delay
    'chat_prompt_delay': (3.0, 6.0),

    # Auth refresh minimum interval
    'auth_refresh_interval': 120.0,
}

# ==============================================================================
# RETRY CONFIGURATION
# ==============================================================================

RETRY_CONFIG = {
    'max_attempts': 3,
    'base_delay': 30.0,
    'command_timeout': 300.0,

    # Deep research specific (more aggressive)
    'deep_research_max_attempts': 5,
    'deep_research_base_delay': 120.0,  # 2 minutes for deep research
    'deep_research_timeout': 480.0,
}

# ==============================================================================
# VALIDATION SETTINGS
# ==============================================================================

# Required configuration attributes per client
REQUIRED_CLIENT_ATTRS = ['name', 'industry', 'folder']

# Enable startup validation
VALIDATE_CONFIG_ON_STARTUP = True

# Enable prompt output validation
VALIDATE_PROMPT_OUTPUTS = False  # Set to True when prompt_validation.py is implemented

# ==============================================================================
# INDUSTRY-SPECIFIC FOCUS AREAS
# ==============================================================================
#
# Define strategic focus areas for each industry vertical.
# These are automatically injected into prompts to ensure industry-relevant analysis.
#
# When adding a new client, use one of these industry keys or add your own.
#

INDUSTRY_FOCUS_AREAS = {
    "pharmaceuticals and healthcare": [
        "FDA/EMA regulatory compliance",
        "Clinical trial digitization",
        "R&D acceleration and drug discovery",
        "Supply chain traceability (serialization)",
        "Patient data privacy and security",
        "Manufacturing automation and quality control"
    ],
    "manufacturing": [
        "Smart factory and Industry 4.0",
        "Predictive maintenance",
        "Supply chain resilience",
        "Product lifecycle management (PLM)",
        "Quality assurance automation",
        "IoT and edge computing"
    ],
    "financial services": [
        "Real-time transaction processing",
        "Fraud detection and prevention",
        "Regulatory compliance (RegTech)",
        "Customer data privacy and security",
        "Digital banking and payments",
        "AI-driven investment strategies"
    ],
    "retail and consumer goods": [
        "Omnichannel customer experience",
        "Inventory optimization",
        "Demand forecasting and planning",
        "Supply chain visibility",
        "Personalization and customer insights",
        "Sustainability initiatives"
    ],
    "technology and software": [
        "Cloud-native application development",
        "DevOps and CI/CD automation",
        "Container orchestration (Kubernetes/OpenShift)",
        "Microservices architecture",
        "API management and integration",
        "Security and compliance automation"
    ],
    "telecommunications": [
        "5G network infrastructure",
        "Network function virtualization (NFV)",
        "Edge computing and IoT",
        "Customer experience management",
        "Revenue assurance and fraud management",
        "Network automation and orchestration"
    ],
    "energy and utilities": [
        "Smart grid and renewable energy integration",
        "Predictive maintenance for infrastructure",
        "Regulatory compliance and reporting",
        "Customer engagement and demand response",
        "Asset management and optimization",
        "Cybersecurity for critical infrastructure"
    ],
    "transportation and logistics": [
        "Fleet management and optimization",
        "Real-time tracking and visibility",
        "Route optimization and planning",
        "Warehouse automation",
        "Last-mile delivery innovation",
        "Sustainability and carbon tracking"
    ],
}

# ==============================================================================
# CLIENT-SPECIFIC WORKSPACE CONFIGURATIONS
# ==============================================================================
#
# For each client token in the 'clients' list above, define three attributes:
#
# 1. {client_token}_name: Display name for the client
# 2. {client_token}_industry: Industry vertical (must match INDUSTRY_FOCUS_AREAS keys)
# 3. {client_token}_folder: Absolute path to folder containing customer documents
#
# EXAMPLE CLIENT CONFIGURATIONS:
# Replace these with your actual clients
# ==============================================================================

# --- Acme Corporation Configuration ---
acme_corp_name = "Acme Corporation"
acme_corp_industry = "manufacturing"
acme_corp_folder = "/path/to/customer/documents/Acme_Corp/"

# --- Globex Industries Configuration ---
globex_industries_name = "Globex Industries"
globex_industries_industry = "pharmaceuticals and healthcare"
globex_industries_folder = "/path/to/customer/documents/Globex/"

# --- Initech Configuration ---
initech_name = "Initech"
initech_industry = "financial services"
initech_folder = "/path/to/customer/documents/Initech/"

# ==============================================================================
# ADDING NEW CLIENTS
# ==============================================================================
#
# To add a new client:
#
# 1. Choose a client token (lowercase, underscores only)
#    Example: "wayne_enterprises"
#
# 2. Add the token to the clients list above:
#    clients = ["acme_corp", "globex_industries", "wayne_enterprises"]
#
# 3. Define the three required attributes:
#    wayne_enterprises_name = "Wayne Enterprises"
#    wayne_enterprises_industry = "technology and software"
#    wayne_enterprises_folder = "/path/to/documents/Wayne/"
#
# 4. Ensure the folder contains customer documents (PDFs, CSVs)
#
# 5. (Optional) If the industry doesn't exist, add it to INDUSTRY_FOCUS_AREAS
#
# ==============================================================================

# ==============================================================================
# ENVIRONMENT VARIABLE OVERRIDES (ADVANCED)
# ==============================================================================
#
# Advanced users can override configuration at runtime using environment variables:
#
# Deep Mode Rate Limiting:
#   export DEEP_RATE_LIMIT_RPM=0.5        # Requests per minute (default: 0.5)
#   export DEEP_RATE_LIMIT_BURST=1        # Burst tokens (default: 1)
#   export DEEP_MAX_WORKERS=1             # Worker threads (default: 1)
#
# Deep Mode Delays:
#   export DEEP_RESEARCH_BASE_DELAY=120.0      # Base retry delay (default: 120s)
#   export DEEP_RESEARCH_COOLDOWN_MIN=90.0     # Min cooldown (default: 90s)
#   export DEEP_RESEARCH_COOLDOWN_MAX=150.0    # Max cooldown (default: 150s)
#
# Auth Refresh:
#   export DEEP_AUTH_REFRESH_INTERVAL=240      # Auth refresh interval (default: 240s)
#
# ==============================================================================
