#!/usr/bin/env bash
# V6 Master Pro — one-word command shortcuts
# Usage: source v6-cmd.sh   (or add to .bash_aliases)

deploy() {
    echo "🚀 Deploying V6 Master Pro..."
    pkill -f "python3 main.py" 2>/dev/null && echo "   ↳ killed old process" || echo "   ↳ no old process running"
    sleep 1
    nohup python3 /home/runner/workspace/main.py > /home/runner/workspace/v6_server.log 2>&1 &
    echo "   ↳ started PID $!"
}

stop() {
    echo "🛑 Stopping V6 Master Pro..."
    if pkill -f "python3 main.py"; then
        echo "   ↳ process killed"
    else
        echo "   ↳ no running process found"
    fi
}

restart() {
    deploy
}

status() {
    echo "📊 V6 Master Pro status:"
    PIDS=$(pgrep -f "python3 main.py")
    if [ -n "$PIDS" ]; then
        echo "   ↳ RUNNING — PID(s): $PIDS"
    else
        echo "   ↳ NOT RUNNING"
    fi
    LOG=/home/runner/workspace/v6_server.log
    if [ -f "$LOG" ]; then
        echo ""
        echo "   Last 5 log lines:"
        tail -5 "$LOG" | sed 's/^/      /'
    else
        echo "   (no log file yet)"
    fi
}

logs() {
    tail -30 /home/runner/workspace/v6_server.log 2>/dev/null || echo "No log file found at v6_server.log"
}

save() {
    echo "💾 Saving project..."
    bash /home/runner/workspace/saveproj.sh
}

push() {
    echo "📤 Saving and pushing to GitHub..."
    bash /home/runner/workspace/saveproj.sh
    cd /home/runner/workspace
    git add .
    git commit -m "v6 update"
    git push
}

full() {
    echo "⚡ Running full sequence: save → deploy → push"
    save
    deploy
    push
}

echo "✅ V6 commands loaded: deploy | stop | restart | status | logs | save | push | full"
