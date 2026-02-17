"""Audio device management."""

import logging
import subprocess
from typing import Optional

from .config import config

logger = logging.getLogger(__name__)


def list_audio_devices() -> dict:
    """List available audio input and output devices."""
    devices = {"inputs": [], "outputs": []}

    try:
        # List input devices
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.split("\n"):
            if line.startswith("card"):
                devices["inputs"].append(line)

        # List output devices
        result = subprocess.run(
            ["aplay", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.split("\n"):
            if line.startswith("card"):
                devices["outputs"].append(line)

    except Exception as e:
        logger.error(f"Error listing audio devices: {e}")

    return devices


def set_volume(level: int, device: str = "Master") -> bool:
    """Set audio volume (0-100)."""
    level = max(0, min(100, level))
    try:
        subprocess.run(
            ["amixer", "set", device, f"{level}%"],
            capture_output=True,
            timeout=5,
        )
        return True
    except Exception as e:
        logger.error(f"Error setting volume: {e}")
        return False


def play_sound(filename: str, device: Optional[str] = None) -> bool:
    """Play a sound file."""
    try:
        cmd = ["aplay"]
        if device:
            cmd.extend(["-D", device])
        cmd.append(filename)

        subprocess.run(cmd, capture_output=True, timeout=30)
        return True
    except Exception as e:
        logger.error(f"Error playing sound: {e}")
        return False


def play_ringtone() -> bool:
    """Play the configured ringtone."""
    import os
    ringtone = config.get("audio.ringtone", "classic.wav")
    sound_dir = os.path.join(os.path.dirname(__file__), "..", "ui", "sounds")
    filepath = os.path.join(sound_dir, ringtone)

    if not os.path.exists(filepath):
        logger.warning(f"Ringtone not found: {filepath}")
        return False

    return play_sound(filepath)


class AudioMonitor:
    """Monitor audio input for hook detection (alternative to GPIO)."""

    def __init__(self, threshold: float = 0.1, callback=None):
        self.threshold = threshold
        self.callback = callback
        self._running = False
        self._lifted = False

    def start(self):
        """Start audio monitoring in background."""
        import threading
        self._running = True
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop audio monitoring."""
        self._running = False

    def _monitor(self):
        """Monitor audio levels."""
        try:
            import pyaudio
            import struct
            import math

            pa = pyaudio.PyAudio()

            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=1024,
            )

            while self._running:
                data = stream.read(1024, exception_on_overflow=False)
                samples = struct.unpack(f"{len(data)//2}h", data)
                rms = math.sqrt(sum(s**2 for s in samples) / len(samples))
                level = rms / 32768.0  # Normalize

                was_lifted = self._lifted
                self._lifted = level > self.threshold

                if self._lifted != was_lifted and self.callback:
                    self.callback(self._lifted)

            stream.close()
            pa.terminate()

        except Exception as e:
            logger.error(f"Audio monitoring error: {e}")
