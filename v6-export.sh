#!/bin/bash
OUTPUT="v6_modules_export.txt"
TIMESTAMP=$(date -u +"%a %b %d %I:%M:%S %p UTC %Y")
FILES=("v6_database.py" "v6_crypto.py" "v6_oco.py" "v6_websocket.py" "v6_partial_tp.py" "v6_multitimeframe.py")

{
  echo "=== V6 Master Pro — Upgrade Modules Export ==="
  echo "Generated: $TIMESTAMP"
  echo "========================================"
  for f in "${FILES[@]}"; do
    echo ""
    echo "========================================"
    echo "FILE: ./$f"
    echo "========================================"
    if [ -f "$f" ]; then
      cat "$f"
    else
      echo "[MISSING — module not yet created]"
    fi
  done
  echo ""
  echo "========================================"
  echo "END OF EXPORT"
  echo "========================================"
} > "$OUTPUT"

echo "✅ V6 modules exported to $OUTPUT ($(wc -l < "$OUTPUT") lines)"
