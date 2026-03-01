#!/usr/bin/env python3
"""
JD Download Telegram Bot
Main bot file with health checks and error recovery
"""

import os
import sys
import asyncio
import logging
import signal
import humanize
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, CallbackQueryHandler
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

from config import (
    TELEGRAM_BOT_TOKEN, ALLOWED_USERS, DOWNLOAD_PATH, 
    MAX_FILE_SIZE_BYTES, LOG_LEVEL, HEALTH_CHECK_PORT
)
from jd_client import JDownloaderClient
from healthcheck import HealthServer

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)

# Initialize JDownloader client
jd_client = JDownloaderClient()

# Store user download status and tasks
user_downloads: Dict[int, Dict] = {}
active_tasks: Dict[int, asyncio.Task] = {}

# Health check server
health_server = HealthServer(port=HEALTH_CHECK_PORT)

# Authentication decorator
def authorized_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not is_authorized(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            logger.warning(f"Unauthorized access attempt by user {user_id}")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def is_authorized(user_id: int) -> bool:
    """Check if user is authorized"""
    if not ALLOWED_USERS or ALLOWED_USERS[0] == '':
        return True
    return str(user_id) in ALLOWED_USERS

def get_progress_bar(percentage: float, width: int = 20) -> str:
    """Generate a progress bar"""
    filled = int(width * percentage / 100)
    bar = '█' * filled + '░' * (width - filled)
    return f"`[{bar}]`"

def format_size(size: int) -> str:
    """Format file size"""
    if size == 0:
        return "0 B"
    return humanize.naturalsize(size)

async def health_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Health check endpoint"""
    status = "✅" if jd_client.connected else "⚠️"
    await update.message.reply_text(
        f"Bot Status: {status}\n"
        f"JDownloader: {'Connected' if jd_client.connected else 'Disconnected'}\n"
        f"Active Downloads: {len(await jd_client.get_downloads_info())}\n"
        f"Monitoring Users: {len(user_downloads)}"
    )

@authorized_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    welcome_msg = (
        f"👋 Hello {user.first_name}!\n\n"
        "I'm a JDownloader Telegram Bot. Send me any download link "
        "(HTTP, FTP, torrent, etc.) and I'll download it for you.\n\n"
        "**Commands:**\n"
        "/start - Show this message\n"
        "/status - Check download status\n"
        "/downloads - List all downloads\n"
        "/cancel - Cancel current downloads\n"
        "/help - Show help\n"
        "/health - Bot health check\n\n"
        f"**Max file size:** {format_size(MAX_FILE_SIZE_BYTES)}"
    )
    
    await update.message.reply_text(welcome_msg, parse_mode=ParseMode.MARKDOWN)

@authorized_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = (
        "**How to use:**\n"
        "1. Send me a direct download link\n"
        "2. I'll add it to JDownloader\n"
        "3. Check status with /status\n"
        "4. Once complete, files will be uploaded\n\n"
        "**Supported links:**\n"
        "• HTTP/HTTPS\n"
        "• FTP\n"
        "• Magnet links\n"
        "• Torrent files\n"
        "• Many file hosts\n\n"
        "**Commands:**\n"
        "/status - Current download progress\n"
        "/downloads - List all active downloads\n"
        "/cancel - Cancel active downloads\n"
        "/cleanup - Remove completed downloads\n"
        "/restart - Restart JDownloader connection\n\n"
        "**Note:** Large files may take time to upload."
    )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

@authorized_only
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Status command handler"""
    status_msg = await update.message.reply_text("🔍 Checking download status...")
    
    try:
        downloads = await jd_client.get_downloads_info()
        
        if not downloads:
            await status_msg.edit_text("📊 No active downloads.")
            return
        
        msg = "**📊 Download Status:**\n\n"
        
        for i, dl in enumerate(downloads[:5], 1):
            if dl['total'] > 0:
                percentage = (dl['downloaded'] / dl['total']) * 100
            else:
                percentage = 0
            
            progress = get_progress_bar(percentage)
            downloaded = format_size(dl['downloaded'])
            total = format_size(dl['total'])
            speed = format_size(dl['speed']) + "/s" if dl['speed'] > 0 else "N/A"
            
            if dl['eta'] > 0:
                eta = f"{dl['eta'] // 60}m {dl['eta'] % 60}s"
            else:
                eta = "N/A"
            
            msg += (
                f"**{i}. {dl['name'][:50]}**\n"
                f"{progress} {percentage:.1f}%\n"
                f"📥 {downloaded} / {total}\n"
                f"⚡ Speed: {speed} | ⏱️ ETA: {eta}\n"
                f"📌 Status: {dl['status']}\n\n"
            )
        
        if len(downloads) > 5:
            msg += f"*And {len(downloads) - 5} more downloads...*\n"
        
        # Add keyboard for actions
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status"),
             InlineKeyboardButton("❌ Cancel All", callback_data="cancel_all")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_msg.edit_text(
            msg, 
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Status error: {e}")
        await status_msg.edit_text(f"❌ Error getting status: {str(e)}")

@authorized_only
async def downloads_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all downloads command"""
    downloads = await jd_client.get_downloads_info()
    
    if not downloads:
        await update.message.reply_text("📊 No downloads in queue.")
        return
    
    msg = "**📋 All Downloads:**\n\n"
    for i, dl in enumerate(downloads, 1):
        status_emoji = "🟢" if dl['status'] == "Running" else "🟡" if dl['downloaded'] > 0 else "🔴"
        msg += f"{status_emoji} **{i}. {dl['name'][:50]}**\n"
        msg += f"   Status: {dl['status']}\n"
        msg += f"   Size: {format_size(dl['downloaded'])} / {format_size(dl['total'])}\n\n"
    
    # Split long messages
    if len(msg) > 4096:
        for x in range(0, len(msg), 4096):
            await update.message.reply_text(msg[x:x+4096], parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

@authorized_only
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel downloads command"""
    msg = await update.message.reply_text("🔄 Cancelling downloads...")
    
    try:
        await jd_client.cancel_all_downloads()
        await msg.edit_text("✅ All downloads cancelled successfully.")
    except Exception as e:
        await msg.edit_text(f"❌ Failed to cancel downloads: {e}")

@authorized_only
async def cleanup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cleanup completed downloads"""
    msg = await update.message.reply_text("🧹 Cleaning up...")
    
    try:
        await jd_client.cleanup_completed()
        await msg.edit_text("✅ Cleanup completed successfully.")
    except Exception as e:
        await msg.edit_text(f"❌ Cleanup failed: {e}")

@authorized_only
async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restart JDownloader connection"""
    msg = await update.message.reply_text("🔄 Restarting JDownloader connection...")
    
    try:
        success = await jd_client.reconnect()
        if success:
            await msg.edit_text("✅ Successfully reconnected to JDownloader.")
        else:
            await msg.edit_text("❌ Failed to reconnect to JDownloader.")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

@authorized_only
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle download links"""
    user_id = update.effective_user.id
    url = update.message.text.strip()
    
    # Validate URL
    if not url.startswith(('http://', 'https://', 'ftp://', 'magnet:', 'file://')):
        await update.message.reply_text(
            "❌ Please send a valid link:\n"
            "• HTTP/HTTPS\n"
            "• FTP\n"
            "• Magnet links"
        )
        return
    
    status_msg = await update.message.reply_text(
        f"🔍 Processing link: {url[:50]}...\n"
        "Adding to JDownloader..."
    )
    
    try:
        # Ensure JDownloader connection
        if not jd_client.connected:
            await status_msg.edit_text("🔄 Connecting to JDownloader...")
            if not await jd_client.connect():
                await status_msg.edit_text(
                    "❌ Failed to connect to JDownloader.\n"
                    "Please check:\n"
                    "1. JDownloader is running\n"
                    "2. MyJDownloader credentials are correct\n"
                    "3. Network connectivity"
                )
                return
        
        # Add link
        await status_msg.edit_text("📥 Adding link to download queue...")
        success, message = await jd_client.add_link(url)
        
        if success:
            await status_msg.edit_text(
                f"✅ {message}\n\n"
                "Use /status to check download progress.\n"
                "I'll notify you when downloads are complete."
            )
            
            # Start monitoring if not already
            if user_id not in user_downloads:
                user_downloads[user_id] = {'active': True}
                if user_id not in active_tasks:
                    task = asyncio.create_task(
                        monitor_downloads(update.effective_user.id, context)
                    )
                    active_tasks[user_id] = task
        else:
            await status_msg.edit_text(f"❌ {message}")
            
    except Exception as e:
        logger.error(f"Link handling error: {e}")
        await status_msg.edit_text(f"❌ Unexpected error: {str(e)[:100]}")

@authorized_only
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle torrent files"""
    user_id = update.effective_user.id
    document = update.message.document
    
    # Check if it's a torrent file
    if not document.file_name.endswith('.torrent'):
        await update.message.reply_text("❌ Please send a valid .torrent file.")
        return
    
    # Check file size (max 10MB for torrent files)
    if document.file_size > 10 * 1024 * 1024:
        await update.message.reply_text("❌ Torrent file too large (max 10MB).")
        return
    
    status_msg = await update.message.reply_text("📥 Downloading torrent file...")
    
    try:
        # Download torrent file
        file = await context.bot.get_file(document.file_id)
        torrent_path = os.path.join(DOWNLOAD_PATH, f"torrent_{user_id}_{document.file_name}")
        await file.download_to_drive(torrent_path)
        
        await status_msg.edit_text("✅ Torrent file saved. Adding to JDownloader...")
        
        # Connect to JDownloader if needed
        if not jd_client.connected:
            await jd_client.connect()
        
        # Add torrent
        success, message = await jd_client.add_link(torrent_path)
        
        if success:
            await status_msg.edit_text(
                f"✅ {message}\n\n"
                "Use /status to check download progress."
            )
            
            # Start monitoring
            if user_id not in user_downloads:
                user_downloads[user_id] = {'active': True}
                if user_id not in active_tasks:
                    task = asyncio.create_task(
                        monitor_downloads(user_id, context)
                    )
                    active_tasks[user_id] = task
        else:
            await status_msg.edit_text(f"❌ {message}")
            
    except Exception as e:
        logger.error(f"File handling error: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)[:100]}")

async def monitor_downloads(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Background task to monitor downloads"""
    logger.info(f"Started monitoring for user {user_id}")
    
    while user_id in user_downloads and user_downloads[user_id].get('active', True):
        try:
            # Get completed files
            completed_files = await jd_client.get_completed_files()
            
            for file_info in completed_files:
                file_path = file_info['path']
                file_name = file_info['name']
                file_size = file_info['size']
                
                # Verify file exists and is complete
                if os.path.exists(file_path) and os.path.getsize(file_path) == file_size:
                    logger.info(f"File completed: {file_name} ({format_size(file_size)})")
                    
                    # Check file size limit
                    if file_size <= MAX_FILE_SIZE_BYTES:
                        # Upload file
                        await upload_file_with_progress(user_id, context, file_path, file_name)
                    else:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"⚠️ File too large for Telegram: {file_name}\n"
                                 f"Size: {format_size(file_size)}\n"
                                 f"Max: {format_size(MAX_FILE_SIZE_BYTES)}\n"
                                 f"Please download directly from JDownloader."
                        )
                    
                    # Clean up file
                    try:
                        os.remove(file_path)
                        logger.info(f"Removed file: {file_path}")
                    except Exception as e:
                        logger.error(f"Failed to remove file {file_path}: {e}")
            
            # Clean up completed downloads from JDownloader
            await jd_client.cleanup_completed()
            
        except Exception as e:
            logger.error(f"Monitor error for user {user_id}: {e}")
            await asyncio.sleep(60)  # Longer delay on error
        
        await asyncio.sleep(30)  # Check every 30 seconds
    
    logger.info(f"Stopped monitoring for user {user_id}")

async def upload_file_with_progress(user_id: int, context: ContextTypes.DEFAULT_TYPE, file_path: str, file_name: str):
    """Upload file with progress updates"""
    file_size = os.path.getsize(file_path)
    
    # Send initial message
    progress_msg = await context.bot.send_message(
        chat_id=user_id,
        text=f"📤 **Uploading:** {file_name}\n"
             f"📊 **Size:** {format_size(file_size)}\n"
             f"⏳ **Progress:** 0%",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Upload file with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(file_path, 'rb') as file:
                    await context.bot.send_document(
                        chat_id=user_id,
                        document=file,
                        filename=file_name,
                        caption=f"✅ **Download Complete!**\n"
                               f"📁 **File:** {file_name}\n"
                               f"📊 **Size:** {format_size(file_size)}",
                        parse_mode=ParseMode.MARKDOWN,
                        read_timeout=300,
                        write_timeout=300,
                        connect_timeout=60
                    )
                
                # Update progress message
                await progress_msg.edit_text(
                    f"✅ **Upload Complete!**\n"
                    f"📁 {file_name}\n"
                    f"📊 {format_size(file_size)}",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                logger.info(f"Successfully uploaded {file_name} to user {user_id}")
                break
                
            except TelegramError as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(5 * (attempt + 1))
                    await progress_msg.edit_text(
                        f"🔄 Retrying upload ({attempt + 2}/{max_retries})...\n"
                        f"Error: {str(e)[:50]}"
                    )
                else:
                    raise e
        
    except Exception as e:
        logger.error(f"Upload failed for {file_name}: {e}")
        await progress_msg.edit_text(
            f"❌ **Upload Failed**\n"
            f"File: {file_name}\n"
            f"Error: {str(e)[:100]}",
            parse_mode=ParseMode.MARKDOWN
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "refresh_status":
        await status_command(update, context)
    elif query.data == "cancel_all":
        await cancel_command(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An error occurred. Please try again later."
            )
    except:
        pass

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Received shutdown signal, cleaning up...")
    
    # Cancel all monitoring tasks
    for user_id, task in active_tasks.items():
        task.cancel()
    
    # Stop health check server
    health_server.stop()
    
    logger.info("Shutdown complete")
    sys.exit(0)

def main():
    """Main entry point"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start health check server in background
    import threading
    health_thread = threading.Thread(target=health_server.start, daemon=True)
    health_thread.start()
    
    # Create application
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("downloads", downloads_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("cleanup", cleanup_command))
    application.add_handler(CommandHandler("restart", restart_command))
    application.add_handler(CommandHandler("health", health_check))
    
    # Add callback handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add message handlers
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_link
    ))
    application.add_handler(MessageHandler(
        filters.Document.FileExtension("torrent"), handle_file
    ))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start bot
    logger.info("🤖 Bot starting up...")
    logger.info(f"Authorized users: {ALLOWED_USERS if ALLOWED_USERS[0] else 'All users'}")
    logger.info(f"Download path: {DOWNLOAD_PATH}")
    logger.info(f"Max file size: {format_size(MAX_FILE_SIZE_BYTES)}")
    
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
