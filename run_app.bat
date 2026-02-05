@echo off
setlocal
title P2P Network Launcher

echo ===================================================
echo      P2P File Sharing System - Auto Setup
echo ===================================================

echo [1/4] Checking for 'uv' package manager...
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo 'uv' is not found. Installing via pip...
    pip install uv
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Failed to install 'uv'. Please ensure Python and pip are in your PATH.
        pause
        exit /b
    )
    echo 'uv' installed successfully.
) else (
    echo Found 'uv'.
)

echo.
echo [2/4] Checking Virtual Environment...
if not exist ".venv" (
    echo Creating virtual environment '.venv'...
    uv venv
) else (
    echo Virtual environment found.
)

echo.
echo [3/4] Installing dependencies into .venv...
:: Install requirements into the virtual environment
uv pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b
)

echo.
echo [4/4] Launching Application...
echo.
:: Run python from the venv directly
.venv\Scripts\python.exe launcher.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application crashed or verified closed.
    pause
)
