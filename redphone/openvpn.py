"""OpenVPN connection management for Asuswrt-Merlin router VPN."""

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .config import config

logger = logging.getLogger(__name__)


class OpenVPNManager:
    """Manage OpenVPN connection to router VPN server."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._running = False
        self._connected = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._on_connect: Optional[Callable[[], None]] = None
        self._on_disconnect: Optional[Callable[[], None]] = None

    @property
    def is_connected(self) -> bool:
        """Check if VPN is connected."""
        return self._connected

    def on_connect(self, callback: Callable[[], None]) -> None:
        """Register callback for VPN connect event."""
        self._on_connect = callback

    def on_disconnect(self, callback: Callable[[], None]) -> None:
        """Register callback for VPN disconnect event."""
        self._on_disconnect = callback

    def setup_credentials(self, username: str, password: str) -> bool:
        """
        Set up OpenVPN credentials file.
        
        Creates auth.txt with username and password for auto-login.
        """
        auth_file = Path(config.get("network.openvpn.auth_file", "/etc/redphone/vpn/auth.txt"))
        
        try:
            auth_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(auth_file, "w") as f:
                f.write(f"{username}\n{password}\n")
            
            # Secure the file
            os.chmod(auth_file, 0o600)
            
            logger.info(f"Credentials saved to {auth_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")
            return False

    def setup_config(self, ovpn_content: str) -> bool:
        """
        Set up OpenVPN config file.
        
        Writes the .ovpn content and patches it for auth-user-pass.
        """
        config_file = Path(config.get("network.openvpn.config_file", "/etc/redphone/vpn/client.ovpn"))
        auth_file = Path(config.get("network.openvpn.auth_file", "/etc/redphone/vpn/auth.txt"))
        
        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if auth-user-pass is already configured
            lines = ovpn_content.split("\n")
            has_auth = any(line.strip().startswith("auth-user-pass") for line in lines)
            
            # Add auth-user-pass directive if not present
            if not has_auth:
                lines.append(f"auth-user-pass {auth_file}")
            else:
                # Update existing auth-user-pass to point to our file
                lines = [
                    f"auth-user-pass {auth_file}" if line.strip().startswith("auth-user-pass") else line
                    for line in lines
                ]
            
            with open(config_file, "w") as f:
                f.write("\n".join(lines))
            
            os.chmod(config_file, 0o600)
            
            logger.info(f"OpenVPN config saved to {config_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save OpenVPN config: {e}")
            return False

    def start(self) -> bool:
        """Start OpenVPN connection."""
        if self._running:
            logger.warning("OpenVPN already running")
            return True

        config_file = config.get("network.openvpn.config_file", "/etc/redphone/vpn/client.ovpn")
        
        if not os.path.exists(config_file):
            logger.error(f"OpenVPN config not found: {config_file}")
            return False

        try:
            # Start OpenVPN
            self._process = subprocess.Popen(
                ["openvpn", "--config", config_file, "--daemon", "--log", "/var/log/redphone/openvpn.log"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            self._running = True
            
            # Start monitor thread
            self._monitor_thread = threading.Thread(target=self._monitor_connection, daemon=True)
            self._monitor_thread.start()
            
            logger.info("OpenVPN started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start OpenVPN: {e}")
            return False

    def stop(self) -> None:
        """Stop OpenVPN connection."""
        self._running = False
        
        try:
            # Kill OpenVPN process
            subprocess.run(["killall", "openvpn"], capture_output=True, timeout=5)
        except Exception as e:
            logger.error(f"Error stopping OpenVPN: {e}")
        
        self._connected = False
        self._process = None

    def _monitor_connection(self) -> None:
        """Monitor VPN connection status."""
        reconnect_delay = config.get("network.openvpn.reconnect_delay", 10)
        auto_reconnect = config.get("network.openvpn.auto_reconnect", True)
        
        while self._running:
            was_connected = self._connected
            self._connected = self._check_connection()
            
            # Connection state changed
            if self._connected and not was_connected:
                logger.info("VPN connected")
                if self._on_connect:
                    self._on_connect()
                    
            elif not self._connected and was_connected:
                logger.warning("VPN disconnected")
                if self._on_disconnect:
                    self._on_disconnect()
                
                # Auto-reconnect
                if auto_reconnect and self._running:
                    logger.info(f"Reconnecting in {reconnect_delay}s...")
                    time.sleep(reconnect_delay)
                    self._reconnect()
            
            time.sleep(5)

    def _check_connection(self) -> bool:
        """Check if VPN tunnel is up."""
        try:
            # Check for tun interface
            result = subprocess.run(
                ["ip", "link", "show", "tun0"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _reconnect(self) -> None:
        """Attempt to reconnect VPN."""
        try:
            # Kill any existing OpenVPN
            subprocess.run(["killall", "openvpn"], capture_output=True, timeout=5)
            time.sleep(2)
            
            # Restart
            config_file = config.get("network.openvpn.config_file", "/etc/redphone/vpn/client.ovpn")
            subprocess.Popen(
                ["openvpn", "--config", config_file, "--daemon", "--log", "/var/log/redphone/openvpn.log"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            logger.info("OpenVPN reconnection initiated")
            
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")

    def get_vpn_ip(self) -> Optional[str]:
        """Get the VPN tunnel IP address."""
        try:
            result = subprocess.run(
                ["ip", "-4", "addr", "show", "tun0"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "inet " in line:
                        # Extract IP from "inet 10.8.0.2/24 ..."
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            return parts[1].split("/")[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get VPN IP: {e}")
            return None


# Global instance
openvpn = OpenVPNManager()
