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

#### Option A: Using `mpremote` (CLI — Fast)
Install `mpremote` on your system:
```bash
pip install mpremote
```

Make sure nothing else is holding the USB port (stop the `tufty-monitor` systemd service, close Thonny). Then, from the repository root:
```bash
.venv/bin/mpremote a0 fs ls             # sanity check: the drive answers
.venv/bin/mpremote a0 cp main.py :main.py
.venv/bin/mpremote a0 reset
```

You can also target an explicit port instead of auto-detect (`a0`):
`mpremote /dev/ttyACM0 cp main.py :main.py` (Linux) or `mpremote COM7 cp main.py :main.py` (Windows).

#### Option B: Using Thonny (IDE — Visual)
1. Open Thonny and choose **Raspberry Pi MicroPython** → **ESP/other board** from the interpreter menu if it is not already selected.
2. Connect the Tufty 2040 over USB (Thonny will detect `/dev/ttyACM0` or the equivalent COM port).
3. Open `main.py` in Thonny and transfer it to the device with **Run → Save as… → select `main.py` on the `:memory:`/root filesystem** (or simply open **File → Open**, pick `main.py` from the device, paste the content, and save).
4. Reset the board (**Run → Reset → Soft**) so the freshly uploaded `main.py` starts on boot.

---

## 📡 After a Successful Upload

- The screen shows the **LCARS standby view** (`SYSTEM STANDBY / AWAITING DATA FROM COMPUTER...`) while no telemetry is arriving, and switches to the **STATS** screen as soon as the first frame lands.
- The USB serial port **is** the data channel: the host sender (`host/sender.py`) and the REPL share `/dev/ttyACM0`, so only one of them may be attached at a time.
- To watch the boot log (`[DEBUG][RAM Free: …]`, `[RTC SYNC]`, `[MODE]`, `[AUTO-LUX]` lines) live, open a serial terminal on `/dev/ttyACM0` at 115200 baud — see the ["Watching the Tufty serial log (development)"](../docs/setup_guide.md#-watching-the-tufty-serial-log-development) section in `docs/setup_guide.md`.
- If the screen prints `[CRITICAL ERROR] Insufficient free heap (< 8 KB). Refusing to start main loop.`, the upload is corrupted or `main.py` grew too large — re-upload per the steps above.
