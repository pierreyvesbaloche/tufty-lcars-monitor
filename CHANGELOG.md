# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### ✨ Added
- **Heartbeat / liveness frame (protocol, §1.2 of `docs/IMPROVEMENT_PLAN.md`)** — the host now sends a `PING:<n>` frame every 2 s as its **own line** (`PING_INTERVAL`), independently of telemetry and time sync; `<n>` is a monotonically increasing counter (wraps at 65535) so a stuck host repeating the same line is distinguishable from a live one. No `PONG` — the host is one-way. The Tufty treats PING as a distinct frame type and now tracks liveness as the **newest of telemetry / sync / heartbeat** (`last_activity`), so a stuck-but-quiet host is no longer indistinguishable from a dead one: the COMM FAILURE view only appears when no frame of any kind has arrived for 5 s. Pausing telemetry while heartbeats continue no longer trips the failure view.

### ⚡ Changed
- **Time-sync frame split (protocol, §1.1 of `docs/IMPROVEMENT_PLAN.md`)** — `INIT_TIME` no longer rides on the telemetry line. The host now sends it as a **separate `INIT_TIME:YYYY,MM,DD,HH,MM,SS` line** whenever the 60 s `SYNC_INTERVAL` elapses, independently of telemetry ticks, so a dropped or late metrics frame can no longer delay or suppress a pending sync. The Tufty parser treats `INIT_TIME` as a distinct frame type (line-level dispatch) instead of a key inside the telemetry dict; a sync frame still counts as host liveness for the 5 s COMM FAILURE timer. No user-visible behaviour change: same fields, same 60 s cadence, same RTC drift correction rule (hour/minute diff or ≥ 2 s).

### ✨ Added
- **Battery / power indicator (`tufty/main.py`)** — §3.3 of `docs/IMPROVEMENT_PLAN.md`. A small battery icon (top-right corner, 24×12 px) now renders on every screen, showing:
  - **Fill level** from an ADC-29 voltage measurement (vref mux on GPIO 27, shared with the lux sensor — the pin is asserted LOW for ~1 ms per read, then restored, so auto-brightness is unaffected).
  - **Color**: cyan (reuses `CYAN_MAIN`) above 20 %, red (reuses `RED_ALERT`) at/below 20 %.
  - **USB bolt** (gold, reuses `GOLD_LCARS`) when VBUS is detected on GPIO 24.
  - **Hidden** when no battery is connected (vbat < 1.0 V) or the measurement fails — the icon degrades to outline-only, no error spam.
  - **Refresh**: every 2 s, gated by `vbat_adc is not None` so a failed init costs zero cycles.
  - **No new pens**: the PEN_P4 16-color cap is already at 12/12 used; the icon reuses `GRAY_TEXT` / `BLACK` / `CYAN_MAIN` / `RED_ALERT` / `GOLD_LCARS`. Palette budget unchanged.
  - **No protocol change, no new serial output** — the icon is purely local to the Tufty.
  - **Tunable**: `BATT_FULL_V` (default 3.7 V, Galleon 400 mAh LiPo), `BATT_EMPTY_V` (default 2.5 V), `BATT_LOW_PCT` (default 20), `BATT_REFRESH_S` (default 2.0) are module-level constants — adjust for your cell if needed.
  - **Caveat (documented in code)**: there is **no** Pimoroni `BATTERY` / fuel-gauge class in the Pimoroni MicroPython firmware for the Tufty 2040 — the `pimoroni.py` module only ships `Button` / `Analog` / `AnalogMux` / `LED` / `RGBLED`. The measurement is implemented inline (same approach as the official `micropython/examples/tufty2040/battery.py`), adapted for the shared GPIO 27 and the PEN_P4 palette.

### ⚡ Changed
- **Tufty firmware internals (`tufty/main.py`) — refactor for future screens, data model, and button debouncing (hardware-verified on a real Tufty 2040):**
  - **Screen dispatch centralised** (`draw_current_screen()`): the main loop no longer branches on `current_screen` directly. Adding a screen is now a one-function + one-branch change instead of touching the main loop.
  - **Typed telemetry model** (`TELEMETRY`): the flat `last_data` dict with mixed `float`/`str` keys is replaced by a single shared object with 10 named fields (`cpu`, `ram_pct`, `ram_u`, `ram_t`, `disk_pct`, `disk_u`, `disk_t`, `eth`, `wifi`, `ts`). The parser writes in-place; draw functions read by field name. No protocol change — same `KEY:VALUE` wire format.
  - **Button debouncing** (15 ms edge-hold, on top of the Pimoroni `Button` class's own internal filtering): single-frame glitches no longer flip `auto_brightness` or switch screens. Up/Down brightness steps and the AUTO/MAN toggle on Button C are now stable under 100 Hz polling. Field-verified: short real presses get through, glitches are swallowed.
  - **Startup memory headroom check**: firmware now refuses to enter the main loop if free heap < 8 KB (prints `[CRITICAL ERROR]` and exits). Catches a broken `main.py` upload before it OOMs the device mid-frame. Field-verified: passes on a known-good upload with ~18× margin (154 512 B free at boot).
  - **No user-visible behaviour change** on existing hardware: same screens, same buttons, same serial protocol, same gauge thresholds (amber ≥ 80 %, red ≥ 90 %), same 5 s COMM FAILURE timeout. STATS / CLOCK / LIGHT / brightness transitions all confirmed on the physical display.

### 📚 Added
- **`docs/setup_guide.md` — "Watching the Tufty serial log (development)" section**: recommended `screen /dev/ttyACM0 115200` workflow (releases the port cleanly on quit, unlike `cat`), `minicom` / `picocom` / `pyserial` one-shot alternatives, expected clean-boot sequence, and the `[CRITICAL ERROR]` line to avoid. Troubleshooting entries for the new headroom check and the 15 ms debounce.

---

## [1.0.0] - 2026-09-08

### ✨ Added
- **Tufty 2040 LCARS Display Interface (`tufty/main.py`)**:
  - **System Metrics Screen (STATS)**: Graphic bar gauges displaying real-time CPU, RAM, and Disk utilization with dynamic visual warnings (amber at ≥ 80%, red at ≥ 90%).
  - **Clock Screen (CLOCK)**: Real-time host-synced clock, standard date layout, and *Stardate* calculation.
  - **Physical Button Labels & Underlines**: Dynamic underline indicator for button labels aligned with physical hardware (`x=55` for STATS, `x=145` for CLOCK, `x=235` for LIGHT).
  - **Display Brightness Control (LIGHT)**:
    - Automatic mode driven by the ambient light sensor (phototransistor on ADC 26 / GPIO 27).
    - Manual mode with `UP` / `DOWN` button adjustments.
    - Active underline and accent color on the **LIGHT** label when manual mode is engaged.
  - **Status & Failure Views**:
    - Initial standby view (`AWAITING DATA FROM COMPUTER...`).
    - Communication failure view triggered after 5 seconds without serial data (`COMM FAILURE / COMPUTER OFFLINE`).
  - **MicroPython RTC Timestamp Incompatibility**: Replaced standard Unix epoch timestamps with human-readable string formatting (`YYYY,MM,DD,HH,MM,SS`) to bypass RP2040 MicroPython 2000-epoch offset limitations.
  - **Serial Buffer Overflows**: Reduced frequency of `[AUTO-LUX]` log printouts from 2s to 30s to prevent serial port buffer congestion and log backlog.
  - **Host Sync Interval Tracking**: Fixed a bug in `host/monitor_sender.py` where `last_sync_time` stored the offsetted target timestamp instead of the local timestamp, ensuring true 60-second synchronization intervals.

- **Host Monitoring Script (`host/sender.py`)**:
  - Telemetry collector and serial data provider (CPU, RAM, Disk, Unix Timestamp, IP Addresses).
  - Cross-platform support for **Windows**, **Linux**, and **macOS**.
  - Dynamic network interface scanning supporting hot-swapping for Ethernet and Wi-Fi connections.
  - Automatic filtering of virtual adapters, VPNs, and loopbacks (`docker`, `tun`, `tap`, `veth`, etc.).
  - **Timezone Offset Support**: Added `-o` / `--offset` command-line argument to `host/sender.py` to specify timezone offsets (e.g., `-o 2` for UTC+2).
  - **Complete English Localization**: Standardized all logs, terminal outputs, error messages, and code comments in English.
  - **Automatic connection**: Automatically detect the port to which the Tufty is connected to.

- **Tooling & Documentation**:
  - Integrated `mpremote` USB serial support (e.g., `COM7` under Windows).
  - Command reference guide for code deployment, file transfers, and real-time REPL logging.

---

## Standard Emoji Guide for Future Releases

| Emoji | Section | Description |
| :---: | :--- | :--- |
| ✨ | `Added` | New features introduced |
| ⚡ | `Changed` | Changes in existing functionality |
| 🗑️ | `Deprecated` | Soon-to-be removed features |
| ❌ | `Removed` | Features removed in this release |
| 🐛 | `Fixed` | Any bug fixes |
| 🔒 | `Security` | Vulnerability fixes and security updates |

[1.0.0]: https://github.com/pierreyvesbaloche/tufty-lcars-monitor/releases/tag/v1.0.0

