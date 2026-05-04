#!/usr/bin/env bash
# ==============================================================================
#  setup.sh — Setup script for FileRenamerAIEN
# ==============================================================================
#
#  This script checks all prerequisites for FileRenamerAIEN and sets up
#  the development environment completely. It performs the following steps:
#
#    1. Checks whether Homebrew is installed (required for macOS packages).
#    2. Checks and installs Python 3.10+ via Homebrew (if needed).
#    3. Checks and installs Tesseract OCR + English language pack + Poppler
#       (optional, but recommended for scanned PDFs).
#    4. Checks and installs Ollama (locally running AI model).
#    5. Creates a Python virtual environment (.venv) in the project folder.
#    6. Installs all Python packages from requirements.txt into the venv.
#    7. Activates the virtual environment in the current shell session.
#    8. Starts Ollama in the background (if not already running).
#
#  Confirmation is requested explicitly before each installation.
#  Already installed components are detected and skipped.
#
#  Usage:
#    chmod +x setup.sh   # make executable once
#    ./setup.sh
#
#  Author: Lars Eberhart
# ==============================================================================

# ------------------------------------------------------------------------------
# Safety options:
#   -e  Exit immediately on any error (no silent failures).
#   -u  Treat unset variables as errors.
#   -o pipefail  A failure in a pipeline counts as an overall failure.
# ------------------------------------------------------------------------------
set -euo pipefail

# ------------------------------------------------------------------------------
# Color codes for readable terminal output.
# Only set if the terminal supports colors (tput available).
# ------------------------------------------------------------------------------
if command -v tput &>/dev/null && tput colors &>/dev/null; then
    C_RESET=$(tput sgr0)
    C_BOLD=$(tput bold)
    C_GREEN=$(tput setaf 2)
    C_YELLOW=$(tput setaf 3)
    C_CYAN=$(tput setaf 6)
    C_RED=$(tput setaf 1)
else
    C_RESET="" C_BOLD="" C_GREEN="" C_YELLOW="" C_CYAN="" C_RED=""
fi

# ------------------------------------------------------------------------------
# Helper functions for formatted output.
# ------------------------------------------------------------------------------

# Print an info message (cyan).
info()    { echo "${C_CYAN}${C_BOLD}[info]${C_RESET}  $*"; }

# Print a success message (green).
ok()      { echo "${C_GREEN}${C_BOLD}[ok]${C_RESET}    $*"; }

# Print a warning (yellow) — no exit.
warn()    { echo "${C_YELLOW}${C_BOLD}[warn]${C_RESET}  $*"; }

# Print an error (red) — then exit.
error()   { echo "${C_RED}${C_BOLD}[error]${C_RESET} $*" >&2; exit 1; }

# Separator line for readability between sections.
separator() { echo; echo "${C_BOLD}──────────────────────────────────────────────${C_RESET}"; echo; }

# ------------------------------------------------------------------------------
# ask_confirm <question>
#
# Asks the user a yes/no question. Returns 0 for yes, 1 for no.
# Accepts: j / J / y / Y → yes
#          n / N / Enter  → no (default answer)
# ------------------------------------------------------------------------------
ask_confirm() {
    local prompt="$1"
    local answer
    # Write the prompt directly to the terminal (not via stdout, so pipes
    # don't swallow the text).
    printf "%s %s[y/N]%s " \
        "${C_YELLOW}${C_BOLD}[?]${C_RESET} ${prompt}" \
        "${C_BOLD}" "${C_RESET}" >/dev/tty
    read -r answer </dev/tty || answer="n"
    case "$answer" in
        [jJyY]) return 0 ;;
        *)       return 1 ;;
    esac
}

# ==============================================================================
# HEADER — Welcome and overview
# ==============================================================================
clear
echo "${C_BOLD}${C_CYAN}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║          FileRenamerAIEN — Setup Script              ║"
echo "╚══════════════════════════════════════════════════════╝"
echo "${C_RESET}"
echo "This script sets up all prerequisites for FileRenamerAIEN."
echo "Confirmation is requested before each installation."
echo

# ==============================================================================
# STEP 1: Check Homebrew (required prerequisite)
# ==============================================================================
separator
info "Step 1/6 — Checking Homebrew"
echo "Homebrew is required to install Python, Tesseract, and Ollama."
echo

if command -v brew &>/dev/null; then
    ok "Homebrew is already installed: $(brew --version | head -1)"
else
    # Homebrew is missing — without Homebrew we cannot install system packages
    # on macOS. The user must install it manually.
    warn "Homebrew is not installed."
    echo "Homebrew is the standard package manager for macOS."
    echo "Installation command (from https://brew.sh):"
    echo
    echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    echo
    if ask_confirm "Install Homebrew now?"; then
        info "Starting Homebrew installation ..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        ok "Homebrew installed successfully."
    else
        error "Homebrew is required. Setup aborted."
    fi
fi

# ==============================================================================
# STEP 2: Check and optionally install Python 3.10+
# ==============================================================================
separator
info "Step 2/8 — Checking Python 3.10+"
echo "FileRenamerAIEN requires Python 3.10 or newer."
echo

# Search for a Python binary (python3 or python) reporting at least version 3.10.
PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        # Read version number as integer: e.g. "3.11" → 311
        py_ver=$("$candidate" -c \
            "import sys; print(sys.version_info.major * 100 + sys.version_info.minor)" \
            2>/dev/null || echo "0")
        if [ "$py_ver" -ge 310 ]; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -n "$PYTHON_BIN" ]; then
    py_version=$("$PYTHON_BIN" --version 2>&1)
    ok "Python found: $py_version (${PYTHON_BIN})"
else
    warn "Python 3.10+ not found."
    echo "Homebrew can install Python 3:"
    echo "  brew install python3"
    echo
    if ask_confirm "Install Python 3 via Homebrew?"; then
        info "Installing Python 3 via Homebrew ..."
        brew install python3
        # Use the newly installed binary.
        PYTHON_BIN="python3"
        ok "Python 3 installed successfully: $($PYTHON_BIN --version)"
    else
        error "Python 3.10+ is required. Setup aborted."
    fi
fi

# ==============================================================================
# STEP 3: Tesseract OCR + English language pack + Poppler (optional)
# ==============================================================================
separator
info "Step 3/8 — Checking Tesseract OCR + English language pack + Poppler (optional)"
echo "These system tools are only needed for scanned PDFs without embedded text."
echo "Without Tesseract, such files are skipped automatically."
echo
echo "  • tesseract      — OCR engine"
echo "  • tesseract-lang — Language packs (incl. English 'eng')"
echo "  • poppler        — PDF-to-image conversion for pdf2image"
echo

# Check each component individually so only missing ones are installed.
MISSING_OCR_TOOLS=()

if ! command -v tesseract &>/dev/null; then
    MISSING_OCR_TOOLS+=("tesseract")
else
    ok "tesseract is already installed: $(tesseract --version 2>&1 | head -1)"
    # Check English language pack (tesseract --list-langs lists one per line).
    if ! tesseract --list-langs 2>/dev/null | grep -q "^eng$"; then
        warn "Tesseract language pack 'eng' (English) is missing."
        MISSING_OCR_TOOLS+=("tesseract-lang")
    else
        ok "Tesseract language pack 'eng' is present."
    fi
fi

if ! command -v pdftoppm &>/dev/null; then
    # pdftoppm is part of Poppler; its presence is sufficient as a check.
    MISSING_OCR_TOOLS+=("poppler")
else
    ok "poppler is already installed."
fi

if [ ${#MISSING_OCR_TOOLS[@]} -eq 0 ]; then
    ok "All OCR system tools are already installed."
else
    warn "The following OCR system tools are missing: ${MISSING_OCR_TOOLS[*]}"
    echo
    if ask_confirm "Install missing OCR system tools via Homebrew (recommended)?"; then
        info "Installing: ${MISSING_OCR_TOOLS[*]} ..."
        brew install "${MISSING_OCR_TOOLS[@]}"
        ok "OCR system tools installed successfully."
    else
        warn "OCR system tools skipped. Scanned PDFs cannot be processed."
    fi
fi

# ==============================================================================
# STEP 4: Check and optionally install Ollama
# ==============================================================================
separator
info "Step 4/8 — Checking Ollama"
echo "Ollama is required to run the local AI model."
echo "Default model: qwen3.5:latest"
echo

if command -v ollama &>/dev/null; then
    ok "Ollama is already installed: $(ollama --version 2>/dev/null || echo 'version unknown')"
else
    warn "Ollama is not installed."
    echo "Ollama can be installed via Homebrew:"
    echo "  brew install ollama"
    echo
    if ask_confirm "Install Ollama via Homebrew?"; then
        info "Installing Ollama ..."
        brew install ollama
        ok "Ollama installed successfully."
    else
        warn "Ollama skipped. The script cannot run without Ollama."
    fi
fi

# Download the model if Ollama was just installed or the default model is not yet present.
if command -v ollama &>/dev/null; then
    echo
    info "Checking whether the default model 'qwen3.5:latest' is already downloaded ..."
    # 'ollama list' lists all local models; grep searches for the model name.
    if ollama list 2>/dev/null | grep -q "qwen3.5"; then
        ok "Model 'qwen3.5:latest' is already present."
    else
        warn "Model 'qwen3.5:latest' has not been downloaded yet."
        echo "Downloading may take several minutes (size: ~2-5 GB)."
        echo
        if ask_confirm "Download model 'qwen3.5:latest' now?"; then
            info "Downloading model (ollama pull qwen3.5:latest) ..."
            ollama pull qwen3.5:latest
            ok "Model 'qwen3.5:latest' downloaded successfully."
        else
            warn "Model not downloaded. Run 'ollama pull qwen3.5:latest' before first use."
        fi
    fi
fi

# ==============================================================================
# STEP 5: Create Python virtual environment
# ==============================================================================
separator
info "Step 5/8 — Setting up Python virtual environment (.venv)"
echo "A virtual environment isolates this project's Python packages"
echo "from the system Python and prevents conflicts with other projects."
echo

VENV_DIR="$(pwd)/.venv"

if [ -d "$VENV_DIR" ]; then
    # Already present — check if it is functional.
    ok ".venv directory already exists: $VENV_DIR"
    if ask_confirm "Recreate .venv (deletes existing packages)?"; then
        info "Removing existing .venv ..."
        # Deactivate the active venv so no files are locked by the running
        # interpreter. The 'deactivate' function only exists when a venv is
        # active — hence the 'command -v' check.
        if command -v deactivate &>/dev/null; then
            deactivate 2>/dev/null || true
        fi
        # rm -rf occasionally fails on macOS with extended attributes or
        # locked files. Python's shutil.rmtree is more robust and reliably
        # works around these restrictions.
        if ! rm -rf "$VENV_DIR" 2>/dev/null; then
            warn "rm -rf failed — using shutil.rmtree as fallback ..."
            "$PYTHON_BIN" -c "import shutil; shutil.rmtree('${VENV_DIR}')"
        fi
        info "Creating new virtual environment ..."
        "$PYTHON_BIN" -m venv "$VENV_DIR"
        ok "Virtual environment recreated."
    else
        info "Keeping existing .venv."
    fi
else
    info "Creating virtual environment in $VENV_DIR ..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    ok "Virtual environment created successfully."
fi

# Path to the venv Python interpreter (not sourced, since we stay in the
# same subshell context).
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# ==============================================================================
# STEP 6: Install Python packages from requirements.txt
# ==============================================================================
separator
info "Step 6/8 — Installing Python packages (requirements.txt)"
echo "The following packages will be installed into the virtual environment:"
echo
# Filter and display packages from requirements.txt (excluding comments and blank lines).
grep -v '^\s*#' requirements.txt | grep -v '^\s*$' | sed 's/^/  • /'
echo

if ask_confirm "Install packages into .venv now?"; then
    info "Upgrading pip to the latest version ..."
    "$VENV_PYTHON" -m pip install --upgrade pip

    info "Installing packages from requirements.txt ..."
    "$VENV_PIP" install -r requirements.txt
    ok "All Python packages installed successfully."
else
    warn "Package installation skipped. The script will not work without Python packages."
    warn "To install manually: source .venv/bin/activate && pip install -r requirements.txt"
fi

# ==============================================================================
# STEP 7: Activate the virtual environment in the current shell
# ==============================================================================
separator
info "Step 7/8 — Activating virtual environment"
echo "The venv will be activated in the current shell session."
echo "Note: When the script is started as './setup.sh' (subshell), the"
echo "activation only applies within this script. To keep it active in your shell,"
echo "run 'source .venv/bin/activate' afterwards."
echo

if ask_confirm "Activate virtual environment now (source .venv/bin/activate)?"; then
    # shellcheck source=/dev/null
    # Activate with 'source' (dot operator) so environment variables
    # (PATH, VIRTUAL_ENV, etc.) are exported into the current shell.
    # In a subshell (./setup.sh) this only applies for the script's lifetime;
    # when sourced (source ./setup.sh) it remains active permanently.
    source "$VENV_DIR/bin/activate"
    ok "Virtual environment activated: $VIRTUAL_ENV"
else
    warn "Activation skipped. Activate manually before running the script:"
    warn "  source .venv/bin/activate"
fi

# ==============================================================================
# STEP 8: Start Ollama in the background
# ==============================================================================
separator
info "Step 8/8 — Starting Ollama"
echo "Ollama must run as a background service so the language model"
echo "can accept requests."
echo

# Check whether Ollama is already running: 'ollama list' fails if the
# service is not running. Alternative: check port 11434 for open connections.
OLLAMA_RUNNING=false
if command -v ollama &>/dev/null; then
    if ollama list &>/dev/null 2>&1; then
        OLLAMA_RUNNING=true
    fi
fi

if $OLLAMA_RUNNING; then
    ok "Ollama is already running."
else
    if ! command -v ollama &>/dev/null; then
        warn "Ollama is not installed — step skipped."
    else
        warn "Ollama is not running."
        echo
        if ask_confirm "Start Ollama in the background now (ollama serve)?"; then
            info "Starting Ollama in the background ..."
            # 'nohup ... &' starts Ollama detached from this shell
            # so it keeps running after the script ends.
            # Stdout/Stderr are redirected to ~/.ollama/setup-serve.log
            # to avoid blocking the terminal.
            nohup ollama serve >> ~/.ollama/setup-serve.log 2>&1 &
            OLLAMA_PID=$!
            info "Waiting for Ollama to start (PID $OLLAMA_PID) ..."
            # Wait up to 10 seconds for the API port to respond.
            for i in $(seq 1 10); do
                if ollama list &>/dev/null 2>&1; then
                    ok "Ollama has started and is ready (PID $OLLAMA_PID)."
                    break
                fi
                sleep 1
                if [ "$i" -eq 10 ]; then
                    warn "Ollama is not responding yet — still running in the background."
                    warn "Log: ~/.ollama/setup-serve.log"
                fi
            done
        else
            warn "Ollama will not be started. Start it manually before first use:"
            warn "  ollama serve"
        fi
    fi
fi

# ==============================================================================
# CONCLUSION — Summary and next steps
# ==============================================================================
separator
echo "${C_GREEN}${C_BOLD}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║              Setup complete!                         ║"
echo "╚══════════════════════════════════════════════════════╝"
echo "${C_RESET}"
echo "Next steps:"
echo

# Check whether the venv is already active ($VIRTUAL_ENV is set by 'source activate').
# If not, offer activation again — e.g. if step 7 was skipped or the script
# was restarted.
if [ -z "${VIRTUAL_ENV:-}" ]; then
    if ask_confirm "Activate virtual environment in this shell now (source .venv/bin/activate)?"; then
        # shellcheck source=/dev/null
        source "$VENV_DIR/bin/activate"
        ok "Virtual environment activated: $VIRTUAL_ENV"
    else
        echo
        echo "  Activate virtual environment manually:"
        echo "     ${C_BOLD}source .venv/bin/activate${C_RESET}"
    fi
else
    ok "Virtual environment is already active: $VIRTUAL_ENV"
fi
echo
echo "  Run the script (preview without renaming):"
echo "     ${C_BOLD}python filerenameraien.py ~/Documents/Invoices --dry-run${C_RESET}"
echo
echo "  Perform actual renaming:"
echo "     ${C_BOLD}python filerenameraien.py ~/Documents/Invoices${C_RESET}"
echo
