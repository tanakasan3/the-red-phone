"""GPIO hook switch detection for Raspberry Pi."""

import logging
from typing import Callable, Optional

from .config import config

logger = logging.getLogger(__name__)


class HookDetector:
    """Detect handset hook state via GPIO."""

    def __init__(self, callback: Optional[Callable[[bool], None]] = None):
        self.callback = callback
        self._gpio = None
        self._pin = config.get("gpio.hook_pin", 17)
        self._high_on_lift = config.get("gpio.hook_logic", "high_on_lift") == "high_on_lift"
        self._lifted = False

    def start(self) -> bool:
        """Start hook detection."""
        if not config.get("gpio.enabled", False):
            logger.info("GPIO hook detection disabled")
            return False

        try:
            import RPi.GPIO as GPIO

            self._gpio = GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            # Setup pin with pull-down resistor
            GPIO.setup(self._pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

            # Add edge detection
            GPIO.add_event_detect(
                self._pin,
                GPIO.BOTH,
                callback=self._handle_edge,
                bouncetime=100,
            )

            logger.info(f"GPIO hook detection started on pin {self._pin}")
            return True

        except ImportError:
            logger.warning("RPi.GPIO not available (not running on Raspberry Pi?)")
            return False
        except Exception as e:
            logger.error(f"GPIO setup error: {e}")
            return False

    def stop(self) -> None:
        """Stop hook detection."""
        if self._gpio:
            try:
                self._gpio.remove_event_detect(self._pin)
                self._gpio.cleanup(self._pin)
            except Exception as e:
                logger.error(f"GPIO cleanup error: {e}")
            self._gpio = None

    def is_lifted(self) -> bool:
        """Check if handset is currently lifted."""
        if not self._gpio:
            return False

        state = self._gpio.input(self._pin)
        return state == 1 if self._high_on_lift else state == 0

    def _handle_edge(self, channel: int) -> None:
        """Handle GPIO edge event."""
        lifted = self.is_lifted()

        if lifted != self._lifted:
            self._lifted = lifted
            logger.debug(f"Hook state changed: {'lifted' if lifted else 'replaced'}")

            if self.callback:
                self.callback(lifted)


# Alternative using gpiozero (simpler API)
class HookDetectorZero:
    """Hook detection using gpiozero library."""

    def __init__(self, callback: Optional[Callable[[bool], None]] = None):
        self.callback = callback
        self._button = None
        self._pin = config.get("gpio.hook_pin", 17)
        self._high_on_lift = config.get("gpio.hook_logic", "high_on_lift") == "high_on_lift"

    def start(self) -> bool:
        """Start hook detection."""
        if not config.get("gpio.enabled", False):
            logger.info("GPIO hook detection disabled")
            return False

        try:
            from gpiozero import Button

            # Hook switch acts like a button
            self._button = Button(
                self._pin,
                pull_up=not self._high_on_lift,
                bounce_time=0.1,
            )

            if self.callback:
                if self._high_on_lift:
                    self._button.when_pressed = lambda: self.callback(True)
                    self._button.when_released = lambda: self.callback(False)
                else:
                    self._button.when_pressed = lambda: self.callback(False)
                    self._button.when_released = lambda: self.callback(True)

            logger.info(f"gpiozero hook detection started on pin {self._pin}")
            return True

        except ImportError:
            logger.warning("gpiozero not available")
            return False
        except Exception as e:
            logger.error(f"gpiozero setup error: {e}")
            return False

    def stop(self) -> None:
        """Stop hook detection."""
        if self._button:
            self._button.close()
            self._button = None

    def is_lifted(self) -> bool:
        """Check if handset is currently lifted."""
        if not self._button:
            return False

        if self._high_on_lift:
            return self._button.is_pressed
        else:
            return not self._button.is_pressed
