#!/usr/bin/env python3
"""
Configuration management with environment variables
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is required")

# JDownloader Configuration
JD_EMAIL = os.getenv('JD_EMAIL')
JD_PASSWORD = os.getenv('JD_PASSWORD')
JD_DEVICE_NAME = os.getenv('JD_DEVICE_NAME', 'TelegramBot')

if not JD_EMAIL or not JD_PASSWORD:
    raise ValueError("JD_EMAIL and JD_PASSWORD are required")

# User Authorization
ALLOWED_USERS = os.getenv('ALLOWED_USERS', '').split(',')
ALLOWED_USERS = [user.strip() for user in ALLOWED_USERS if user.strip()]

# Download Settings
DOWNLOAD_PATH = os.getenv('DOWNLOAD_PATH', '/app/downloads')
MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', '2000'))  # MB
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE * 1024 * 1024

# Health Check Settings
HEALTH_CHECK_PORT = int(os.getenv('HEALTH_CHECK_PORT', '8080'))

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', '/app/logs/bot.log')

# Create necessary directories
Path(DOWNLOAD_PATH).mkdir(parents=True, exist_ok=True)
Path(os.path.dirname(LOG_FILE)).mkdir(parents=True, exist_ok=True)

# Connection Settings
JD_CONNECTION_TIMEOUT = int(os.getenv('JD_CONNECTION_TIMEOUT', '30'))
JD_RECONNECT_INTERVAL = int(os.getenv('JD_RECONNECT_INTERVAL', '300'))

# Upload Settings
UPLOAD_CHUNK_SIZE = int(os.getenv('UPLOAD_CHUNK_SIZE', '5242880'))  # 5MB
UPLOAD_RETRY_COUNT = int(os.getenv('UPLOAD_RETRY_COUNT', '3'))
