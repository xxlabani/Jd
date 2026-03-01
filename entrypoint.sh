#!/bin/bash
set -e

echo "🚀 Starting JD Telegram Bot..."

# Check required environment variables
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ TELEGRAM_BOT_TOKEN is not set"
    exit 1
fi

if [ -z "$JD_EMAIL" ] || [ -z "$JD_PASSWORD" ]; then
    echo "❌ JD_EMAIL and JD_PASSWORD must be set"
    exit 1
fi

# Create log directory if it doesn't exist
mkdir -p /app/logs

# Start supervisor
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
