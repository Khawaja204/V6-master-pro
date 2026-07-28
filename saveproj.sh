#!/bin/bash
echo "=== V6 Master Pro Project Export ===" > project.txt
echo "Generated: $(date)" >> project.txt
echo "========================================" >> project.txt
echo "" >> project.txt
for f in main.py logic.py config.json index.html focus.html; do
  if [ -f "$f" ]; then
    echo "" >> project.txt
    echo "========================================" >> project.txt
    echo "FILE: ./$f" >> project.txt
    echo "========================================" >> project.txt
    cat "$f" >> project.txt
  fi
done
echo "" >> project.txt
echo "=== END EXPORT ===" >> project.txt
echo "Project exported to project.txt"
