#!/bin/bash
# The Red Phone - Installation Script
# Run with sudo: sudo ./scripts/install.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${RED}╔═══════════════════════════════════════╗${NC}"
echo -e "${RED}║       The Red Phone Installer         ║${NC}"
echo -e "${RED}╚═══════════════════════════════════════╝${NC}"
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: Please run as root (sudo)${NC}"
    exit 1
fi

# Detect if running on Raspberry Pi
if grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    IS_PI=true
    echo -e "${GREEN}✓ Detected Raspberry Pi${NC}"
else
    IS_PI=false
    echo -e "${YELLOW}⚠ Not running on Raspberry Pi - some features disabled${NC}"
fi

# Get the install directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "\nInstalling from: ${INSTALL_DIR}"

# ============================================================================
# System packages
# ============================================================================

echo -e "\n${YELLOW}Installing system packages...${NC}"

apt-get update -qq

apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    asterisk \
    chromium-browser \
    avahi-daemon \
    libasound2-dev \
    portaudio19-dev \
    curl

echo -e "${GREEN}✓ System packages installed${NC}"

# ============================================================================
# Tailscale
# ============================================================================

if ! command -v tailscale &> /dev/null; then
    echo -e "\n${YELLOW}Installing Tailscale...${NC}"
    curl -fsSL https://tailscale.com/install.sh | sh
    echo -e "${GREEN}✓ Tailscale installed${NC}"
    echo -e "${YELLOW}⚠ Run 'sudo tailscale up' to authenticate${NC}"
else
    echo -e "${GREEN}✓ Tailscale already installed${NC}"
fi

# ============================================================================
# Python virtual environment
# ============================================================================

echo -e "\n${YELLOW}Setting up Python environment...${NC}"

VENV_DIR="${INSTALL_DIR}/venv"

if [ -d "$VENV_DIR" ]; then
    rm -rf "$VENV_DIR"
fi

python3 -m venv "$VENV_DIR"
source "${VENV_DIR}/bin/activate"

pip install --upgrade pip wheel -q
pip install -r "${INSTALL_DIR}/requirements.txt" -q

echo -e "${GREEN}✓ Python environment ready${NC}"

# ============================================================================
# Configuration directories
# ============================================================================

echo -e "\n${YELLOW}Creating configuration directories...${NC}"

mkdir -p /etc/redphone
mkdir -p /var/lib/redphone
mkdir -p /var/log/redphone

# Copy example config if none exists
if [ ! -f /etc/redphone/config.yaml ]; then
    cp "${INSTALL_DIR}/config.example.yaml" /etc/redphone/config.yaml
    echo -e "${YELLOW}⚠ Edit /etc/redphone/config.yaml to configure your phone${NC}"
fi

# Set permissions
chown -R root:root /etc/redphone
chmod 755 /etc/redphone
chmod 644 /etc/redphone/config.yaml

echo -e "${GREEN}✓ Configuration directories created${NC}"

# ============================================================================
# Asterisk configuration
# ============================================================================

echo -e "\n${YELLOW}Configuring Asterisk...${NC}"

# Backup original config
if [ ! -f /etc/asterisk/sip.conf.orig ]; then
    cp /etc/asterisk/sip.conf /etc/asterisk/sip.conf.orig 2>/dev/null || true
fi

# Copy our Asterisk configs
if [ -d "${INSTALL_DIR}/asterisk/config" ]; then
    cp "${INSTALL_DIR}/asterisk/config/"* /etc/asterisk/
fi

# Enable and start Asterisk
systemctl enable asterisk
systemctl restart asterisk

echo -e "${GREEN}✓ Asterisk configured${NC}"

# ============================================================================
# Systemd service
# ============================================================================

echo -e "\n${YELLOW}Installing systemd service...${NC}"

cat > /etc/systemd/system/redphone.service << EOF
[Unit]
Description=The Red Phone VoIP Service
After=network.target asterisk.service tailscaled.service
Wants=asterisk.service

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=${VENV_DIR}/bin/python -m redphone.app
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable redphone

echo -e "${GREEN}✓ Systemd service installed${NC}"

# ============================================================================
# Kiosk mode (Raspberry Pi only)
# ============================================================================

if [ "$IS_PI" = true ]; then
    echo -e "\n${YELLOW}Configuring kiosk mode...${NC}"
    
    # Create kiosk startup script
    mkdir -p /home/pi/.config/autostart
    
    cat > /home/pi/.config/autostart/redphone-kiosk.desktop << EOF
[Desktop Entry]
Type=Application
Name=RedPhone Kiosk
Exec=/usr/bin/chromium-browser --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble --disable-restore-session-state http://localhost:5000
X-GNOME-Autostart-enabled=true
EOF
    
    chown pi:pi /home/pi/.config/autostart/redphone-kiosk.desktop
    
    # Disable screen blanking
    if [ -f /etc/lightdm/lightdm.conf ]; then
        sed -i 's/#xserver-command=X/xserver-command=X -s 0 -dpms/' /etc/lightdm/lightdm.conf
    fi
    
    echo -e "${GREEN}✓ Kiosk mode configured${NC}"
fi

# ============================================================================
# Done!
# ============================================================================

echo
echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Installation Complete! ☎️          ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
echo
echo -e "Next steps:"
echo -e "  1. Edit /etc/redphone/config.yaml"
echo -e "  2. Set up Tailscale: ${YELLOW}sudo tailscale up${NC}"
echo -e "  3. Start the service: ${YELLOW}sudo systemctl start redphone${NC}"
echo -e "  4. Open http://localhost:5000 in browser"
echo
echo -e "${YELLOW}To check status: sudo systemctl status redphone${NC}"
echo -e "${YELLOW}To view logs: journalctl -u redphone -f${NC}"
