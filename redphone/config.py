"""Configuration management for The Red Phone."""

import os
from pathlib import Path
from typing import Any, Optional

import yaml


DEFAULT_CONFIG = {
    "phone": {
        "name": "RedPhone",
        "extension": 100,
    },
    "network": {
        "vpn": "tailscale",  # openvpn | tailscale | none
        "tailscale": {
            "tailnet": "",
            "tag": "redphone",
        },
        "openvpn": {
            "config_file": "/etc/redphone/vpn/client.ovpn",
            "auth_file": "/etc/redphone/vpn/auth.txt",
            "auto_reconnect": True,
            "reconnect_delay": 10,
        },
    },
    "audio": {
        "input": "default",
        "output": "default",
        "ring_volume": 80,
        "call_volume": 70,
        "ringtone": "classic.wav",
    },
    "quiet_hours": {
        "enabled": True,
        "start": "22:00",
        "end": "08:00",
        "timezone": "UTC",
    },
    "discovery": {
        "mdns": True,
        "tailscale_api": True,
        "udp_broadcast": True,
        "udp_port": 5199,
        "announce_interval": 30,
        "phone_timeout": 120,
    },
    "ui": {
        "theme": "dark",
        "screen_timeout": 300,
        "show_clock": True,
    },
    "admin": {
        "enabled": False,
        "password": "",
        "serve_config": False,
    },
    "config": {
        "server": "",
        "pull_interval": 300,
    },
    "gpio": {
        "enabled": False,
        "hook_pin": 17,
        "hook_logic": "high_on_lift",
    },
    "logging": {
        "level": "INFO",
        "file": "/var/log/redphone/app.log",
    },
    "asterisk": {
        "ami_host": "127.0.0.1",
        "ami_port": 5038,
        "ami_user": "redphone",
        "ami_secret": "redphone",
        "rtp_start": 10000,
        "rtp_end": 20000,
    },
}

CONFIG_PATHS = [
    Path("/etc/redphone/config.yaml"),
    Path.home() / ".config/redphone/config.yaml",
    Path("config.yaml"),
]


class Config:
    """Configuration manager."""

    def __init__(self, config_path: Optional[Path] = None):
        self._config: dict[str, Any] = {}
        self._config_path: Optional[Path] = None
        self.load(config_path)

    def load(self, config_path: Optional[Path] = None) -> None:
        """Load configuration from file."""
        # Start with defaults
        self._config = DEFAULT_CONFIG.copy()

        # Find config file
        if config_path and config_path.exists():
            self._config_path = config_path
        else:
            for path in CONFIG_PATHS:
                if path.exists():
                    self._config_path = path
                    break

        # Load and merge
        if self._config_path:
            with open(self._config_path) as f:
                user_config = yaml.safe_load(f) or {}
            self._merge_config(self._config, user_config)

    def _merge_config(self, base: dict, override: dict) -> None:
        """Deep merge override into base."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value

    def save(self) -> None:
        """Save current configuration to file."""
        if not self._config_path:
            self._config_path = CONFIG_PATHS[0]

        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w") as f:
            yaml.dump(self._config, f, default_flow_style=False)

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot-notation key (e.g., 'phone.name')."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """Set config value by dot-notation key."""
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    @property
    def phone_name(self) -> str:
        return self.get("phone.name", "RedPhone")

    @property
    def extension(self) -> int:
        return self.get("phone.extension", 100)

    @property
    def tailnet(self) -> str:
        return self.get("network.tailnet", "")

    @property
    def quiet_hours_enabled(self) -> bool:
        return self.get("quiet_hours.enabled", True)

    @property
    def quiet_hours_start(self) -> str:
        return self.get("quiet_hours.start", "22:00")

    @property
    def quiet_hours_end(self) -> str:
        return self.get("quiet_hours.end", "08:00")

    @property
    def timezone(self) -> str:
        return self.get("quiet_hours.timezone", "UTC")

    def to_dict(self) -> dict[str, Any]:
        """Return full configuration as dictionary."""
        return self._config.copy()


# Global config instance
config = Config()
