# 📖 Detailed Setup & Troubleshooting Guide

## 🖥️ Systemd Service Setup (Raspberry Pi / Linux)

To ensure the monitoring sender runs continuously in the background and starts automatically whenever your host boots up, a **Systemd service** is used.

### Default Installation
`host/setup_env.sh` only creates `.venv/` and installs the Python dependencies — it does **not** register the service. After running it, install the unit from the repository root:
```bash
sudo cp host/tufty-monitor.service /etc/systemd/system/tufty-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable --now tufty-monitor
systemctl status tufty-monitor
```
The unit's default paths point at `/home/pi/tufty-lcars-monitor`; if your checkout lives elsewhere, edit the `WorkingDirectory` / `ExecStart` lines first (and/or keep a custom unit, see below).

### Custom Project Paths
If your project repository is located outside the standard `/home/pi/tufty-lcars-monitor` directory, update the paths inside `host/tufty-monitor.service` before installing the unit:

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
```

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

Buttons use a 15 ms edge-hold debounce on top of the Pimoroni `Button` class's own internal filtering. A press that lasts **less than ~15 ms** is ignored. If a button never responds:

1. Confirm the button physically works (hold it for a second and check the underline under `STATS` / `CLOCK` / `LIGHT` on screen).
2. Open the serial log (see [Watching the Tufty serial log](#-watching-the-tufty-serial-log-development)) and press the button. You should see a `[RAW-PRESS] <name> is_pressed=True` line. If you see it but no screen change, the debounce is eating the press — report it with the log.
3. If you see **no** `[RAW-PRESS]` line while holding the button, the GPIO is not transitioning — re-seat the Tufty 2040 on its base (a loose connector can cause a stuck state), and confirm the `pimoroni` library version matches the firmware (re-flash per `tufty/README.md`).

### Battery icon missing, stuck at 0 %, or wrong percentage

The battery icon (top-right) reads an ADC-29 voltage with the onboard vref mux on GPIO 27. If it's not showing what you expect:

1. **No icon at all (outline only)** — the firmware thinks no battery is connected (`vbat < 1.0 V`). Check the JST-PH connector on the back of the Tufty; a loose contact reads as 0 V.
2. **Stuck at 0 %** — the battery is below `BATT_EMPTY_V` (default 2.5 V). Either the cell is genuinely dead, or the default `BATT_EMPTY_V` / `BATT_FULL_V` don't match your cell. The Tufty 2040 supports AAA/AA packs (3× AAA recommended) and optional LiPo; the defaults (3.7 V / 2.5 V) are for a Galleon 400 mAh LiPo per the Pimoroni example. Adjust `BATT_FULL_V` / `BATT_EMPTY_V` at the top of `tufty/main.py` for your cell.
3. **Jumps / flickers** — the vref mux on GPIO 27 is shared with the lux sensor; the firmware asserts it LOW for ~1 ms per read (every 2 s) and restores it. If you see flicker, lower `BATT_REFRESH_S` is the wrong fix — check that nothing else in `main.py` is driving GPIO 27 to a fixed value (search for `Pin(27`). The lux-sensor init and the battery reader are the only two places that touch it.
4. **USB bolt not showing when plugged in** — the bolt is driven by GPIO 24 (VBUS detect). Some USB hubs/cables don't expose VBUS cleanly; try a different cable or a direct connection to the Pi/laptop.

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

## 👀 Watching the Tufty serial log (development)

The firmware prints `[DEBUG]`, `[MODE]`, `[RTC SYNC]`, `[AUTO-LUX]` and (during development) `[BOOT-TICK]` / `[RAW-PRESS]` lines to `sys.stdout`, which is the USB serial port. To see them live you need a serial terminal on `/dev/ttyACM0` at 115200 baud.

### Recommended: `screen`

`screen` is pre-installed on most Linux distros and — unlike `cat` — releases the port cleanly on quit, so you can still use `mpremote` from another terminal if needed.

```bash
# 1. Stop anything that holds the port (the systemd service, a stray mpremote, etc.)
sudo systemctl stop tufty-monitor          # if the service is installed

# 2. Upload the latest firmware and reset
.venv/bin/mpremote a0 cp tufty/main.py :main.py
.venv/bin/mpremote a0 reset

# 3. Open a live log window
screen /dev/ttyACM0 115200
```

Inside `screen`:
- `Ctrl-a` then `x` — quit (and close the port).
- `Ctrl-a` then `d` — detach (keeps the port open in the background; re-attach later with `screen -r`).
- Scrollback: `Ctrl-a` then `[` — enter copy mode, arrow keys to scroll, `Esc` to leave.

### Why not `cat /dev/ttyACM0`?

`cat` works, but it **exclusively** opens the port and never releases it cleanly on `Ctrl-C` — you'll often find the port stuck "busy" for the next `mpremote` call until you unplug/re-plug the Tufty. `screen` releases the port on quit and is the safer default.

### Other options

| Tool | Command | Notes |
|---|---|---|
| `minicom` | `minicom -D /dev/ttyACM0 -b 115200` | Full-featured, scrollable, logs to file. `Ctrl-A` `X` to quit. |
| `picocom` | `picocom -b 115200 /dev/ttyACM0` | `Ctrl-A` `Ctrl-X` to quit. |
| `pyserial` one-shot | `python3 -c "import serial,time; s=serial.Serial('/dev/ttyACM0',115200); start=time.time(); buf=b'';
while time.time()-start<10 and (line:=s.readline()): buf+=line;
print(buf.decode())"` | 10 s capture without holding the port interactively. |

### What to look for in a clean boot

```
[DEBUG][RAM Free: XXXXX B | Alloc: XXXX B] -> Initializing system...
[DEBUG][RAM Free: ...] -> Hardware and buttons initialized successfully!
[DEBUG][RAM Free: ...] -> Color palette initialized.
[DEBUG][RAM Free: ...] -> Starting main loop.
```

…and **not** seeing:

```
[CRITICAL ERROR] Insufficient free heap (< 8 KB). Refusing to start main loop.
```
