# AGENTS.md — Tufty 2040 LCARS System Monitor

Guidance for AI coding agents working in this repository.

## Project overview
Star Trek **LCARS**-styled system monitor for the Pimoroni **Tufty 2040** (RP2040). A Python host script (`host/sender.py`) streams CPU/RAM/disk/IP metrics + time over **USB serial** to a MicroPython program (`tufty/main.py`) that renders an LCARS dashboard.

**Repo layout (flat, ~10 tracked files — read them all; no test suite, no CI, no package config):**
```
host/
  sender.py                # host telemetry sender (pyserial + psutil)
  requirements.txt         # psutil, pyserial, mpremote
  setup_env.sh             # venv + deps + systemd service install (bash, set -e)
  tufty-monitor.service    # systemd unit (User=pi, /home/pi/tufty-lcars-monitor)
tufty/
  main.py                  # MicroPython firmware (runs on the Tufty 2040)
  README.md                # firmware setup / flashing guide
docs/
  setup_guide.md           # systemd guide
  Tufty2040-LCARS-Documentation.pdf
assets/ 01.png..05.png    # project photos/screenshots
models/ *_v1.stl          # 3D-printed case (left/right)
README.md, CHANGELOG.md, LICENSE, AGENTS.md
```

## Agent output rules
- **No code in chat or thinking:** never paste file contents, diffs, or code snippets into the user-facing reply or extended thinking. Report actions briefly and in plain language (what was changed, where, and why) without showing the underlying code or reasoning steps.

## Critical constraints (easy to get wrong)

### Two incompatible Pythons
- **`host/`** = CPython 3, runs on the host (Linux/Win/macOS). Normal stdlib ok. Deps: `psutil`, `pyserial`.
- **`tufty/main.py`** = **MicroPython on RP2040**. No venv, no pip, no CPython stdlib, **~256 KB RAM, PEN_P4 4-bit palette (16 colors max)**.
- Never import CPython-only libraries in `tufty/main.py`. Memory is scarce: `gc.collect()` liberally, `micropython.alloc_emergency_exception_buf(100)` is load-bearing — keep both.
- **Don't print from `tufty/main.py` carelessly**: it shares the USB serial line with telemetry. Lux logging was throttled 2 s → 30 s specifically to stop buffer overflows. Keep the 30 s throttle (or add equivalent throttling) on any new periodic log.
- **MicroPython RTC quirk:** no Unix-epoch time. That's why sync uses the human-readable string format `YYYY,MM,DD,HH,MM,SS` inside `INIT_TIME`. Don't "fix" it to Unix timestamps — the 2000-epoch limitation is why it's a string.

### The serial protocol (do not change unilaterally)
Both ends must stay in sync. Frames are **UTF-8, pipe-delimited `KEY:VALUE`, one line per frame, `\n`-terminated**:
```
CPU:12.5|RAM_PCT:48.2|RAM_U:7.7|RAM_T:16.0|DISK_PCT:62.1|DISK_U:310.5|DISK_T:500.0|ETH:192.168.1.50|WIFI:N/A
```
- **`INIT_TIME` is its own frame** (`INIT_TIME:YYYY,MM,DD,HH,MM,SS`, sent on its own line whenever the 60 s `SYNC_INTERVAL` elapses, independently of telemetry — §1.1). It is **not** a key inside the telemetry dict; the Tufty parser dispatches it at line level. A sync frame still counts as host liveness for the 5 s COMM FAILURE timer.
- `INIT_TIME` value = `YYYY,MM,DD,HH,MM,SS` (comma-separated, **not Unix epoch**).
- Tufty parses telemetry case-insensitively; numeric fields are floats, `ETH`/`WIFI` stay strings.
- Protocol changes require editing **both** `host/sender.py` and `tufty/main.py` together, plus updating the README protocol section.
- Baud default **115200**; the Tufty is recognized by **VID 0x2E8A** (Raspberry Pi Foundation) in auto port detection.

### Tuning knobs (documented in code, preserve meaning)
- Gauge thresholds: **amber ≥ 80 %, red ≥ 90 %** (`get_gauge_color`).
- Brightness floor **0.50**; lux ADC clamp **300–5000**.
- Connection-lost timeout **5 s** (`TIMEOUT_SECONDS`).

### Hardware
- Buttons: A=7, B=8, C=9, UP=22, DOWN=6. Light sensor: **ADC 26** + enable pin **GPIO 27** (must be driven HIGH before reading).
- Screens: `0`=STATS, `1`=CLOCK. Label x-positions are **hardcoded** to physical buttons (55 / 145 / 235).
- **PEN_P4 = 4-bit palette: max 16 pens** — the palette block is already near that limit; adding colors requires repurposing one.

## Working agreements
- **Branches:** feature branch per GitHub issue `N-short-slug` (e.g. `9-add-automatic-port-detection`), merged via PR. Issue numbers are sequential from the project's first commit.
- **Commits:** Conventional Commits — `feat(scope): ...`, `fix(scope): ...`, `refactor(scope): ...`, `chore(scope): ...`, `docs(...)` (scopes seen: `protocol`, `tufty`, `detection`, `plan`, `changelog`, `repo`, `3d`, `images`, `enhancements`).
- **PR titles:** same Conventional Commits convention as commits — e.g. `feat(protocol): 1.1 — Time-sync frame split`; body should cite the `docs/IMPROVEMENT_PLAN.md` section and its acceptance criteria.
- **CHANGELOG.md:** Keep-a-Changelog + SemVer. Add an entry under `Unreleased` for user-visible changes; keep the emoji-key convention (✨/⚡/🗑️/❌/🐛/🔒).
- **Docs:** user-facing changes go into `README.md` and/or `docs/setup_guide.md`; `tufty/README.md` covers firmware flashing only.

## Gotchas / known quirks (agent context, not user docs)
- **`host/setup_env.sh` and the README disagree:** the script as committed only creates `.venv/` and installs deps — it does **not** install the systemd unit. `docs/setup_guide.md` claims it does. Don't "fix" either doc to match without checking intent; if asked, resolve the inconsistency deliberately.
- `tufty-monitor.service` hardcodes `User=pi` and `/home/pi/tufty-lcars-monitor`.
- `sender.py` uses `disk_usage('/')` — fine on the Pi, wrong disk on multi-mount Windows/macOS.
- `detect_and_select_port()` opens each port briefly to probe busy/available state — can race with other serial tools.
- `.env` exists in the working tree but is **not gitignored**; verify it's not an accidental secret before committing anything.
- No tests, no CI, no linter. If adding a test for `sender.py`, note the serial device makes it awkward — a fake `serial.Serial` is the sane route.
- `models/` holds 3D-printed case STLs (`left_v1`, `right_v1`) — assets only.
- `assets/` = project photos for README/GitHub.

## When changing protocol / metrics
1. Edit `host/sender.py` (payload build) **and** `tufty/main.py` (parser + render) in the same change.
2. Update the Serial Protocol section in `README.md`.
3. Verify thresholds/colours still make sense (new gauge? apply amber/red rules).
4. Bump version in `CHANGELOG.md` if user-visible.
