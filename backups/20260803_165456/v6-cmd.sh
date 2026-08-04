#!/usr/bin/env bash
# V6 Master Pro — one-word command shortcuts

aj() {
    less +G /home/runner/workspace/AGENT_CHAT_LOG.md 2>/dev/null || cat /home/runner/workspace/AGENT_CHAT_LOG.md
}

chat-log() { aj; }

backlog() {
    less /home/runner/workspace/V6_BACKLOG.md 2>/dev/null || cat /home/runner/workspace/V6_BACKLOG.md
}

deploy() {
    echo "Deploying V6 Master Pro..."
    pkill -f "python3 main.py" 2>/dev/null && echo "   killed old process" || echo "   no old process running"
    sleep 1
    nohup python3 /home/runner/workspace/main.py > /home/runner/workspace/v6_server.log 2>&1 &
    echo "   started PID $!"
}

stop() {
    echo "Stopping V6 Master Pro..."
    if pkill -f "python3 main.py"; then echo "   process killed"; else echo "   no running process found"; fi
}

restart() { deploy; }

status() {
    echo "V6 Master Pro status:"
    PIDS=$(pgrep -f "main.py")
    if [ -n "$PIDS" ]; then echo "   RUNNING — PID(s): $PIDS"; else echo "   NOT RUNNING"; fi
    LOG=/home/runner/workspace/v6_server.log
    if [ -f "$LOG" ]; then echo ""; echo "   Last 5 log lines:"; tail -5 "$LOG" | sed 's/^/      /'; else echo "   (no log file yet)"; fi
}

logs() {
    tail -30 /home/runner/workspace/v6_server.log 2>/dev/null || echo "No log file found at v6_server.log"
}

v8() {
    echo "Exporting V6 upgrade modules..."
    bash /home/runner/workspace/v6-export.sh
}

save() {
    echo "Saving project..."
    bash /home/runner/workspace/saveproj.sh
}

push() {
    echo "Saving and pushing to GitHub..."
    bash /home/runner/workspace/saveproj.sh
    cd /home/runner/workspace
    git add .
    git commit -m "v6 update"
    git push
}

full() {
    echo "Running full sequence: save -> deploy -> push"
    save
    deploy
    push
}

backup() {
    TS=$(date +%Y%m%d_%H%M%S)
    BAK_DIR="/home/runner/workspace/backups/$TS"
    mkdir -p "$BAK_DIR"
    cp /home/runner/workspace/*.py "$BAK_DIR/" 2>/dev/null
    cp /home/runner/workspace/*.json "$BAK_DIR/" 2>/dev/null
    cp /home/runner/workspace/*.sh "$BAK_DIR/" 2>/dev/null
    cp /home/runner/workspace/*.db "$BAK_DIR/" 2>/dev/null
    echo "Backup created: $BAK_DIR"
}

update() {
    echo "Pulling latest code..."
    cd /home/runner/workspace
    git pull
    echo "Installing dependencies..."
    pip install -q -r requirements.txt
    echo "Update complete. Run 'restart' to apply."
}

db-migrate() {
    echo "Running JSON -> SQLite migration..."
    cd /home/runner/workspace
    python3 migrate_to_sqlite.py
}

db-backup() {
    TS=$(date +%Y%m%d_%H%M%S)
    BAK="/home/runner/workspace/backups/v6_master_$TS.db"
    mkdir -p /home/runner/workspace/backups
    if [ -f /home/runner/workspace/v6_master.db ]; then
        cp /home/runner/workspace/v6_master.db "$BAK"
        echo "DB backed up: $BAK"
    else
        echo "No v6_master.db found. Run 'db-migrate' first."
    fi
}

db-status() {
    echo "V6 Database Status"
    if [ -f /home/runner/workspace/v6_master.db ]; then
        python3 -c "
from v6_database import db_status
st = db_status()
print(f'  DB: {st[\"db_path\"]}')
print(f'  Size: {st[\"db_size_bytes\"]:,} bytes ({st[\"db_size_bytes\"]/1024:.1f} KB)')
print()
print('  Table Rows:')
for t, c in st['tables'].items():
    print(f'    • {t:<25} {c:>4} rows')
"
    else
        echo "  v6_master.db not found."
        echo "     Run: db-migrate   (to create from JSON files)"
    fi
}

echo "V6 commands loaded: aj | chat-log | backlog | sp | v8 | deploy | stop | restart | status | logs | save | push | full | backup | update | db-migrate | db-backup | db-status"
