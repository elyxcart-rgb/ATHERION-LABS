"""SONIC AI Dashboard — local HTTP dashboard for remote control.

Plain HTTP on port 8000 with AES-256-CBC encrypted WebSocket communication.
"""
from .server import DashboardServer, PORT, UPLOADS_DIR

__all__ = ["DashboardServer", "PORT", "UPLOADS_DIR"]
