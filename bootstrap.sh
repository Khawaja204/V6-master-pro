#!/usr/bin/env bash

# Install dependencies if pip is available (dev env); Nix packages cover production
python3 -m pip install -r requirements.txt -q 2>/dev/null || true

echo "[bootstrap] Starting V6 Elite Terminal — auto-restart on crash enabled."
while true; do
    python3 main.py
    echo "[bootstrap] main.py exited — restarting in 2 seconds..."
    sleep 2
done
