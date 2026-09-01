# 📖 Detailed Setup & Troubleshooting Guide

## 🖥️ Systemd Service Setup (Raspberry Pi / Linux)

To ensure the monitoring sender runs continuously in the background and starts automatically whenever your host boots up, a **Systemd service** is used.

### Default Installation
The automated script (`host/setup_env.sh`) installs the service automatically. If you ran `./setup_env.sh`, the service is already registered and active.

### Custom Project Paths
If your project repository is located outside the standard `/home/pi/tufty-lcars-monitor` directory, update the paths inside `host/tufty-monitor.service` before running the setup script:

```ini
[Unit]
Description=Tufty 2040 LCARS System Monitor Sender
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/YOUR/CUSTOM/PATH/tufty-lcars-monitor/host
ExecStart=/YOUR/CUSTOM/PATH/tufty-lcars-monitor/.venv/bin/python /YOUR/CUSTOM/PATH/tufty-lcars-monitor/host/sender.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target