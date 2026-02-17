"""Phone discovery service using mDNS and Tailscale API."""

import json
import logging
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

import requests
from zeroconf import ServiceBrowser, ServiceInfo, ServiceListener, Zeroconf

from .config import config

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_redphone._tcp.local."


@dataclass
class Phone:
    """Discovered phone information."""

    name: str
    hostname: str
    ip: str
    extension: int
    status: str = "online"
    last_seen: datetime = field(default_factory=datetime.now)
    source: str = "unknown"  # mdns, tailscale

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "hostname": self.hostname,
            "ip": self.ip,
            "extension": self.extension,
            "status": self.status,
            "last_seen": self.last_seen.isoformat(),
            "source": self.source,
        }


class MDNSListener(ServiceListener):
    """mDNS service listener for local network discovery."""

    def __init__(self, on_update: Callable[[], None]):
        self.phones: dict[str, Phone] = {}
        self.on_update = on_update

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            self._handle_service(info)

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            self._handle_service(info)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        # Extract phone name from service name
        phone_name = name.replace(f".{SERVICE_TYPE}", "")
        if phone_name in self.phones:
            del self.phones[phone_name]
            self.on_update()

    def _handle_service(self, info: ServiceInfo) -> None:
        """Process discovered service."""
        try:
            name = info.name.replace(f".{SERVICE_TYPE}", "")
            ip = socket.inet_ntoa(info.addresses[0]) if info.addresses else ""
            properties = {
                k.decode(): v.decode() if isinstance(v, bytes) else v
                for k, v in info.properties.items()
            }

            phone = Phone(
                name=properties.get("name", name),
                hostname=info.server.rstrip("."),
                ip=ip,
                extension=int(properties.get("extension", 0)),
                status="online",
                last_seen=datetime.now(),
                source="mdns",
            )

            self.phones[name] = phone
            logger.info(f"Discovered phone via mDNS: {phone.name} ({phone.ip})")
            self.on_update()

        except Exception as e:
            logger.error(f"Error processing mDNS service: {e}")


class DiscoveryService:
    """Phone discovery service combining mDNS and Tailscale."""

    def __init__(self):
        self.phones: dict[str, Phone] = {}
        self._zeroconf: Optional[Zeroconf] = None
        self._browser: Optional[ServiceBrowser] = None
        self._mdns_listener: Optional[MDNSListener] = None
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._service_info: Optional[ServiceInfo] = None
        self._callbacks: list[Callable[[list[Phone]], None]] = []

    def start(self) -> None:
        """Start discovery services."""
        self._running = True

        # Start mDNS
        if config.get("discovery.mdns", True):
            self._start_mdns()

        # Start Tailscale polling
        if config.get("discovery.tailscale_api", True):
            self._start_tailscale_polling()

        # Register ourselves
        self._register_service()

    def stop(self) -> None:
        """Stop discovery services."""
        self._running = False

        if self._zeroconf:
            if self._service_info:
                self._zeroconf.unregister_service(self._service_info)
            self._zeroconf.close()
            self._zeroconf = None

        if self._poll_thread:
            self._poll_thread.join(timeout=5)

    def on_phones_updated(self, callback: Callable[[list[Phone]], None]) -> None:
        """Register callback for phone list updates."""
        self._callbacks.append(callback)

    def get_phones(self) -> list[Phone]:
        """Get list of discovered phones (excluding self)."""
        my_name = config.phone_name
        return [p for p in self.phones.values() if p.name != my_name]

    def _notify_update(self) -> None:
        """Notify callbacks of phone list update."""
        phones = self.get_phones()
        for callback in self._callbacks:
            try:
                callback(phones)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _start_mdns(self) -> None:
        """Start mDNS listener."""
        try:
            self._zeroconf = Zeroconf()
            self._mdns_listener = MDNSListener(self._merge_and_notify)
            self._browser = ServiceBrowser(
                self._zeroconf, SERVICE_TYPE, self._mdns_listener
            )
            logger.info("mDNS discovery started")
        except Exception as e:
            logger.error(f"Failed to start mDNS: {e}")

    def _register_service(self) -> None:
        """Register this phone as mDNS service."""
        if not self._zeroconf:
            return

        try:
            hostname = socket.gethostname()
            ip = self._get_local_ip()

            self._service_info = ServiceInfo(
                SERVICE_TYPE,
                f"{hostname}.{SERVICE_TYPE}",
                addresses=[socket.inet_aton(ip)],
                port=5000,
                properties={
                    "name": config.phone_name,
                    "extension": str(config.extension),
                    "version": "0.1.0",
                },
                server=f"{hostname}.local.",
            )

            self._zeroconf.register_service(self._service_info)
            logger.info(f"Registered mDNS service: {config.phone_name}")

        except Exception as e:
            logger.error(f"Failed to register mDNS service: {e}")

    def _start_tailscale_polling(self) -> None:
        """Start Tailscale API polling thread."""
        self._poll_thread = threading.Thread(target=self._poll_tailscale, daemon=True)
        self._poll_thread.start()

    def _poll_tailscale(self) -> None:
        """Poll Tailscale for tagged phones."""
        interval = config.get("discovery.poll_interval", 30)

        while self._running:
            try:
                phones = self._discover_tailscale()
                for phone in phones:
                    self.phones[phone.hostname] = phone
                self._notify_update()
            except Exception as e:
                logger.error(f"Tailscale discovery error: {e}")

            time.sleep(interval)

    def _discover_tailscale(self) -> list[Phone]:
        """Discover phones via Tailscale CLI."""
        phones = []

        try:
            # Get Tailscale status
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return phones

            status = json.loads(result.stdout)
            tag = config.get("network.tag", "redphone")

            for peer_id, peer in status.get("Peer", {}).items():
                # Check if peer has our tag
                tags = peer.get("Tags", []) or []
                if f"tag:{tag}" in tags:
                    # Get phone info via API
                    ip = peer.get("TailscaleIPs", [""])[0]
                    hostname = peer.get("HostName", "unknown")

                    phone = Phone(
                        name=peer.get("DisplayName", hostname),
                        hostname=hostname,
                        ip=ip,
                        extension=0,  # Will be fetched from phone API
                        status="online" if peer.get("Online") else "offline",
                        last_seen=datetime.now(),
                        source="tailscale",
                    )

                    # Try to get extension from phone API
                    try:
                        resp = requests.get(
                            f"http://{ip}:5000/api/info", timeout=2
                        )
                        if resp.ok:
                            info = resp.json()
                            phone.extension = info.get("extension", 0)
                            phone.name = info.get("name", phone.name)
                    except Exception:
                        pass

                    phones.append(phone)

        except Exception as e:
            logger.error(f"Tailscale status error: {e}")

        return phones

    def _merge_and_notify(self) -> None:
        """Merge mDNS discoveries and notify."""
        if self._mdns_listener:
            for name, phone in self._mdns_listener.phones.items():
                # mDNS takes precedence (more up-to-date)
                self.phones[name] = phone
        self._notify_update()

    def _get_local_ip(self) -> str:
        """Get local IP address."""
        try:
            # Try Tailscale IP first
            result = subprocess.run(
                ["tailscale", "ip", "-4"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

        # Fallback to regular IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"


# Global discovery service instance
discovery = DiscoveryService()
