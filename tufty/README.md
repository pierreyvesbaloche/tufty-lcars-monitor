# 🔌 Tufty 2040 Firmware & MicroPython Setup

This directory contains the display code for the **Pimoroni Tufty 2040** (RP2040). It renders an LCARS system monitoring dashboard by parsing metric streams sent over USB Serial from the Raspberry Pi.

---

## 📋 Prerequisites

Before setting up the code, ensure you have:
1. **Pimoroni Tufty 2040** board.
2. Micro-USB data cable (connected to a USB port on your host).
3. **Thonny IDE** OR Python's **`mpremote`** CLI tool installed (`pip install mpremote`).

---

## ⚡ Setup & Flashing Instructions

### Step 1: Flash Pimoroni MicroPython Firmware
1. Hold down the **BOOTSEL** button on your Tufty 2040 while plugging it into your host computer/Raspberry Pi. The board will mount as a USB drive named `RPI-RP2`.
2. Download the latest **Pimoroni PicoGraphics MicroPython** firmware (`.uf2`) from the official repository:
   👉 [Pimoroni Pico Releases (GitHub)](https://github.com/pimoroni/pimoroni-pico/releases)
3. Drag and drop the downloaded `.uf2` file into the `RPI-RP2` drive. The board will automatically reboot.

### Step 2: Upload `main.py`

#### Option A: Using `mpremote` (CLI - Fast)
Install `mpremote` on your system:
```bash
pip install mpremote