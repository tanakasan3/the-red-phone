# Setup Guide

## Prerequisites

- Raspberry Pi 4B (4GB or 8GB)
- MicroSD card (32GB+)
- Raspberry Pi OS Bookworm (64-bit recommended)
- Internet connection for initial setup
- OpenVPN server on Asuswrt-Merlin router (see [OPENVPN.md](OPENVPN.md))

## Step 1: Flash Raspberry Pi OS

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Flash **Raspberry Pi OS (64-bit)** to SD card
3. In Imager settings (gear icon):
   - Enable SSH
   - Set hostname: `redphone-kitchen` (or your chosen name)
   - Set username/password
   - Configure WiFi (optional)

## Step 2: Initial Boot

```bash
# SSH into the Pi (use your configured username)
ssh <your-user>@redphone-kitchen.local

# Update system
sudo apt update && sudo apt upgrade -y

# Reboot
sudo reboot
```

## Step 3: Set Up OpenVPN

You'll need the `.ovpn` file from your Asuswrt-Merlin router. See [OPENVPN.md](OPENVPN.md) for router setup.

```bash
# Create VPN directory
sudo mkdir -p /etc/redphone/vpn
sudo chmod 700 /etc/redphone/vpn

# Copy your .ovpn file
sudo cp /path/to/client.ovpn /etc/redphone/vpn/client.ovpn

# Create credentials file
sudo nano /etc/redphone/vpn/auth.txt
```

Add your VPN username on line 1, password on line 2:
```
your-vpn-username
your-vpn-password
```

Secure the files:
```bash
sudo chmod 600 /etc/redphone/vpn/*
```

**Important:** Enable "Allow Client ↔ Client" on your router for phone-to-phone discovery.

## Step 4: Install The Red Phone

```bash
# Clone repository
cd /opt
sudo git clone https://github.com/tanakasan3/the-red-phone.git redphone
sudo chown -R $USER:$USER /opt/redphone

# Run installer
cd /opt/redphone
sudo ./scripts/install.sh
```

The installer will:
1. Install system dependencies (Asterisk, Python, etc.)
2. Set up Python virtual environment
3. Install Python packages
4. Create systemd services
5. Configure Asterisk
6. Set up kiosk mode

## Step 5: Configure

```bash
# Copy example config
sudo cp /opt/redphone/config.example.yaml /etc/redphone/config.yaml

# Edit configuration
sudo nano /etc/redphone/config.yaml
```

Essential settings:
```yaml
phone:
  name: "Kitchen"        # Friendly name shown to other phones
  extension: 101         # Unique SIP extension (101-199)

network:
  vpn: tailscale
  tailnet: your-tailnet.ts.net

quiet_hours:
  start: "22:00"
  end: "08:00"
  timezone: "Asia/Tokyo"
```

## Step 6: Start Services

```bash
# Enable and start
sudo systemctl enable redphone
sudo systemctl start redphone

# Check status
sudo systemctl status redphone

# View logs
journalctl -u redphone -f
```

## Step 7: Kiosk Mode

The installer sets up automatic login and Chromium kiosk mode.

To manually test:
```bash
# Set display
export DISPLAY=:0

# Run kiosk
chromium-browser --kiosk --noerrdialogs --disable-infobars http://localhost:5000
```

## Step 8: Test

1. Open browser to `http://redphone-kitchen.local:5000`
2. You should see the phone list (empty initially)
3. Set up a second Red Phone on the same Tailscale network
4. Phones should discover each other within ~30 seconds
5. Test a call!

## Verification Checklist

- [ ] OpenVPN connected: `ip addr show tun0`
- [ ] VPN IP assigned: `curl http://localhost:5000/api/vpn/status`
- [ ] Asterisk running: `sudo systemctl status asterisk`
- [ ] Red Phone service running: `sudo systemctl status redphone`
- [ ] Web UI accessible: `curl http://localhost:5000`
- [ ] Audio working: `arecord -d 3 test.wav && aplay test.wav`
- [ ] Other phones discovered: check web UI

## Updating

```bash
cd /opt/redphone
sudo git pull
sudo ./scripts/install.sh --update
sudo systemctl restart redphone
```

## Uninstalling

```bash
sudo systemctl stop redphone
sudo systemctl disable redphone
sudo rm /etc/systemd/system/redphone.service
sudo rm -rf /opt/redphone
sudo rm -rf /etc/redphone
```

## Troubleshooting

### Service won't start

```bash
# Check logs
journalctl -u redphone -n 50

# Test manually
cd /opt/redphone
source venv/bin/activate
python -m redphone.app
```

### Phones not discovering each other

1. Verify both connected to VPN: `curl http://localhost:5000/api/vpn/status`
2. Check router has "Allow Client ↔ Client" enabled
3. Verify mDNS: `avahi-browse -a | grep redphone`
4. Test UDP broadcast between phones (see [OPENVPN.md](OPENVPN.md#troubleshooting))
5. Check firewall: `sudo ufw status`

### Audio issues

See [HARDWARE.md](HARDWARE.md#troubleshooting)

### Display issues

```bash
# Check display
tvservice -s

# Restart display manager
sudo systemctl restart lightdm
```
