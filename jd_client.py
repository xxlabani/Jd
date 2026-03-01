#!/usr/bin/env python3
"""
JDownloader Client with connection management and error handling
"""

import os
import time
import asyncio
import logging
from typing import List, Dict, Tuple, Optional
from jdcloudapi import JDCli

from config import JD_EMAIL, JD_PASSWORD, JD_DEVICE_NAME, DOWNLOAD_PATH

logger = logging.getLogger(__name__)

class JDownloaderClient:
    def __init__(self):
        self.client = None
        self.connected = False
        self.last_connection_attempt = 0
        self.connection_retry_delay = 60  # seconds
        self.max_retries = 3
        
    async def connect(self) -> bool:
        """Connect to JDownloader with retry logic"""
        current_time = time.time()
        
        # Rate limit connection attempts
        if current_time - self.last_connection_attempt < self.connection_retry_delay:
            logger.debug("Connection attempt rate limited")
            return self.connected
        
        self.last_connection_attempt = current_time
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Connecting to JDownloader (attempt {attempt + 1}/{self.max_retries})")
                
                # Run in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                self.client = await loop.run_in_executor(
                    None, 
                    lambda: JDCli()
                )
                
                # Connect to MyJDownloader
                await loop.run_in_executor(
                    None,
                    lambda: self.client.connect(JD_EMAIL, JD_PASSWORD, JD_DEVICE_NAME)
                )
                
                self.connected = True
                logger.info("✅ Connected to JDownloader successfully")
                return True
                
            except Exception as e:
                logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                self.connected = False
                
                if attempt < self.max_retries - 1:
                    wait_time = 5 * (attempt + 1)
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("All connection attempts failed")
        
        return False
    
    async def reconnect(self) -> bool:
        """Force reconnection"""
        self.connected = False
        self.client = None
        return await self.connect()
    
    async def ensure_connection(self) -> bool:
        """Ensure connection is active, reconnect if needed"""
        if not self.connected:
            return await self.connect()
        
        try:
            # Test connection by getting package list
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.get_package_list()
            )
            return True
        except:
            logger.warning("Connection lost, reconnecting...")
            self.connected = False
            return await self.connect()
    
    async def add_link(self, url: str) -> Tuple[bool, str]:
        """Add a link to JDownloader"""
        if not await self.ensure_connection():
            return False, "Failed to connect to JDownloader"
        
        try:
            loop = asyncio.get_event_loop()
            
            # Add links to JDownloader
            await loop.run_in_executor(
                None,
                lambda: self.client.add_links([url], DOWNLOAD_PATH)
            )
            
            logger.info(f"Added link: {url[:50]}...")
            return True, "Link added to download queue"
            
        except Exception as e:
            logger.error(f"Failed to add link: {e}")
            return False, f"Failed to add link: {str(e)[:100]}"
    
    async def get_downloads_info(self) -> List[Dict]:
        """Get information about current downloads"""
        if not await self.ensure_connection():
            return []
        
        try:
            loop = asyncio.get_event_loop()
            
            # Get package list
            packages = await loop.run_in_executor(
                None,
                lambda: self.client.get_package_list()
            )
            
            downloads = []
            
            for package in packages:
                if hasattr(package, 'links'):
                    for link in package.links:
                        if hasattr(link, 'bytes_total') and link.bytes_total > 0:
                            downloads.append({
                                'name': getattr(link, 'name', 'Unknown'),
                                'package': getattr(package, 'name', 'Unknown'),
                                'total': getattr(link, 'bytes_total', 0),
                                'downloaded': getattr(link, 'bytes_loaded', 0),
                                'speed': getattr(link, 'speed', 0),
                                'eta': getattr(link, 'eta', 0),
                                'status': getattr(link, 'status', 'Unknown'),
                                'uuid': getattr(link, 'uuid', None)
                            })
            
            logger.debug(f"Found {len(downloads)} active downloads")
            return downloads
            
        except Exception as e:
            logger.error(f"Failed to get downloads info: {e}")
            return []
    
    async def get_completed_files(self) -> List[Dict]:
        """Get list of completed files"""
        if not await self.ensure_connection():
            return []
        
        try:
            loop = asyncio.get_event_loop()
            
            # Get finished downloads
            finished = await loop.run_in_executor(
                None,
                lambda: self.client.get_finished_downloads()
            )
            
            files = []
            
            for item in finished:
                if hasattr(item, 'save_to') and hasattr(item, 'name'):
                    file_path = getattr(item, 'save_to')
                    if os.path.exists(file_path):
                        files.append({
                            'path': file_path,
                            'name': getattr(item, 'name'),
                            'size': getattr(item, 'bytes_total', 0),
                            'uuid': getattr(item, 'uuid', None)
                        })
            
            logger.info(f"Found {len(files)} completed files")
            return files
            
        except Exception as e:
            logger.error(f"Failed to get completed files: {e}")
            return []
    
    async def cancel_download(self, link_uuid: str) -> bool:
        """Cancel a specific download"""
        if not await self.ensure_connection():
            return False
        
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.remove_links([link_uuid])
            )
            logger.info(f"Cancelled download {link_uuid}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel download: {e}")
            return False
    
    async def cancel_all_downloads(self) -> bool:
        """Cancel all downloads"""
        if not await self.ensure_connection():
            return False
        
        try:
            downloads = await self.get_downloads_info()
            for dl in downloads:
                if dl.get('uuid'):
                    await self.cancel_download(dl['uuid'])
            logger.info("Cancelled all downloads")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel all downloads: {e}")
            return False
    
    async def cleanup_completed(self) -> bool:
        """Remove completed downloads from list"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.cleanup_finished()
            )
            logger.info("Cleaned up completed downloads")
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup: {e}")
            return False
    
    async def get_download_speed(self) -> int:
        """Get current download speed"""
        downloads = await self.get_downloads_info()
        total_speed = sum(dl.get('speed', 0) for dl in downloads)
        return total_speed
    
    async def get_queue_size(self) -> int:
        """Get number of items in queue"""
        downloads = await self.get_downloads_info()
        return len(downloads)
