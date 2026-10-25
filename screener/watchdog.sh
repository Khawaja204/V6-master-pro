#!/bin/bash
cd ~/workspace/screener || exit 1
while true; do
  if ! ps -p "$(cat bot.pid 2>/dev/null)" >/dev/null 2>&1; then
    nohup .venv/bin/python main.py >> bot.log 2>&1 &
    echo $! > bot.pid
    echo "$(date -u '+%F %T UTC') restarted main.py pid $(cat bot.pid)" >> watchdog.log
  fi
  date -u '+%F %T UTC' > heartbeat.txt
  sleep 60
done
