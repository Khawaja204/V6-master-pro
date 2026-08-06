#!/bin/bash
# V6 Master Pro — Command Toolkit
# Usage: source ~/workspace/v6-cmd.sh

WORKSPACE="$HOME/workspace"
cd "$WORKSPACE" 2>/dev/null || cd "$HOME" 2>/dev/null

echo "V6 commands loaded: aj | chat-log | back-log | sp | v8 | deploy | stop | restart | status | logs | save | push | full | backup | update | db-migrate | db-backup | db-status"

# ── Agent & Logs ──
alias aj='bash ~/workspace/agent_log.sh'
alias chat-log='bash ~/workspace/agent_log.sh tail 50'
alias back-log='cat ~/workspace/agent_work_log.txt 2>/dev/null || echo "No log yet"'

# ── Project Export ──
alias sp='bash ~/workspace/saveproj.sh'

# ── V6 Modules Export ──
alias v8='bash ~/workspace/v6-export.sh'

# ── Process Control ──
stop() {
    pkill -f "python3 main.py" 2>/dev/null && echo "✅ V6 stopped" || echo "ℹ️ Not running"
}
restart() {
    stop
    sleep 2
    nohup python3 main.py > v6.out 2>&1 &
    echo "🚀 V6 restarted on port ${PORT:-8080}"
}
status() {
    pgrep -f "python3 main.py" > /dev/null && echo "🟢 V6 is RUNNING (PID: $(pgrep -f 'python3 main.py'))" || echo "🔴 V6 is STOPPED"
}
logs() {
    tail -f ~/workspace/v6.out 2>/dev/null || tail -f ~/workspace/error.log 2>/dev/null || echo "No log file found"
}

# ── Git / Deploy ──
save() { bash ~/workspace/saveproj.sh; }
push() { git add . && git commit -m "V6 update $(date +%H:%M)" && git push; }
full() { save && push; }
deploy() { push && echo "🚀 Triggering Render deploy..."; }
update() { git pull origin main && echo "✅ Updated"; }

# ── Backup ──
backup() {
    BACKUP="backup_$(date +%Y%m%d_%H%M).tar.gz"
    tar -czf "$BACKUP" main.py logic.py config.json requirements.txt *.json *.log V6_Master_Pro_UI/ 2>/dev/null
    echo "✅ Backup: $BACKUP ($(du -h "$BACKUP" | cut -f1))"
}

# ── Database (SQLite) ──
db-migrate() {
    if [ -f "v6_database.py" ]; then
        python3 -c "from v6_database import init_db; init_db()" && echo "✅ DB migrated" || echo "❌ Migration failed"
    else
        echo "❌ v6_database.py not found"
    fi
}
db-backup() {
    if [ -f "v6_master_pro.db" ]; then
        cp v6_master_pro.db "v6_master_pro_backup_$(date +%Y%m%d_%H%M).db"
        echo "✅ DB backed up"
    else
        echo "❌ No DB file found"
    fi
}
db-status() {
    if [ -f "v6_master_pro.db" ]; then
        ls -lh v6_master_pro.db
        sqlite3 v6_master_pro.db ".tables" 2>/dev/null || echo "sqlite3 CLI not installed — file exists but can't inspect"
    else
        echo "❌ No DB file found"
    fi
}
