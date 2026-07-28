#!/bin/bash

OUTPUT="project.txt"
ZIPFILE="project.zip"
MAX_SIZE_KB=500

echo "🔍 Scanning project files..."

# Clear output
> "$OUTPUT"

# Header
cat >> "$OUTPUT" << 'HEADER'
================================================================================
                    V6 MASTER PRO - PROJECT EXPORT
================================================================================
HEADER

echo "" >> "$OUTPUT"
echo "📁 PROJECT STRUCTURE OVERVIEW" >> "$OUTPUT"
echo "--------------------------------------------------------------------------------" >> "$OUTPUT"

# Temp file for file list
TMPFILE=$(mktemp)

# Find all code/config files, skip junk folders
find . \
    -path "./.git" -prune -o \
    -path "./.agents" -prune -o \
    -path "./.pythonlibs" -prune -o \
    -path "./.upm" -prune -o \
    -path "./node_modules" -prune -o \
    -path "./attached_assets" -prune -o \
    -path "./__pycache__" -prune -o \
    -path "./.venv" -prune -o \
    -path "./venv" -prune -o \
    -type f \( \
        -iname "*.py" -o \
        -iname "*.js" -o \
        -iname "*.css" -o \
        -iname "*.html" -o \
        -iname "*.htm" -o \
        -iname "*.json" -o \
        -iname "*.txt" -o \
        -iname "*.sh" -o \
        -iname "*.md" -o \
        -iname "*.xml" -o \
        -iname "*.yaml" -o \
        -iname "*.yml" -o \
        -iname "*.toml" -o \
        -iname "*.ini" -o \
        -iname "*.cfg" -o \
        -iname "*.sql" \
    \) -print 2>/dev/null | \
while IFS= read -r file; do
    clean_file="${file#./}"
    
    # Skip excluded patterns
    case "$clean_file" in
        .env*|*.env*|*.pyc|*.pyo|*.log|*.sqlite|*.db|*.zip|*.tar|*.gz|*.rar|*.7z|*.jpg|*.jpeg|*.png|*.gif|*.webp|*.mp4|*.mp3|*.woff|*.woff2|*.ttf|*.eot|package-lock.json|project.txt|saveproj.sh)
            continue
            ;;
    esac
    
    echo "$clean_file"
done | sort > "$TMPFILE"

# Add file list to output
cat "$TMPFILE" >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "================================================================================" >> "$OUTPUT"
echo "                           FILE CONTENTS START" >> "$OUTPUT"
echo "================================================================================" >> "$OUTPUT"
echo "" >> "$OUTPUT"

# Process each file
TOTAL_FILES=0
SKIPPED=0

while IFS= read -r clean_file; do
    file="./$clean_file"
    
    [ ! -f "$file" ] && continue
    
    SIZE_KB=$(du -k "$file" 2>/dev/null | cut -f1)
    
    # Skip large files
    if [ "$SIZE_KB" -gt "$MAX_SIZE_KB" ]; then
        echo "" >> "$OUTPUT"
        echo "⚠️  SKIPPED (too large: ${SIZE_KB}KB): $clean_file" >> "$OUTPUT"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi
    
    # Write file header
    echo "" >> "$OUTPUT"
    echo "════════════════════════════════════════════════════════════════════════════════" >> "$OUTPUT"
    echo "📄 FILE: $clean_file" >> "$OUTPUT"
    echo "📏 SIZE: ${SIZE_KB}KB" >> "$OUTPUT"
    echo "════════════════════════════════════════════════════════════════════════════════" >> "$OUTPUT"
    echo "" >> "$OUTPUT"
    
    cat "$file" >> "$OUTPUT" 2>/dev/null
    echo "" >> "$OUTPUT"
    
    TOTAL_FILES=$((TOTAL_FILES + 1))
    
done < "$TMPFILE"

rm -f "$TMPFILE"

# Footer
cat >> "$OUTPUT" << 'FOOTER'

================================================================================
                           FILE CONTENTS END
================================================================================
FOOTER

# ZIP generation
echo ""
echo "📦 Creating zip file..."
rm -f "$ZIPFILE"
zip -q "$ZIPFILE" "$OUTPUT"

TXT_SIZE=$(du -h "$OUTPUT" 2>/dev/null | cut -f1)
ZIP_SIZE=$(du -h "$ZIPFILE" 2>/dev/null | cut -f1)

echo ""
echo "========================================"
echo "✅ SMART EXPORT + ZIP COMPLETE!"
echo "========================================"
echo "📄 $OUTPUT  →  $TXT_SIZE"
echo "📦 $ZIPFILE  →  $ZIP_SIZE"
echo "📊 Files exported: $TOTAL_FILES"
echo "🚫 Files skipped (too large): $SKIPPED"
echo ""
echo "💡 Upload '$ZIPFILE' to Kimi Chat"
echo "========================================"
