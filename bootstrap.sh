#!/usr/bin/env bash
set -e

echo "[bootstrap] Installing/upgrading dependencies..."
pip install -r requirements.txt --upgrade -q

echo "[bootstrap] Clearing port 8080..."
fuser -k 8080/tcp 2>/dev/null || true

echo "[bootstrap] Starting V6 Elite Terminal..."
python3 main.py
