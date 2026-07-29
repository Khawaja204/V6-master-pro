#!/bin/bash
OUTPUT="project.txt"
TIMESTAMP=$(date -u +"%a %b %d %I:%M:%S %p UTC %Y")

FILES=(
  "main.py" "logic.py" "config.json" "scoring_engine.py"
  "requirements.txt" "saveproj.sh"
  "V6_Master_Pro_UI/index.html"
  "V6_Master_Pro_UI/script.js"
  "V6_Master_Pro_UI/style.css"
  "focus.html" "index.html"
)

{
  echo "=== V6 Master Pro Project Export ==="
  echo "Generated: $TIMESTAMP"
  echo "========================================"
  for f in "${FILES[@]}"; do
    if [ -f "$f" ]; then
      echo ""; echo "========================================"; echo "FILE: ./$f"; echo "========================================"; cat "$f"
    else
      echo ""; echo "========================================"; echo "FILE: ./$f [MISSING]"; echo "========================================"
    fi
  done
  echo ""; echo "========================================"; echo "END OF EXPORT"; echo "========================================"
} > "$OUTPUT"

echo "✅ Exported to $OUTPUT ($(wc -l < "$OUTPUT") lines)"
