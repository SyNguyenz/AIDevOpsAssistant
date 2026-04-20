#!/usr/bin/env bash
# setup.sh — First-time setup for AI DevOps Assistant
#
# Usage:
#   bash setup.sh
#
# What this does:
#   1. Create Python virtual environment (venv/)
#   2. Clone Qodo PR-Agent source → pr_agent_src/
#   3. Install PR-Agent from source (pip 0.3.x has a bug, use source)
#   4. Install project dependencies
#   5. Create .env from .env.example
#   6. Generate dummy test repo for local testing

set -e

PYTHON=${PYTHON:-python3}

# --- 1. Virtual environment ---
if [ ! -d "venv" ]; then
    echo "[1/6] Creating virtual environment..."
    $PYTHON -m venv venv
else
    echo "[1/6] venv already exists, skipping."
fi

if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || -f "venv/Scripts/activate" ]]; then
    PIP="venv/Scripts/pip.exe"
    PYTHON_VENV="venv/Scripts/python.exe"
else
    PIP="venv/bin/pip"
    PYTHON_VENV="venv/bin/python"
fi

# --- 2. Clone PR-Agent source ---
if [ ! -d "pr_agent_src" ]; then
    echo "[2/6] Cloning Qodo PR-Agent source..."
    git clone --depth=1 https://github.com/qodo-ai/pr-agent.git pr_agent_src
else
    echo "[2/6] pr_agent_src already exists, skipping clone."
fi

# --- 3. Install PR-Agent from source ---
echo "[3/6] Installing PR-Agent from source (editable)..."
$PIP install -e pr_agent_src/ --quiet

# --- 4. Install project dependencies ---
echo "[4/6] Installing project dependencies..."
$PIP install -r requirements.txt --quiet

# --- 5. Environment file ---
if [ ! -f ".env" ]; then
    echo "[5/6] Creating .env from .env.example..."
    cp .env.example .env
    echo "      --> Fill in your API keys in .env before running anything."
else
    echo "[5/6] .env already exists, skipping."
fi

# --- 6. Dummy test repo ---
if [ ! -d "dummy_repo" ]; then
    echo "[6/6] Generating dummy test repo..."
    $PYTHON_VENV scripts/create_dummy_repo.py
else
    echo "[6/6] dummy_repo already exists, skipping."
fi

echo ""
echo "Setup complete."
echo ""
echo "Next steps:"
echo "  1. Edit .env and fill in: GEMINI_API_KEY, GITHUB_USER_TOKEN"
echo "  2. Test KG pipeline: $PYTHON_VENV scripts/build_and_test_kg.py"
echo "  3. Test PR review:   $PYTHON_VENV run_review.py <PR_URL>"
