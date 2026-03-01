#!/usr/bin/env python3
"""
Health check server for container orchestration
"""

import os
import json
import socket
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
import threading

logger = logging.getLogger(__name__)

class HealthHandler(BaseHTTPRequestHandler):
    """HTTP request handler for health checks"""
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            health_status = {
                'status': 'healthy',
                'service': 'jd-telegram-bot',
                'timestamp': self.date_time_string()
            }
            
            self.wfile.write(json.dumps(health_status).encode())
        elif self.path == '/ready':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            ready_status = {
                'status': 'ready',
                'service': 'jd-telegram-bot'
            }
            
            self.wfile.write(json.dumps(ready_status).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

class HealthServer:
    """Health check server running in separate thread"""
    
    def __init__(self, port: int = 8080):
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False
    
    def start(self):
        """Start health check server"""
        try:
            self.server = HTTPServer(('0.0.0.0', self.port), HealthHandler)
            self.running = True
            logger.info(f"Health check server started on port {self.port}")
            self.server.serve_forever()
        except Exception as e:
            logger.error(f"Failed to start health check server: {e}")
    
    def stop(self):
        """Stop health check server"""
        self.running = False
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logger.info("Health check server stopped")
    
    def is_running(self) -> bool:
        """Check if server is running"""
        return self.running
