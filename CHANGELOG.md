# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### ⚡ Changed
- **Tufty firmware internals (`tufty/main.py`) — refactor for future screens, data model, and button debouncing:**
  - **Screen dispatch centralised** (`draw_current_screen()`): the main loop no longer branches on `current_screen` directly. Adding a screen is now a one-function + one-branch change instead of touching the main loop.
  - **Typed telemetry model** (`TELEMETRY`): the flat `last_data` dict with mixed `float`/`str` keys is replaced by a single shared object with 10 named fields (`cpu`, `ram_pct`, `ram_u`, `ram_t`, `disk_pct`, `disk_u`, `disk_t`, `eth`, `wifi`, `ts`). The parser writes in-place; draw functions read by field name. No protocol change — same `KEY:VALUE` wire format.
  - **Button debouncing** (30 ms edge-hold): single-frame glitches no longer flip `auto_brightness` or switch screens. Up/Down brightness steps and the AUTO/MAN toggle on Button C are now stable under 100 Hz polling.
  - **Startup memory headroom check**: firmware now refuses to enter the main loop if free heap < 8 KB (prints `[CRITICAL ERROR]` and exits). Catches a broken `main.py` upload before it OOMs the device mid-frame.
  - **No user-visible behaviour change** on existing hardware: same screens, same buttons, same serial protocol, same gauge thresholds (amber ≥ 80 %, red ≥ 90 %), same 5 s COMM FAILURE timeout.

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

