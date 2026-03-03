"""
Connection manager for myCobot 280 Pi over TCP/IP socket.
Wraps MyCobot280Socket with connect/reconnect/health-check logic.
"""

import time
import logging
from typing import Optional
from pymycobot import MyCobot280Socket
from src.cobot.config import get_config

logger = logging.getLogger(__name__)


class CobotConnection:
    """
    Manages the TCP socket connection to a myCobot 280 Pi.

    The myCobot Pi must be running the TCP server (Server_280.py or
    the MyStudio TCP server) on the configured port (default 9000).
    """

    def __init__(self, host: str = None, port: int = None):
        cfg = get_config().robot
        self.host = host or cfg.host
        self.port = port or cfg.port
        self._mc: Optional[MyCobot280Socket] = None

    @property
    def mc(self) -> MyCobot280Socket:
        """Get the active MyCobot280Socket instance, connecting if needed."""
        if self._mc is None:
            self.connect()
        return self._mc

    def connect(self) -> MyCobot280Socket:
        """Establish TCP connection to the robot."""
        logger.info(f"Connecting to myCobot at {self.host}:{self.port} ...")
        self._mc = MyCobot280Socket(self.host, self.port)
        # Set interpolation mode for smooth motion
        self._mc.set_fresh_mode(0)
        time.sleep(0.5)
        logger.info("Connected to myCobot successfully.")
        return self._mc

    def disconnect(self):
        """Close the connection."""
        if self._mc is not None:
            try:
                self._mc.close()
            except Exception:
                pass
            self._mc = None
            logger.info("Disconnected from myCobot.")

    def reconnect(self) -> MyCobot280Socket:
        """Disconnect and reconnect."""
        self.disconnect()
        return self.connect()

    def is_alive(self) -> bool:
        """Check if the robot connection is alive."""
        try:
            if self._mc is None:
                return False
            result = self._mc.is_controller_connected()
            return result == 1
        except Exception:
            return False

    def ensure_connected(self) -> MyCobot280Socket:
        """Ensure we have a live connection, reconnecting if necessary."""
        if not self.is_alive():
            logger.warning("Connection lost. Reconnecting...")
            return self.reconnect()
        return self._mc


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
_connection: Optional[CobotConnection] = None


def get_connection() -> CobotConnection:
    """Get the global CobotConnection singleton."""
    global _connection
    if _connection is None:
        _connection = CobotConnection()
    return _connection


def get_mc() -> MyCobot280Socket:
    """Shortcut: get the connected MyCobot280Socket instance."""
    return get_connection().mc
