#!/usr/bin/env bash

set -e

echo "==================================================="
echo "     P2P File Sharing System - Auto Setup"
echo "==================================================="

echo "[1/4] Checking for 'uv' package manager..."

if command -v uv >/dev/null 2>&1; then
    echo "Found 'uv'."
else
    echo "'uv' is not found. Installing via pip..."
    
    if command -v pip >/dev/null 2>&1; then
        pip install uv
    else
        python3 -m pip install uv
    fi

    if ! command -v uv >/dev/null 2>&1; then
        echo
        echo "[ERROR] Failed to install 'uv'. Ensure Python and pip are installed."
        exit 1
    fi

    echo "'uv' installed successfully."
fi

echo
echo "[2/4] Checking Virtual Environment..."

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment '.venv'..."
    uv venv
else
    echo "Virtual environment found."
fi

echo
echo "[3/4] Installing dependencies into .venv..."

uv pip install -r requirements.txt

echo
echo "[4/4] Launching Application..."
echo

source .venv/bin/activate
python launcher.py

echo
echo "Application finished."