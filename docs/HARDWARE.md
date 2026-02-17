# Hardware Guide

## Bill of Materials

### Core Components

| Item | Model | Notes | Est. Cost |
|------|-------|-------|-----------|
| Raspberry Pi | 4B 4GB or 8GB | 4GB is sufficient | $55-75 |
| MicroSD Card | 32GB+ Class 10 | A2 rated preferred | $10 |
| Touchscreen | Official 7" RPi Display | 800x480, capacitive | $70 |
| Power Supply | Official 5.1V 3A USB-C | Or equivalent 15W+ | $10 |
| USB Sound Card | Any USB audio adapter | For testing | $10 |

### Phone Shell Options

**Option A: Vintage Phone**
- Old rotary or push-button phone (non-working OK)
- Remove internals, keep handset and shell
- Wire handset speaker/mic to audio jack

**Option B: 3D Printed**
- Print `3d-models/phone-shell.scad`
- ~200g PLA/PETG
- Buy/salvage a handset separately

### Audio Hardware

**For Testing:**
- Any USB headset with microphone
- Or 3.5mm headset with TRRS plug

**For Production:**
Rewire vintage handset to 3.5mm TRRS:
- Handset speaker → Tip + Ring1 (stereo L/R)
- Handset mic → Sleeve
- Common ground → Ring2

## Wiring Diagrams

### Handset to TRRS Jack

Most vintage handsets have 4 wires:
```
Handset Wire Colors (varies by model):
┌─────────────────────────────────────┐
│  Wire     │ Typical │ Connect to   │
├───────────┼─────────┼──────────────┤
│  Speaker+ │ Red     │ TRRS Tip     │
│  Speaker- │ Black   │ TRRS Ring2   │
│  Mic+     │ White   │ TRRS Sleeve  │
│  Mic-     │ Green   │ TRRS Ring2   │
└─────────────────────────────────────┘

TRRS Plug (3.5mm, 4-pole):
         ┌──┐
     Tip │  │ ← Left audio / Speaker+
   Ring1 │  │ ← Right audio (bridge to Tip)
   Ring2 │  │ ← Ground
  Sleeve │  │ ← Microphone
         └──┘
```

### Hook Switch Detection (GPIO)

The hook switch closes when the handset is lifted.

```
                    3.3V
                     │
                     ├──────┐
                     │      │
                   ┌─┴─┐    │
                   │10K│    │  Hook Switch
                   │ Ω │   ─┴─ (in cradle = open)
                   └─┬─┘   ─┬─
                     │      │
    GPIO17 ──────────┴──────┘
                     │
                    GND

GPIO17 = HIGH when handset lifted (switch closes)
GPIO17 = LOW when handset on cradle (switch open, pulled down)
```

**GPIO Pin Selection:**
- Use GPIO17 (physical pin 11) — no special function
- Configure as input with internal pull-down

### Raspberry Pi Pinout Reference

```
                    3.3V (1)  (2) 5V
            GPIO2/SDA (3)  (4) 5V
           GPIO3/SCL (5)  (6) GND
               GPIO4 (7)  (8) GPIO14/TX
                 GND (9) (10) GPIO15/RX
     Hook → GPIO17 (11) (12) GPIO18
              GPIO27 (13) (14) GND
              GPIO22 (15) (16) GPIO23
                3.3V (17) (18) GPIO24
              GPIO10 (19) (20) GND
               GPIO9 (21) (22) GPIO25
              GPIO11 (23) (24) GPIO8
                 GND (25) (26) GPIO7
               GPIO0 (27) (28) GPIO1
               GPIO5 (29) (30) GND
               GPIO6 (31) (32) GPIO12
              GPIO13 (33) (34) GND
              GPIO19 (35) (36) GPIO16
              GPIO26 (37) (38) GPIO20
                 GND (39) (40) GPIO21
```

## Assembly

### Step 1: Prepare the Display

1. Attach ribbon cable to Raspberry Pi DSI port
2. Connect display power to Pi GPIO (5V + GND)
3. Mount display in case/shell

### Step 2: Prepare the Handset

1. Open handset, identify speaker and mic wires
2. Measure continuity to confirm which is which:
   - Speaker: ~50-150Ω resistance
   - Mic: Very high or infinite (electret) or ~50-300Ω (carbon/dynamic)
3. Solder wires to TRRS breakout or jack
4. Test with `arecord` / `aplay`

### Step 3: Hook Switch (Optional)

1. Identify hook switch mechanism in phone base
2. Wire switch between GPIO17 and 3.3V
3. Add 10KΩ pull-down resistor GPIO17 to GND
4. Test with `gpio read 0` (wiringPi) or Python

### Step 4: Final Assembly

1. Mount Pi in phone base
2. Route cables (power, audio, display)
3. Secure with standoffs/screws
4. Test all functions before closing

## Testing

### Audio Test

```bash
# List audio devices
arecord -l
aplay -l

# Record 5 seconds from handset mic
arecord -D plughw:1,0 -d 5 -f cd test.wav

# Play back through handset speaker
aplay -D plughw:1,0 test.wav

# Real-time loopback test (speak into mic, hear in speaker)
arecord -D plughw:1,0 -f cd | aplay -D plughw:1,0
```

### GPIO Test

```bash
# Install GPIO tools
sudo apt install python3-rpi.gpio

# Test hook switch
python3 << 'EOF'
import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

print("Lift and replace handset to test...")
while True:
    if GPIO.input(17):
        print("Handset UP")
    else:
        print("Handset DOWN")
    time.sleep(0.5)
EOF
```

### Display Test

```bash
# Check display is detected
tvservice -s

# Test touch input
evtest /dev/input/event0
```

## Troubleshooting

### No Audio

1. Check ALSA device names: `arecord -l`
2. Verify USB audio is default: `cat /proc/asound/cards`
3. Check volume levels: `alsamixer`
4. Test with known-good headset

### Touch Not Working

1. Check I2C is enabled: `sudo raspi-config` → Interfaces
2. Look for touch device: `ls /dev/input/`
3. Install touch drivers if needed: `sudo apt install xserver-xorg-input-evdev`

### GPIO Not Responding

1. Verify pin number (BCM vs physical)
2. Check wiring continuity
3. Test with different GPIO pin
4. Check for shorts

### Display Upside Down

Add to `/boot/config.txt`:
```
lcd_rotate=2
```

## Parts Sources

- **Raspberry Pi**: Adafruit, SparkFun, PiShop
- **Vintage phones**: eBay, thrift stores, estate sales
- **TRRS jacks**: Amazon, AliExpress, electronic surplus
- **Enclosure**: 3D print or modify existing phone shell
