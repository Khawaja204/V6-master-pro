# Screener shortcuts. Har nayi Shell session mein ek baar chalayein:
#   source ~/workspace/screener/shortcuts.sh
SC_DIR="$HOME/workspace/screener"
SC_PY="$SC_DIR/.venv/bin/python"
SC_PID="$SC_DIR/bot.pid"
SC_LOG="$SC_DIR/bot.log"

sc_check() {
  cd "$SC_DIR" && "$SC_PY" -m py_compile config.py fetcher.py strategy.py alerter.py main.py && echo "CHECK OK"
}

sc_run() {
  if [ -f "$SC_PID" ] && kill -0 "$(cat "$SC_PID")" 2>/dev/null; then
    echo "Already running (pid $(cat "$SC_PID"))"
    return 0
  fi
  cd "$SC_DIR" && nohup "$SC_PY" main.py >> "$SC_LOG" 2>&1 &
  echo $! > "$SC_PID"
  echo "Started pid $(cat "$SC_PID"). Logs ke liye: sc_logs"
}

sc_stop() {
  if [ -f "$SC_PID" ]; then
    kill "$(cat "$SC_PID")" 2>/dev/null && echo "Stopped"
    rm -f "$SC_PID"
  else
    echo "Not running"
  fi
}

sc_logs() {
  tail -n "${1:-40}" "$SC_LOG"
}

sc_push() {
  local msg="${*:-Update screener}"
  cd "$HOME/workspace" || return 1
  git add -- screener/*.py screener/requirements.txt screener/shortcuts.sh && \
  git commit -m "$msg" && \
  git push origin main
}

push()   { sc_push "${*:-Update screener}"; }
save()   { sc_push "${*:-Save progress}"; }
deploy() { sc_check && sc_run; }
