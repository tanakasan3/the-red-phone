# Architecture

## System Overview

The Red Phone is built on four core components:

1. **Asterisk PBX** — Handles all SIP/VoIP signaling and audio
2. **Discovery Service** — Finds other Red Phones on the VPN
3. **Web UI** — Touchscreen interface in kiosk mode
4. **Config Service** — REST API for phone configuration

## Component Details

### Asterisk PBX

We use Asterisk as a local PBX on each phone. Each phone is both a SIP client and can receive calls.

```
Asterisk Configuration:
├── sip.conf          # SIP peer definitions (auto-generated)
├── extensions.conf   # Dial plan
├── rtp.conf          # RTP ports (audio streaming)
└── manager.conf      # AMI for programmatic control
```

**Why local Asterisk instead of central?**
- Works offline (LAN calls still work)
- No single point of failure
- Each phone is sovereign

### Discovery Service

Multi-tier discovery based on VPN type:

1. **mDNS (local network)** — `_redphone._tcp.local`
   - Works on LAN even without internet
   - Immediate discovery (~1 second)
   - Always enabled

2. **Tailscale API** (when `vpn: tailscale`)
   - Queries Tailscale for machines with `tag:redphone`
   - Polls every 30 seconds
   - Works across any network

3. **UDP Broadcast** (when `vpn: openvpn` or for LAN)
   - Each phone announces presence every 30 seconds
   - Broadcasts on port 5199
   - Works across OpenVPN tunnel (requires client-to-client)

```python
# Discovery data structure
{
    "phones": [
        {
            "name": "Kitchen",
            "hostname": "kitchen-phone",
            "ip": "100.64.1.10",        # Tailscale IP
            "extension": 101,
            "status": "online",
            "last_seen": "2026-02-17T09:00:00Z"
        }
    ]
}
```

### Web UI (Kiosk)

Flask app running in Chromium kiosk mode.

**Pages:**
- `/` — Main screen (phone list)
- `/call/<extension>` — Calling screen
- `/incoming` — Incoming call screen
- `/setup` — WiFi setup (captive portal mode)
- `/admin` — Admin interface (protected)

**State Machine:**

```
┌──────────┐
│   IDLE   │◄─────────────────┐
└────┬─────┘                  │
     │ pick up handset        │ hang up
     ▼                        │
┌──────────┐                  │
│ DIALING  │──────────────────┤
└────┬─────┘ timeout/cancel   │
     │ select contact         │
     ▼                        │
┌──────────┐                  │
│ CALLING  │──────────────────┤
└────┬─────┘ no answer/busy   │
     │ answered               │
     ▼                        │
┌──────────┐                  │
│ IN_CALL  │──────────────────┘
└──────────┘
```

**Incoming calls:**
```
┌──────────┐
│   IDLE   │
└────┬─────┘
     │ incoming call
     ▼
┌──────────┐
│ RINGING  │──────┐
└────┬─────┘      │ timeout/caller hangs up
     │ pick up    │
     ▼            ▼
┌──────────┐  ┌──────────┐
│ IN_CALL  │  │   IDLE   │
└──────────┘  └──────────┘
```

### Config Service

REST API for remote administration.

**Endpoints:**
- `GET /api/config` — Get current config
- `PUT /api/config` — Update config (admin only)
- `GET /api/status` — Phone status (calls, uptime)
- `POST /api/restart` — Restart services

**Authentication:**
- Local requests (same machine): no auth
- Remote requests: Bearer token or admin password

## Audio Pipeline

```
Handset Microphone
       │
       ▼
   ALSA Input ──► Asterisk ──► RTP ──► Network
                     │
                     ▼
   ALSA Output ◄── Asterisk ◄── RTP ◄── Network
       │
       ▼
Handset Speaker
```

**Hook Detection:**

Option 1: **GPIO** — Physical switch in handset cradle
- GPIO pin goes HIGH when handset lifted
- Requires wiring modification

Option 2: **Audio detection** — Monitor mic input level
- Sudden increase in ambient noise = handset lifted
- Less reliable but no hardware mods

## Network Architecture

### Option 1: Tailscale (Recommended)

```
┌─────────────────────────────────────────────────────────┐
│                     Internet                            │
└─────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
    ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐
    │ Tailscale │   │ Tailscale │   │ Tailscale │
    │  DERP     │   │  DERP     │   │  DERP     │
    └───────────┘   └───────────┘   └───────────┘
          │               │               │
    ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐
    │ Red Phone │◄─►│ Red Phone │◄─►│ Red Phone │
    │ Kitchen   │   │ Bedroom   │   │ Office    │
    └───────────┘   └───────────┘   └───────────┘
```

Tailscale handles NAT traversal automatically. Phones discover each other via Tailscale API (tagged with `tag:redphone`).

### Option 2: OpenVPN (Asuswrt-Merlin)

```
                     ┌─────────────────────┐
                     │   Asuswrt-Merlin    │
                     │   Router + OpenVPN  │
                     │   Server (10.8.0.1) │
                     └──────────┬──────────┘
                                │
            ┌───────────────────┼───────────────────┐
            │ VPN Tunnel        │ VPN Tunnel        │ VPN Tunnel
            │                   │                   │
      ┌─────▼─────┐       ┌─────▼─────┐       ┌─────▼─────┐
      │ Red Phone │       │ Red Phone │       │ Red Phone │
      │ Kitchen   │◄─────►│ Bedroom   │◄─────►│ Office    │
      │ 10.8.0.2  │ UDP   │ 10.8.0.3  │ UDP   │ 10.8.0.4  │
      └───────────┘ Bcast └───────────┘ Bcast └───────────┘
```

All phones connect to the router's OpenVPN server. The router's "Allow Client ↔ Client" setting enables direct communication. Discovery via UDP broadcast on port 5199.

## Security Model

1. **VPN-only** — All traffic over encrypted VPN tunnel
2. **No external ports** — Nothing exposed to internet
3. **Encryption**:
   - Tailscale: WireGuard protocol, automatic key exchange
   - OpenVPN: TLS certificates from router
4. **Admin auth** — Password-protected admin API
5. **Credentials protected** — VPN auth files mode 600

## File Locations

| Path | Purpose |
|------|---------|
| `/opt/redphone/` | Application code |
| `/etc/redphone/` | Configuration |
| `/var/lib/redphone/` | State (discovered phones, call history) |
| `/var/log/redphone/` | Logs |
| `/etc/asterisk/` | Asterisk configuration |

## Boot Sequence

1. **systemd** starts `redphone.service`
2. Check network connectivity
3. If no network:
   - Start WiFi hotspot (`RedPhone-XXXX`)
   - Start captive portal on port 80
   - Wait for WiFi configuration
4. If network available:
   - If `vpn: openvpn`: Start OpenVPN, wait for tunnel
   - If `vpn: tailscale`: Verify Tailscale is connected
   - Start Asterisk
   - Start discovery service (mDNS + Tailscale API / UDP)
   - Start Flask app in kiosk mode

## Dependencies

```
System packages:
- asterisk
- python3
- chromium-browser
- pulseaudio / pipewire
- tailscale (if using Tailscale VPN)
- openvpn (if using OpenVPN)
- hostapd (WiFi hotspot)
- dnsmasq (DHCP for hotspot)

Python packages:
- flask
- pjsua2 (SIP client)
- zeroconf (mDNS)
- pyyaml
- requests
```
