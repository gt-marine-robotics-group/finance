#!/bin/bash
set -e

# Write rclone config from environment variable if provided
if [ -n "$RCLONE_CONFIG_CONTENT" ]; then
    mkdir -p /root/.config/rclone
    echo "$RCLONE_CONFIG_CONTENT" > /root/.config/rclone/rclone.conf
fi

# Initial pull of xlsx
echo "[start] Pulling latest xlsx from SharePoint..."
rclone copy "$RCLONE_REMOTE" /root/mrg-finance/ 2>&1 || echo "[start] rclone pull failed (will retry via cron)"

# Start cron daemon for periodic sync
cron

# Start gunicorn with the Flask app
echo "[start] Starting web server..."
exec gunicorn app:app \
    --bind 0.0.0.0:${PORT:-5000} \
    --workers 2 \
    --timeout 120 \
    --preload
