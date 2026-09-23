#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$SCRIPT_DIR/a_share_finance_app.py"
PORT="${PORT:-8892}"
LOG="$SCRIPT_DIR/a_share_finance_app.log"
PIDFILE="$SCRIPT_DIR/a_share_finance_app.pid"

if [ ! -f "$APP" ]; then
  echo "未找到程序：$APP"
  read -r -p "按回车键退出..."
  exit 1
fi

if ! (cd "$SCRIPT_DIR" && /usr/bin/python3 -c "import openpyxl") >/dev/null 2>&1; then
  echo "未找到随应用提供的Excel导出组件 openpyxl；网页仍可使用，但Excel导出暂不可用。"
fi

if [ -f "$PIDFILE" ]; then
  OLD_PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "服务已在运行，进程号：$OLD_PID"
  else
    rm -f "$PIDFILE"
  fi
fi

if [ ! -f "$PIDFILE" ]; then
  nohup /usr/bin/python3 "$APP" --port "$PORT" --no-browser >> "$LOG" 2>&1 &
  PID=$!
  echo "$PID" > "$PIDFILE"
  sleep 2
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "启动失败，请查看日志：$LOG"
    tail -30 "$LOG"
    read -r -p "按回车键退出..."
    exit 1
  fi
fi

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
LOCAL_URL="http://127.0.0.1:$PORT"
STATUS_FILE="$SCRIPT_DIR/a_share_finance_app_status.txt"
{
  echo "本机访问：$LOCAL_URL"
  if [ -n "$LAN_IP" ]; then
    echo "局域网访问：http://$LAN_IP:$PORT"
  else
    echo "局域网访问：未能自动获取IP"
  fi
  echo "进程号：$(cat "$PIDFILE")"
  echo "启动时间：$(date '+%Y-%m-%d %H:%M:%S')"
} > "$STATUS_FILE"

echo ""
echo "A股财务望远镜已启动"
echo "本机访问：$LOCAL_URL"
if [ -n "$LAN_IP" ]; then
  echo "局域网访问：http://$LAN_IP:$PORT"
else
  echo "未能自动获取局域网IP，请在系统设置的网络详情中查看本机IP。"
fi
echo ""
echo "请保持本机开机并连接公司局域网。"
echo "首次访问若被macOS防火墙拦截，请选择允许Python接收入站连接。"
echo "关闭此终端窗口不会停止服务；如需停止，请双击“停止A股财务望远镜.command”。"

open "$LOCAL_URL"
read -r -p "按回车键关闭此窗口..."
