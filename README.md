# 🚀 Tufty 2040 LCARS System Monitor

![Aperçu Tufty LCARS Monitor](assets/02.png)

A **Star Trek LCARS** style system monitoring tool for Raspberry Pi using a **Pimoroni Tufty 2040** (RP2040) display.

## 🎮 Features
- **Standby / Waiting Screen:** Displays an LCARS standby status until initial data is received over USB.
- **Real-time Metrics:** Monitors CPU, RAM, Disk Usage, and active network IPs (ETH/WIFI).
- **Dynamic Gauge Colors:** Color transitions automatically based on workload (Normal → Amber at 80% → Red at 90%).
- **Auto Brightness:** Ambient light adjustment using the built-in phototransistor (with a safe floor at 50%).
- **Clock Mode:** Switchable via Button B (RTC Clock + Stardate display).
- **Background Service:** Includes Systemd integration to launch automatically at Raspberry Pi boot.

---

## 🛠️ Project Architecture

- `raspberry/`: Python script running on the Raspberry Pi to collect and stream metrics over Serial (USB), along with Systemd setup scripts.
- `tufty/`: MicroPython script running directly on the Pimoroni Tufty 2040.

---

## ⚡ Quick Start

### 1. Preparing the Tufty 2040
1. Flash the latest **Pimoroni PicoGraphics** MicroPython firmware for Tufty 2040.
2. Transfer `tufty/main.py` to the root of the MicroPython filesystem using **Thonny IDE**.

### 2. Preparing the Raspberry Pi & Installing Service
```bash
cd raspberry
chmod +x setup_env.sh
./setup_env.sh
