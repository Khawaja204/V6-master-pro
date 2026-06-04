#!/usr/bin/env bash

# Ensure this script is executable
chmod +x "$0"

# ── Wire up .pythonlibs so the Nix Python finds installed packages ─────────────
PYLIBS="/home/runner/workspace/.pythonlibs/lib/python3.11/site-packages"
PIP_BIN="/home/runner/workspace/.pythonlibs/bin/pip"
export PYTHONPATH="${PYLIBS}:${PYTHONPATH}"
export PATH="/home/runner/workspace/.pythonlibs/bin:${PATH}"

LOG_FILE="system.log"
MAX_LOG_SIZE=5242880  # 5 MB in bytes

rotate_log() {
    if [ -f "$LOG_FILE" ]; then
        local size
        size=$(stat -c%s "$LOG_FILE" 2>/dev/null || stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)
        if [ "$size" -gt "$MAX_LOG_SIZE" ]; then
            > "$LOG_FILE"
            echo "[bootstrap] system.log exceeded 5 MB — truncated at $(date '+%Y-%m-%d %H:%M:%S')."
        fi
    fi
}

echo "[bootstrap] ============================================"
echo "[bootstrap] V6 Elite Terminal — Production Boot"
echo "[bootstrap] Started at: $(date '+%Y-%m-%d %H:%M:%S')"
echo "[bootstrap] PYTHONPATH=${PYTHONPATH}"
echo "[bootstrap] ============================================"

while true; do
    rotate_log
    python3 main.py
    echo "[bootstrap] main.py exited at $(date '+%Y-%m-%d %H:%M:%S') — restarting in 1 second..."
    sleep 1
done
