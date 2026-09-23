#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$SCRIPT_DIR/a_share_finance_app.pid"

if [ ! -f "$PIDFILE" ]; then
  echo "未发现运行中的服务。"
else
  PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    sleep 1
    echo "服务已停止。"
  else
    echo "服务已不在运行。"
  fi
  rm -f "$PIDFILE"
fi

read -r -p "按回车键关闭此窗口..."
