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
WantedBy=multi-user.target```

## 🩺 Troubleshooting

### "Insufficient free heap" on boot

The firmware now refuses to enter the main loop if less than 8 KB of heap is free at startup. You'll see:

```
[CRITICAL ERROR] Insufficient free heap (< 8 KB). Refusing to start main loop.
```

This is a **safety net**, not a hardware fault. It catches a `main.py` that grew too big (e.g. a new screen added without reusing palette pens) or a corrupted upload. Fix by:

1. Re-uploading `tufty/main.py` from the repo (see `tufty/README.md`).
2. If the problem persists on a known-good upload, check the Pimoroni MicroPython firmware version — a firmware update may have changed the heap layout.

### Button presses feel "stiff" or don't register

Buttons now use a 30 ms edge-hold debounce to swallow single-frame glitches. A press that lasts **less than ~30 ms** is ignored. If a button never responds:

1. Confirm the button physically works (hold it for a second and check the underline under `STATS` / `CLOCK` / `LIGHT` on screen).
2. Re-seat the Tufty 2040 on its base — a loose connector can cause a stuck-low that the debounce now (correctly) filters out.
3. If all five buttons are dead, the `pimoroni` library version may not match the firmware — re-flash per `tufty/README.md`.

### "COMM FAILURE" screen after 5 s

The Tufty shows the red `COMM FAILURE / COMPUTER OFFLINE` screen when no telemetry frame arrives for 5 s. Causes, in order of likelihood:

1. **Serial port gone** — run `python host/sender.py --debug` in the foreground and watch for the `[ALERT] No Tufty 2040 (RP2040) detected` line. Re-plug the USB cable; on Linux check `ls /dev/ttyACM*`.
2. **Service crashed** — `journalctl -u tufty-monitor -n 50` will show the last exception. Common cause: the `.venv` was deleted or the repo moved (update `host/tufty-monitor.service` paths, then `systemctl daemon-reload && systemctl restart tufty-monitor`).
3. **Wrong baud rate** — the sender and the Tufty must agree on `115200`. If you changed `--baud` on the sender, the Tufty is still on 115200 and will show garbled frames → no telemetry.

### Service won't start

```
systemctl status tufty-monitor
journalctl -u tufty-monitor -n 100
```

Common causes:

- **Port already open** — another instance of `sender.py` (or Thonny / `mpremote`) has the Tufty port open. Close it and retry.
- **`.venv` missing** — re-run `cd host && ./setup_env.sh`.
- **Wrong user** — the unit sets `User=pi`. If your Pi user differs, edit the unit, `systemctl daemon-reload`, then `systemctl restart tufty-monitor`.
