"""Phone discovery service using mDNS, Tailscale API, and UDP broadcast."""

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
UDP_MAGIC = b"REDPHONE"


@dataclass
class Phone:
    """Discovered phone information."""

    name: str
    hostname: str
    ip: str
    extension: int
    status: str = "online"
    last_seen: datetime = field(default_factory=datetime.now)
    source: str = "unknown"  # mdns, udp

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


class TailscaleDiscovery:
    """Tailscale API discovery for mesh VPN networks."""

    def __init__(self, on_phone_discovered: Callable[[Phone], None]):
        self.on_phone_discovered = on_phone_discovered
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start Tailscale API polling."""
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll, daemon=True)
        self._poll_thread.start()
        logger.info("Tailscale API discovery started")

    def stop(self) -> None:
        """Stop Tailscale API polling."""
        self._running = False

    def _poll(self) -> None:
        """Poll Tailscale for tagged phones."""
        interval = config.get("discovery.announce_interval", 30)

        while self._running:
            try:
                phones = self._discover()
                for phone in phones:
                    self.on_phone_discovered(phone)
            except Exception as e:
                logger.error(f"Tailscale discovery error: {e}")

            time.sleep(interval)

    def _discover(self) -> list[Phone]:
        """Query Tailscale for phones with our tag."""
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
            tag = config.get("network.tailscale.tag", "redphone")

            for peer_id, peer in status.get("Peer", {}).items():
                # Check if peer has our tag
                tags = peer.get("Tags", []) or []
                if f"tag:{tag}" in tags:
                    ip = peer.get("TailscaleIPs", [""])[0]
                    hostname = peer.get("HostName", "unknown")

                    phone = Phone(
                        name=peer.get("DisplayName", hostname),
                        hostname=hostname,
                        ip=ip,
                        extension=0,
                        status="online" if peer.get("Online") else "offline",
                        last_seen=datetime.now(),
                        source="tailscale",
                    )

                    # Try to get extension from phone API
                    try:
                        resp = requests.get(f"http://{ip}:5000/api/info", timeout=2)
                        if resp.ok:
                            info = resp.json()
                            phone.extension = info.get("extension", 0)
                            phone.name = info.get("name", phone.name)
                    except Exception:
                        pass

                    phones.append(phone)

        except FileNotFoundError:
            logger.debug("Tailscale CLI not installed")
        except Exception as e:
            logger.error(f"Tailscale status error: {e}")

        return phones


class UDPDiscovery:
    """UDP broadcast discovery for VPN networks."""

    def __init__(self, on_phone_discovered: Callable[[Phone], None]):
        self.on_phone_discovered = on_phone_discovered
        self._running = False
        self._listen_thread: Optional[threading.Thread] = None
        self._announce_thread: Optional[threading.Thread] = None
        self._port = config.get("discovery.udp_port", 5199)

    def start(self) -> None:
        """Start UDP discovery (listen and announce)."""
        self._running = True
        
        # Start listener
        self._listen_thread = threading.Thread(target=self._listen, daemon=True)
        self._listen_thread.start()
        
        # Start announcer
        self._announce_thread = threading.Thread(target=self._announce, daemon=True)
        self._announce_thread.start()
        
        logger.info(f"UDP discovery started on port {self._port}")

    def stop(self) -> None:
        """Stop UDP discovery."""
        self._running = False

    def _listen(self) -> None:
        """Listen for discovery announcements."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("", self._port))
            sock.settimeout(1.0)
            
            while self._running:
                try:
                    data, addr = sock.recvfrom(1024)
                    self._handle_announcement(data, addr[0])
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"UDP receive error: {e}")
                    
            sock.close()
            
        except Exception as e:
            logger.error(f"UDP listener error: {e}")

    def _handle_announcement(self, data: bytes, sender_ip: str) -> None:
        """Process received announcement."""
        try:
            # Check magic header
            if not data.startswith(UDP_MAGIC):
                return
            
            # Parse JSON payload
            payload = json.loads(data[len(UDP_MAGIC):].decode())
            
            # Ignore our own announcements
            if payload.get("extension") == config.extension:
                return
            
            phone = Phone(
                name=payload.get("name", "Unknown"),
                hostname=payload.get("hostname", sender_ip),
                ip=sender_ip,
                extension=payload.get("extension", 0),
                status="online",
                last_seen=datetime.now(),
                source="udp",
            )
            
            logger.debug(f"Received announcement from {phone.name} ({sender_ip})")
            self.on_phone_discovered(phone)
            
        except Exception as e:
            logger.error(f"Error parsing announcement: {e}")

    def _announce(self) -> None:
        """Periodically announce presence."""
        interval = config.get("discovery.announce_interval", 30)
        
        while self._running:
            try:
                self._send_announcement()
            except Exception as e:
                logger.error(f"Announcement error: {e}")
            
            time.sleep(interval)

    def _send_announcement(self) -> None:
        """Send presence announcement via broadcast."""
        payload = {
            "name": config.phone_name,
            "hostname": socket.gethostname(),
            "extension": config.extension,
            "version": "0.1.0",
        }
        
        message = UDP_MAGIC + json.dumps(payload).encode()
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            # Broadcast on all interfaces
            sock.sendto(message, ("<broadcast>", self._port))
            
            # Also send to VPN subnet if connected
            vpn_ip = self._get_vpn_ip()
            if vpn_ip:
                # Send to VPN broadcast (assuming /24 subnet)
                vpn_broadcast = ".".join(vpn_ip.split(".")[:3]) + ".255"
                sock.sendto(message, (vpn_broadcast, self._port))
            
            sock.close()
            
        except Exception as e:
            logger.error(f"Broadcast error: {e}")

    def _get_vpn_ip(self) -> Optional[str]:
        """Get VPN tunnel IP."""
        try:
            import subprocess
            result = subprocess.run(
                ["ip", "-4", "addr", "show", "tun0"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "inet " in line:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            return parts[1].split("/")[0]
            return None
        except Exception:
            return None


class DiscoveryService:
    """Phone discovery service combining mDNS, Tailscale API, and UDP broadcast."""

    def __init__(self):
        self.phones: dict[str, Phone] = {}
        self._zeroconf: Optional[Zeroconf] = None
        self._browser: Optional[ServiceBrowser] = None
        self._mdns_listener: Optional[MDNSListener] = None
        self._tailscale_discovery: Optional[TailscaleDiscovery] = None
        self._udp_discovery: Optional[UDPDiscovery] = None
        self._running = False
        self._cleanup_thread: Optional[threading.Thread] = None
        self._service_info: Optional[ServiceInfo] = None
        self._callbacks: list[Callable[[list[Phone]], None]] = []

    def start(self) -> None:
        """Start discovery services."""
        self._running = True
        vpn_type = config.get("network.vpn", "tailscale")

        # Start mDNS (always, for local network)
        if config.get("discovery.mdns", True):
            self._start_mdns()

        # Start Tailscale API discovery (when using Tailscale VPN)
        if vpn_type == "tailscale" and config.get("discovery.tailscale_api", True):
            self._start_tailscale()

        # Start UDP broadcast discovery (when using OpenVPN or for LAN)
        if config.get("discovery.udp_broadcast", True):
            self._start_udp()

        # Start cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_stale, daemon=True)
        self._cleanup_thread.start()

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

        if self._tailscale_discovery:
            self._tailscale_discovery.stop()

        if self._udp_discovery:
            self._udp_discovery.stop()

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

    def _start_tailscale(self) -> None:
        """Start Tailscale API discovery."""
        self._tailscale_discovery = TailscaleDiscovery(self._on_phone_discovered)
        self._tailscale_discovery.start()

    def _start_udp(self) -> None:
        """Start UDP broadcast discovery."""
        self._udp_discovery = UDPDiscovery(self._on_phone_discovered)
        self._udp_discovery.start()

    def _on_phone_discovered(self, phone: Phone) -> None:
        """Handle phone discovered via Tailscale or UDP."""
        key = f"{phone.hostname}_{phone.extension}"
        existing = self.phones.get(key)
        
        # Update if new or more recent
        if not existing or phone.last_seen > existing.last_seen:
            self.phones[key] = phone
            self._notify_update()

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

    def _cleanup_stale(self) -> None:
        """Remove phones that haven't been seen recently."""
        timeout = config.get("discovery.phone_timeout", 120)
        
        while self._running:
            now = datetime.now()
            stale = []
            
            for key, phone in self.phones.items():
                age = (now - phone.last_seen).total_seconds()
                if age > timeout:
                    stale.append(key)
            
            if stale:
                for key in stale:
                    phone = self.phones.pop(key, None)
                    if phone:
                        logger.info(f"Phone offline: {phone.name}")
                self._notify_update()
            
            time.sleep(30)

    def _merge_and_notify(self) -> None:
        """Merge mDNS discoveries and notify."""
        if self._mdns_listener:
            for name, phone in self._mdns_listener.phones.items():
                # mDNS takes precedence (more up-to-date)
                self.phones[name] = phone
        self._notify_update()

    def _get_local_ip(self) -> str:
        """Get local IP address (prefer VPN)."""
        # Try VPN IP first
        try:
            import subprocess
            result = subprocess.run(
                ["ip", "-4", "addr", "show", "tun0"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "inet " in line:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            return parts[1].split("/")[0]
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
