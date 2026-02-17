# Administration Guide

## Admin Interface

Enable admin mode in `/etc/redphone/config.yaml`:

```yaml
admin:
  enabled: true
  password: "your-secure-password"
```

Access at `http://<phone-ip>:5000/admin`

## Managing Multiple Phones

### Central Configuration

One phone can act as a configuration server. Other phones pull config from it.

In config server's `config.yaml`:
```yaml
admin:
  enabled: true
  serve_config: true
```

In client phones' `config.yaml`:
```yaml
config:
  server: "http://admin-phone.ts.net:5000"
  pull_interval: 300  # seconds
```

### REST API

All endpoints require admin authentication:
```bash
curl -H "Authorization: Bearer <password>" http://phone.ts.net:5000/api/...
```

**Get phone status:**
```bash
curl http://phone.ts.net:5000/api/status
```
```json
{
  "name": "Kitchen",
  "extension": 101,
  "status": "idle",
  "uptime": 86400,
  "calls_today": 5,
  "discovered_phones": 3
}
```

**Get configuration:**
```bash
curl http://phone.ts.net:5000/api/config
```

**Update configuration:**
```bash
curl -X PUT -H "Content-Type: application/json" \
  -d '{"quiet_hours": {"start": "23:00"}}' \
  http://phone.ts.net:5000/api/config
```

**List discovered phones:**
```bash
curl http://phone.ts.net:5000/api/phones
```
```json
{
  "phones": [
    {"name": "Living Room", "extension": 102, "status": "online"},
    {"name": "Bedroom", "extension": 103, "status": "offline"}
  ]
}
```

**Restart services:**
```bash
curl -X POST http://phone.ts.net:5000/api/restart
```

## Quiet Hours

Quiet hours prevent accidental late-night calls. When enabled:
- Calls during quiet hours show a confirmation dialog
- Incoming calls still ring (emergencies happen)

Configure per-phone:
```yaml
quiet_hours:
  enabled: true
  start: "22:00"
  end: "08:00"
  timezone: "Asia/Tokyo"
```

Or configure globally via admin server.

## Extension Assignment

Each phone needs a unique extension number (100-999).

Suggested scheme:
- 100: Reserved (voicemail, if implemented)
- 101-199: Personal phones
- 201-299: Office phones
- 301-399: Common areas

## Network Configuration

### Firewall Rules

Red Phones need these ports open **only on Tailscale interface**:

| Port | Protocol | Purpose |
|------|----------|---------|
| 5000 | TCP | Web UI & API |
| 5060 | UDP | SIP signaling |
| 10000-20000 | UDP | RTP audio |
| 5353 | UDP | mDNS discovery |

Example UFW rules:
```bash
# Allow on tailscale0 interface only
sudo ufw allow in on tailscale0 to any port 5000 proto tcp
sudo ufw allow in on tailscale0 to any port 5060 proto udp
sudo ufw allow in on tailscale0 to any port 10000:20000 proto udp
sudo ufw allow in on tailscale0 to any port 5353 proto udp
```

### Tailscale ACLs

In Tailscale admin console, you can restrict which devices can reach Red Phones:

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["tag:redphone"],
      "dst": ["tag:redphone:*"]
    }
  ]
}
```

## Logs

| Log | Location |
|-----|----------|
| Red Phone | `/var/log/redphone/app.log` |
| Asterisk | `/var/log/asterisk/` |
| System | `journalctl -u redphone` |

**Log rotation** is configured automatically.

Enable debug logging:
```yaml
logging:
  level: DEBUG
```

## Backup & Restore

### Backup

```bash
# Config and state
sudo tar -czvf redphone-backup.tar.gz \
  /etc/redphone/ \
  /var/lib/redphone/

# Copy off the Pi (replace <user> with your username)
scp <user>@phone:~/redphone-backup.tar.gz .
```

### Restore

```bash
scp redphone-backup.tar.gz <user>@newphone:~/
ssh <user>@newphone

sudo tar -xzvf redphone-backup.tar.gz -C /
sudo systemctl restart redphone
```

## Monitoring

### Health Check Endpoint

```bash
curl http://phone.ts.net:5000/health
```
```json
{
  "status": "healthy",
  "asterisk": "running",
  "tailscale": "connected",
  "discovery": "active"
}
```

### Prometheus Metrics (Optional)

Enable metrics exporter:
```yaml
metrics:
  enabled: true
  port: 9100
```

Metrics available:
- `redphone_calls_total` — Total calls made/received
- `redphone_call_duration_seconds` — Call duration histogram
- `redphone_discovered_phones` — Number of discovered phones
- `redphone_uptime_seconds` — Service uptime

## Security Considerations

1. **Never expose to public internet** — Tailscale only
2. **Use strong admin passwords**
3. **Keep systems updated** — `apt upgrade` regularly
4. **Monitor logs** for unusual activity
5. **Back up configs** before changes

## Factory Reset

To reset a phone to defaults:

```bash
# Stop service
sudo systemctl stop redphone

# Remove config and state
sudo rm -rf /etc/redphone/config.yaml
sudo rm -rf /var/lib/redphone/*

# Re-run setup
sudo /opt/redphone/scripts/install.sh

# Reconfigure
sudo cp /opt/redphone/config.example.yaml /etc/redphone/config.yaml
sudo nano /etc/redphone/config.yaml

# Start
sudo systemctl start redphone
```
