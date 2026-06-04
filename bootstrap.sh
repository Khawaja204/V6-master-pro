#!/usr/bin/env bash

echo "[bootstrap] Installing/upgrading dependencies..."
python3 -m pip install -r requirements.txt --upgrade -q

echo "[bootstrap] Clearing port 8080..."
fuser -k 8080/tcp 2>/dev/null || true

echo "[bootstrap] Auto-restart loop active — V6 Elite Terminal will restart on crash."
while true; do
    python3 main.py
    echo "[bootstrap] main.py exited. Restarting in 1 second..."
    sleep 1
done
