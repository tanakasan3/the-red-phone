# ☎️ The Red Phone

A retro VoIP intercom system built on Raspberry Pi — because every secret lair needs one.

![Status: In Development](https://img.shields.io/badge/status-in%20development-yellow)

## What Is This?

The Red Phone is a self-contained VoIP phone built into a vintage telephone shell (or 3D-printed replica). Multiple Red Phones connect over a VPN mesh and can call each other with a simple touch interface — no phone company required.

Think of it as a private intercom system for your family, hackerspace, or secret organization.

## Features

- **Retro aesthetics** — Old phone shell or 3D print with real handset
- **Simple UI** — Big buttons on touchscreen, pick up handset to call
- **Mesh discovery** — All phones on the VPN see each other automatically
- **Quiet hours** — Confirmation required to call outside "daytime" 
- **Zero cloud** — All traffic stays on your VPN, runs your own PBX
- **Admin console** — Configure all phones from one place

## Hardware

| Component | Specification |
|-----------|---------------|
| Computer | Raspberry Pi 4B (4GB or 8GB) |
| Display | Official 7" Raspberry Pi Touchscreen (or compatible) |
| OS | Raspberry Pi OS (Bookworm) |
| Audio | USB headset (testing) or 3.5mm TRRS to handset |
| Network | WiFi or Ethernet + OpenVPN (Asuswrt-Merlin) |
| Enclosure | Vintage rotary phone shell or 3D printed |

### Audio Options

1. **Testing**: USB headset or 3.5mm headset with mic
2. **Production**: Wire vintage handset to 3.5mm TRRS jack
   - Tip: Left audio (speaker)
   - Ring 1: Right audio (speaker) 
   - Ring 2: Ground
   - Sleeve: Microphone

## Software Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    The Red Phone                        │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │   Web UI    │  │  Discovery   │  │    Config     │  │
│  │  (Kiosk)    │  │   Service    │  │   Service     │  │
│  │  Flask/Qt   │  │   (mDNS)     │  │   (REST)      │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬───────┘  │
│         │                │                   │          │
│         └────────────────┼───────────────────┘          │
│                          │                              │
│                   ┌──────▼──────┐                       │
│                   │   Asterisk  │                       │
│                   │     PBX     │                       │
│                   └──────┬──────┘                       │
│                          │                              │
├──────────────────────────┼──────────────────────────────┤
│                   ┌──────▼──────┐                       │
│                   │   OpenVPN   │                       │
│                   │   (tun0)    │                       │
│                   └─────────────┘                       │
└─────────────────────────────────────────────────────────┘
```

## User Flows

### First Boot (No Network)
1. Phone creates WiFi hotspot "RedPhone-XXXX"
2. Connect with another device, open captive portal
3. Select WiFi network, enter credentials
4. Phone connects and joins VPN

### Making a Call
1. Pick up handset → Screen shows "Who do you want to call?"
2. See list of discovered Red Phones (big buttons)
3. Tap a name:
   - **Daytime**: "Calling {name}..." → connects
   - **Night**: "Call {name} outside quiet hours?" → confirm/cancel
4. Other phone rings, screen flashes, shows caller name
5. They pick up → connected!

### Receiving a Call
1. Screen flashes, shows "Incoming: {caller}"
2. Ring sound plays through speaker
3. Pick up handset → connected
4. Hang up → call ends

## Directory Structure

```
the-red-phone/
├── README.md
├── docs/
│   ├── SETUP.md           # Installation guide
│   ├── HARDWARE.md        # Wiring and assembly
│   ├── ARCHITECTURE.md    # Technical deep-dive
│   └── ADMIN.md           # Administration guide
├── asterisk/
│   └── config/            # Asterisk configuration templates
├── redphone/
│   ├── __init__.py
│   ├── app.py             # Main Flask application
│   ├── discovery.py       # mDNS/UDP broadcast discovery
│   ├── sip.py             # SIP client wrapper
│   ├── config.py          # Configuration management
│   └── audio.py           # Audio device management
├── ui/
│   ├── templates/         # HTML templates (Jinja2)
│   ├── static/            # CSS, JS, images
│   └── sounds/            # Ring tones, dial tones
├── scripts/
│   ├── install.sh         # Full installation script
│   ├── setup-wifi.sh      # WiFi configuration
│   └── setup-kiosk.sh     # Kiosk mode setup
├── 3d-models/
│   └── phone-shell.scad   # OpenSCAD phone enclosure
├── requirements.txt
├── config.example.yaml
└── LICENSE
```

## Quick Start

```bash
# Clone and install
git clone https://github.com/tanakasan3/the-red-phone.git
cd the-red-phone
sudo ./scripts/install.sh

# Configure
cp config.example.yaml config.yaml
nano config.yaml

# Run
sudo systemctl start redphone
```

## Configuration

```yaml
# config.yaml
phone:
  name: "Kitchen"           # Display name for this phone
  extension: 101            # SIP extension number

network:
  vpn: openvpn              # VPN provider
  openvpn:
    config_file: /etc/redphone/vpn/client.ovpn
    auth_file: /etc/redphone/vpn/auth.txt

audio:
  input: "default"          # ALSA input device
  output: "default"         # ALSA output device
  ring_volume: 80           # Ring volume (0-100)

quiet_hours:
  enabled: true
  start: "22:00"            # Quiet time starts
  end: "08:00"              # Quiet time ends
  timezone: "Asia/Tokyo"

admin:
  enabled: false            # Enable admin interface
  password: ""              # Admin password (set on first run)
```

## Technology Choices

| Component | Choice | Why |
|-----------|--------|-----|
| PBX | Asterisk | Open source, runs on Pi, proven |
| VPN | OpenVPN | Works with Asuswrt-Merlin router |
| UI | Flask + Kiosk | Simple, works in browser |
| Discovery | mDNS + UDP broadcast | Local + VPN-wide discovery |
| Audio | ALSA/PulseAudio | Native Linux audio |

### Why Not 3CX?

3CX is commercial and cloud-dependent. Asterisk runs locally, is fully open source, and we control everything. For a private network of phones, we don't need 3CX's enterprise features.

## Roadmap

- [ ] Basic Flask UI with phone list
- [ ] Asterisk auto-configuration
- [ ] OpenVPN auto-connect on boot
- [ ] Handset off-hook detection (GPIO or audio)
- [ ] Ring/flash on incoming call
- [ ] Quiet hours with confirmation dialog
- [ ] WiFi setup captive portal
- [ ] Admin web interface
- [ ] 3D printable enclosure
- [ ] Hardware build guide

## Contributing

Pull requests welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - See [LICENSE](LICENSE)

---

*"This is a secure line."* ☎️⚡
