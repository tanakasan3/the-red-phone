# OpenVPN Setup for Asuswrt-Merlin

This guide covers setting up The Red Phone to connect to an OpenVPN server running on an Asuswrt-Merlin router.

## Prerequisites

- Asuswrt-Merlin router with OpenVPN server enabled
- Router firmware 384.x or newer recommended
- Access to router admin panel

## Router Configuration

### 1. Enable OpenVPN Server

1. Log into your router at `http://router.asus.com` or its IP
2. Go to **VPN** → **VPN Server** → **OpenVPN** tab
3. Enable **OpenVPN Server**
4. Configure:
   - **Server Port**: 1194 (or your choice)
   - **VPN Subnet**: 10.8.0.0 (default) 
   - **Client will use VPN to access**: LAN only (recommended) or LAN + Internet
   - **Push LAN to clients**: Yes
   - **Manage Client-Specific Options**: Yes
   - **Allow Client ↔ Client**: **Yes** (important for phone-to-phone calls!)

### 2. Create Client Certificate

1. In **Username and Password** section:
   - Add a username (e.g., `redphone-kitchen`)
   - Add a password
   - Click **+** to add

2. Repeat for each Red Phone (each needs unique credentials)

### 3. Export .ovpn File

1. Click **Export OpenVPN configuration file**
2. Save the `.ovpn` file

The file will look something like:
```
client
dev tun
proto udp
remote your-router-ip 1194
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
cipher AES-128-CBC
auth SHA256
comp-lzo
verb 3
<ca>
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
</ca>
<cert>
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
</cert>
<key>
-----BEGIN RSA PRIVATE KEY-----
...
-----END RSA PRIVATE KEY-----
</key>
```

## Red Phone Configuration

### Method 1: Manual Setup

1. Copy the `.ovpn` file to the phone:
```bash
scp client.ovpn <user>@redphone-kitchen:/tmp/
```

2. SSH into the Red Phone:
```bash
ssh <user>@redphone-kitchen
```

3. Move config to correct location:
```bash
sudo mv /tmp/client.ovpn /etc/redphone/vpn/client.ovpn
sudo chmod 600 /etc/redphone/vpn/client.ovpn
```

4. Create credentials file:
```bash
sudo nano /etc/redphone/vpn/auth.txt
```

Add two lines:
```
your-username
your-password
```

5. Secure the file:
```bash
sudo chmod 600 /etc/redphone/vpn/auth.txt
```

6. Restart the service:
```bash
sudo systemctl restart redphone
```

### Method 2: Web UI Setup

1. Access the phone's admin UI at `http://redphone-kitchen:5000/admin`
2. Enter admin password
3. Go to **VPN Settings**
4. Paste the contents of your `.ovpn` file
5. Enter username and password
6. Click **Save & Connect**

### Method 3: API Setup

```bash
# Set up credentials
curl -X POST http://redphone-kitchen:5000/api/vpn/setup \
  -H "Authorization: Bearer <admin-password>" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "redphone-kitchen",
    "password": "your-password",
    "ovpn_config": "<contents of .ovpn file>"
  }'

# Connect
curl -X POST http://redphone-kitchen:5000/api/vpn/connect \
  -H "Authorization: Bearer <admin-password>"
```

## Verifying Connection

### Check VPN Status

```bash
# Via API
curl http://redphone-kitchen:5000/api/vpn/status

# Response:
{
  "connected": true,
  "vpn_ip": "10.8.0.2",
  "provider": "openvpn"
}
```

### Check VPN Interface

```bash
ssh <user>@redphone-kitchen

# Check tun0 interface
ip addr show tun0

# Ping router's VPN IP
ping 10.8.0.1

# Ping another Red Phone
ping 10.8.0.3
```

### Check Logs

```bash
# OpenVPN log
sudo tail -f /var/log/redphone/openvpn.log

# Red Phone service log
journalctl -u redphone -f
```

## Discovery Over VPN

Red Phones discover each other using UDP broadcast on the VPN subnet.

Each phone:
1. Broadcasts its presence every 30 seconds on port 5199
2. Listens for announcements from other phones
3. Marks phones offline after 120 seconds of no announcement

**Note**: The router must allow client-to-client communication for discovery to work.

## Troubleshooting

### VPN Won't Connect

1. Check credentials are correct
2. Verify router is reachable: `ping <router-ip>`
3. Check OpenVPN log: `sudo cat /var/log/redphone/openvpn.log`
4. Ensure UDP port 1194 is open on router

### Phones Not Discovering Each Other

1. Verify both phones are connected to VPN: check `/api/vpn/status`
2. Ensure router has **Allow Client ↔ Client** enabled
3. Check UDP broadcast is working:
   ```bash
   # On phone A
   nc -ul 5199
   
   # On phone B (should see output on A)
   echo "test" | nc -u -b 10.8.0.255 5199
   ```

### Connection Drops

Check auto-reconnect is enabled in config:
```yaml
network:
  openvpn:
    auto_reconnect: true
    reconnect_delay: 10
```

## Multiple Locations

For phones at different locations (behind different NATs):

1. Use Dynamic DNS for your router
2. Set `remote your-ddns-hostname.asuscomm.com 1194` in .ovpn
3. Port forward UDP 1194 to router (if behind another NAT)

## Security Notes

- Keep `.ovpn` files secure — they contain private keys
- Use strong passwords for VPN authentication
- The `/etc/redphone/vpn/` directory is mode 700 (owner only)
- Consider revoking and regenerating certificates periodically
