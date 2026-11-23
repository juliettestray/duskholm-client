#!/bin/bash
# Stop the throwaway Haven test server (default port 3500).
PORT="${1:-3500}"
pkill -9 -f "haven $PORT" 2>/dev/null
sleep 1
pgrep -f "haven $PORT" >/dev/null && echo "still running" || echo "stopped"
