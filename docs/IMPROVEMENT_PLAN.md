# Improvement Plan — Tufty 2040 LCARS Monitor

> Roadmap of planned improvements, written for issue tracking.
> Each item is scoped to one or a few commits, includes the files it touches,
> and states the acceptance criteria. Check off as issues land.

## Status legend
- `[ ]` planned — `[~]` started — `[x]` done

## Done
- [x] #12 — §3.1 + §3.2 + §3.5 + §3.6 (Tufty firmware code quality) — PR #12, hardware-verified on a real Tufty 2040.
- [x] #13 — §3.3 (Tufty battery / fuel-gauge indicator) — PR #13, merged (origin/main @ `b50ccc8`, post-2026-11-12), hardware-verified on a real Tufty 2040 (USB power case; no battery pack attached during test).
- [x] #14 — §1.1 (Time-sync frame split) — merged (origin/main @ `5258dfa`, 2026-11-12). `INIT_TIME` is now a standalone `INIT_TIME:YYYY,MM,DD,HH,MM,SS` frame sent on its own line, independently of telemetry; Tufty parser treats it as a distinct frame type (line-level dispatch). No user-visible behaviour change (same fields, same 60 s cadence, same RTC correction rule).
- [x] #15 — §1.2 (Heartbeat / liveness) — merged (origin/main @ `af633a0`, 2026-11-12). `PING:<n>` (monotonic, wraps at 65535) is sent every 2 s on its own line, independently of telemetry and time sync; the Tufty treats it as a distinct frame type and keys the 5 s COMM FAILURE view off `last_activity` = newest of telemetry / sync / heartbeat. No user-visible behaviour change on a healthy host (same screens, same thresholds, same timeout).
- [~] #16 — §1.3 (Frame integrity: SEQ) — in progress, see AGENT STATE below.
## AGENT STATE — §1.3 Frame integrity: SEQ (#16, in progress)
- Status: `[~]` started — implemented locally on branch `16-frame-seq-integrity` (commit `74f6bc8`): the SEQ option from the plan (lighter than CRC). Host appends `|SEQ:<n>` (monotonic, wraps at 65536) to every telemetry frame; Tufty parser reads `seq` as an int field and rejects a frame when the distance from the last accepted seq is not exactly 1 (gap = dropped frame, duplicate = retransmission): frame dropped, last-good data kept, `[STALE FRAME] seq a -> b` logged, liveness still counts (1.2). First frame (prev seq -1) and legacy frames without SEQ parse as before — no hard dependency. Shadow-tested incl. wraparound (65535 -> 0 accept, 0 -> 2 reject). **Branch is LOCAL ONLY — not pushed.**
- WHAT IS LEFT TO BE DONE (user actions, then the agent does post-merge bookkeeping):
  1. Push the branch: `git push -u origin 16-frame-seq-integrity`.
  2. Open issue/PR #16 — suggested title: `1.3 — Frame integrity: telemetry SEQ counter (gap/duplicate rejection)` (body: plan §1.3 acceptance criteria).
  3. Merge (squash recommended).
  4. Post-merge: agent updates the Done list + this block.

## Conventions for turning these into issues
- Branch: `N-<slug>` (matches existing history, e.g. `12-add-heartbeat-ping`).
- Commit: Conventional Commits (`feat(scope)`, `fix(scope)`, `refactor(scope)`, `test(scope)`, `docs`, `chore`).
- CHANGELOG entry required for user-visible changes (✨/⚡/🗑️/❌/🐛/🔒 key).
- Protocol changes ship in **one** change touching `host/sender.py` + `tufty/main.py` + README protocol section.

---

## 1. Correctness & reliability

### 1.1 — Time-sync: stop "merging" `INIT_TIME` into telemetry
- **Why:** `INIT_TIME` is currently appended to the same line as the telemetry frame. That works but couples two concerns into one frame; a dropped/late sync line also delays a metrics frame. It also means a parse bug in one can lose both.
- **Files:** `host/sender.py`, `tufty/main.py`.
- **Plan:**
  - Send telemetry and time-sync as separate frames when both are due.
  - Keep `SYNC_INTERVAL = 60`; on the Tufty, treat `INIT_TIME` as a distinct message type, not a key inside the telemetry dict.
- **Acceptance:**
  - With a debug capture, `INIT_TIME` arrives on its own line.
  - Missing telemetry frame does not suppress a pending sync.
  - Tufty still corrects RTC drift identically (hour/minute diff or ≥2 s).

### 1.2 — Heartbeat / liveness on the serial line
- **Why:** The "COMM FAILURE" screen only triggers if **no** frame arrives for 5 s. A stuck-but-quiet host looks the same as a dead one; and a flaky USB cable can produce partial frames.
- **Files:** both.
- **Plan:**
  - Host sends a `PING:<n>` frame every 2 s (or every 2 telemetry ticks if cheaper).
  - Tufty tracks last-ping separately from last-telemetry; liveness = min of the two.
  - Optional: `PONG` not required — host is one-way.
- **Acceptance:**
  - Kill the host → Tufty shows COMM FAILURE in ≤ 5 s.
  - Pause telemetry (mock) but keep pinging → still considered alive.

### 1.3 — Frame integrity (checksum / seq number)
- **Why:** Pipe-delimited lines are easy to corrupt mid-line over USB; the Tufty currently just `try/except: pass` on parse errors and keeps the old data. Silent data staleness is the worst failure mode.
- **Files:** both.
- **Plan (pick one, prefer the lighter one):**
  - Add `SEQ:<n>` (monotonic, wrap at 65535) so the Tufty can detect gaps and flag "stale".
  - Or a 8-bit CRC over the whole line (`|CRC:<hex>`).
- **Acceptance:**
  - Inject a corrupted frame → Tufty either rejects it (no state change) or flags staleness visibly.
  - No regressions in normal operation.

### 1.4 — Handle `serial.Serial` open race in port probe
- **Why:** `detect_and_select_port()` opens every port briefly to probe busy/available. On Linux, `/dev/ttyACM*` probing can leave the port in a weird state or race with the auto-detected RP2040.
- **Files:** `host/sender.py`.
- **Plan:**
  - Use `p.hwid`/`p.manufacturer`/`p.vid` first; only open the candidate RP2040 port.
  - Or open with `exclusive=True` and close immediately, wrapped in a `finally`.
- **Acceptance:**
  - Repeated runs in a row on Linux don't wedge the Tufty port.

### 1.5 — Disk usage: make the mount configurable
- **Why:** `psutil.disk_usage('/')` is Pi-centric. On a multi-mount Linux or Windows this is misleading.
- **Files:** `host/sender.py`, README.
- **Plan:**
  - New CLI arg `--disk <path>` (default `/`).
  - On Windows default to the drive containing the CWD, or `C:\`.
- **Acceptance:**
  - `python sender.py COM7 --disk D:\` reports D: usage.

### 1.6 — Network IP: prefer a stable interface name
- **Why:** The name-based classifier (`'eth' in name`, `'wifi' in name`) is fragile across distros (Linux `enp3s0`, macOS `en0`, Windows `Ethernet 1`).
- **Files:** `host/sender.py`.
- **Plan:**
  - Use `psutil.net_if_stats()` + `net_if_addrs()`; classify by **interface type** where available (`iface_type` on Linux) and fall back to name heuristics.
  - Allow a `--eth-iface` / `--wifi-iface` override.
- **Acceptance:**
  - Correct IP on a headless Pi (eth0), a laptop (en0 + wlan0), and a VM (veth* filtered).

---

## 2. Host sender — code quality

### 2.1 — Split `sender.py` into a small package
- **Why:** single 200-line file is fine now; the moment we add protocol framing (1.1/1.3) it'll balloon.
- **Files:** `host/sender.py` → `host/tufty_monitor/{__init__,protocol,collector,main}.py`.
- **Plan:**
  - `protocol.py`: builds/validates frames (pure functions, easy to unit-test).
  - `collector.py`: `psutil` + IP collection, returns a `dataclass TelemetryFrame`.
  - `main.py`: argparse, port detection, loop.
- **Acceptance:**
  - `python -m tufty_monitor` works from the repo root.
  - `setup_env.sh` and `tufty-monitor.service` updated to match.

### 2.2 — Structured logging
- **Why:** `print(...)` everywhere; no levels; no timestamps; no log file for a long-running systemd service.
- **Files:** `host/` (whole).
- **Plan:**
  - `logging` module, default `INFO`, `--debug` → `DEBUG`.
  - `--log-file <path>` (rotating, default 5 MB × 3).
  - Under systemd, emit to stdout only (journald handles the rest).
- **Acceptance:**
  - `journalctl -u tufty-monitor` shows clean lines.
  - No `print()` left in the hot path.

### 2.3 — Graceful shutdown & signal handling
- **Why:** only `KeyboardInterrupt` is handled; SIGTERM (the systemd stop signal) leaves the serial port open and the last frame half-sent.
- **Files:** `host/sender.py`.
- **Plan:**
  - `signal.signal(SIGTERM, ...)` → clean close + final `SHUTDOWN` frame (optional, see 3.4).
  - `contextlib.ExitStack` for the serial handle.
- **Acceptance:**
  - `systemctl stop tufty-monitor` → no "port in use" on next start.

### 2.4 — Config via `.env` / CLI / defaults
- **Why:** `--offset` is the only tunable; a real deployment wants `baud`, `sync_interval`, `disk_mount`, `iface overrides` without editing code.
- **Files:** `host/sender.py`.
- **Plan:**
  - `python-dotenv` (add to `requirements.txt`), `.env` is already present in the tree but untracked-by-gitignore — **decide and document** which values live in `.env` vs CLI.
  - Precedence: CLI > env > default.
- **Acceptance:**
  - Documented matrix in README.
  - `.env` either tracked with placeholder values or explicitly `.gitignore`d — pick one and make it consistent.

### 2.5 — `requirements.txt`: pin or not?
- **Why:** currently `>=` only. MicroPython/Pimoroni updates occasionally break things; `psutil` and `pyserial` are stable but worth pinning on the Pi service.
- **Files:** `host/requirements.txt`.
- **Plan:** pin exact versions for the service, keep `>=` in a `requirements-dev.txt` if you want dev flexibility.
- **Acceptance:** `setup_env.sh` produces a reproducible venv.

---

## 3. Tufty firmware — code quality & UX

### 3.1 — State machine for screens [x] #12
- **Why:** `current_screen` is a global int and the main loop branches on it. Adding a 3rd screen (e.g. alerts, network detail) is a pain.
- **Files:** `tufty/main.py`.
- **Plan:**
  - Small `SCREENS = {"STATS": draw_screen_metrics, "CLOCK": draw_screen_clock, ...}` table.
  - `handle_buttons` returns the **target screen** (or `None` for no-op); loop just calls it.
- **Acceptance:**
  - Adding a new screen = one dict entry + one draw function.

### 3.2 — Data model on the Tufty [x] #12
- **Why:** `last_data` is a flat dict with mixed types (`float` + `str` for ETH/WIFI); key names are ad-hoc (`ram_pct`, `disk_pct`).
- **Files:** `tufty/main.py`.
- **Plan:**
  - Typed dict or small class `Telemetry(cpu, ram_pct, ram_u, ram_t, disk_pct, disk_u, disk_t, eth, wifi, ts)`.
  - Parser returns an instance or `None` (rejects malformed frames — pairs with 1.3).
- **Acceptance:**
  - Renderers read fields by name, no `d.get('cpu', 0)` sprinkled around.

### 3.3 — Battery / power [x] #13 (merged)
- **Why:** The Tufty 2040 can be powered from USB or an optional LiPo; right now the code assumes USB.
- **Files:** `tufty/main.py` (+ a `BATTERY` metric on the host if/when relevant).
- **Plan:**
  - Read the Pimoroni `BATTERY` / fuel-gauge API if present; show a small icon on the STATS screen.
  - If not present, skip silently.
- **Acceptance:** No regressions on USB-only setups.

### 3.4 — `SHUTDOWN` / `WAKEUP` frames (optional)
- **Why:** When the host stops cleanly (see 2.3) the Tufty can show a distinct "HOST OFFLINE" screen instead of the generic COMM FAILURE.
- **Files:** both.
- **Plan:** host sends `SHUTDOWN` on SIGTERM; Tufty shows a "HOST SIGNED OFF" view for N seconds, then reverts to standby.
- **Acceptance:** clean `systemctl stop` → graceful screen change, no 5 s red blink.

### 3.5 — Memory: audit & headroom [x] #12
- **Why:** PEN_P4 16-pen limit is already at the cap. Any new screen needs to reuse pens.
- **Files:** `tufty/main.py`.
- **Plan:**
  - Add a `[RAM]` startup log line that prints free/allocated at boot (already there for the first frame; make it permanent at `DEBUG` level).
  - Before merging any new screen, run `gc.mem_free()` and assert ≥ 8 KB headroom in a small boot-time check.
- **Acceptance:** no `MemoryError` in normal operation; new screens pass the headroom check.

### 3.6 — Button debouncing & long-press [x] #12
- **Why:** buttons are polled at 100 Hz; a single glitch can flip `auto_brightness`.
- **Files:** `tufty/main.py`.
- **Plan:**
  - 30 ms debounce (edge-trigger with a timestamp per button).
  - Optional: 1 s long-press on C = reset to AUTO mode.
- **Acceptance:** no accidental mode flips in 10 min of random tapping.

---

## 4. Tests (currently zero)

### 4.1 — Host: unit tests for the protocol
- **Why:** protocol bugs are the #1 risk in this repo.
- **Files:** `host/tests/test_protocol.py`, `host/tests/test_collector.py`.
- **Plan:**
  - `pytest` + a `FakeSerial` that captures writes.
  - Build frame → assert byte-exact match.
  - Parse frame → assert field types and values.
  - IP classifier: fake `psutil.net_if_addrs` responses for Linux/Windows/macOS.
- **Acceptance:** `pytest -q` green on a fresh venv.

### 4.2 — Host: integration test with a loopback serial
- **Why:** catches open/close/timeout regressions.
- **Files:** `host/tests/test_loopback.py`.
- **Plan:** `pyserial`'s `serial.Serial('loop://')` or a `socat`-based fixture (Linux only; mark `skipif` on Win/macOS).
- **Acceptance:** open → write → read → close, 100 iterations, no resource leak.

### 4.3 — Tufty: a host-side "shadow" parser
- **Why:** can't easily unit-test MicroPython on the dev box.
- **Files:** `host/tests/test_tufty_protocol_compat.py`.
- **Plan:** a pure-Python re-implementation of the Tufty parser (same field names, same case rules) tested against host-emitted frames. Catches drift when only one side changes.
- **Acceptance:** every frame `sender.py` produces is accepted by the shadow parser.

### 4.4 — CI (GitHub Actions)
- **Why:** no CI at all today.
- **Files:** `.github/workflows/ci.yml`.
- **Plan:**
  - `setup-python` + `pytest` for the host package.
  - `ruff` (or `flake8`) lint pass on `host/` (skip `tufty/` — MicroPython tooling is different).
  - Cache `~/.cache/pip`.
- **Acceptance:** green on every PR; red on lint or test failure.

### 4.5 — `mypy` / type hints
- **Why:** `sender.py` is untyped; the protocol is the kind of thing that benefits from `TypedDict`/`dataclass`.
- **Files:** `host/`.
- **Plan:** add annotations, run `mypy --strict` on `host/` only (tufty/ excluded).
- **Acceptance:** `mypy` clean; no runtime behaviour change.

---

## 5. Tooling & DX

### 5.1 — `Makefile` (or `justfile`)
- **Why:** every dev runs the same 5 commands.
- **Files:** `Makefile` at repo root.
- **Plan:**
  - `make venv` → `setup_env.sh`
  - `make run PORT=/dev/ttyACM0` → foreground sender with `--debug`
  - `make service-install` / `service-remove` / `service-status`
  - `make upload` → `mpremote cp tufty/main.py :main.py`
  - `make test`, `make lint`
- **Acceptance:** a new dev can go from `git clone` to "running on hardware" in < 5 min with only `make` + `make run`.

### 5.2 — `setup_env.sh` / systemd consistency
- **Why:** **the script does not install the unit, but `docs/setup_guide.md` says it does.** Pick the truth.
- **Files:** `host/setup_env.sh`, `host/tufty-monitor.service`, `docs/setup_guide.md`.
- **Plan (recommended):**
  - Script *does* install: `systemctl daemon-reload && systemctl enable --now tufty-monitor` (guarded by `command -v systemctl`).
  - On non-systemd (Windows/macOS), print a friendly skip message.
  - Add a `--no-service` flag for headless/CI.
- **Acceptance:** on a fresh Pi, `./setup_env.sh` → service is active within 30 s, no manual unit edits.

### 5.3 — `pyproject.toml` (host)
- **Why:** `requirements.txt`-only is fine for the service, but a proper package helps tests, lint config, and future `pipx`-style installs.
- **Files:** `host/pyproject.toml`, drop `requirements.txt` in favour of `[project.dependencies]`.
- **Plan:** `setuptools` or `hatchling` backend, single package `tufty-monitor`.
- **Acceptance:** `pip install -e ./host` works; `pytest` discovers tests.

### 5.4 — `pre-commit` (optional)
- **Why:** cheap lint gate.
- **Files:** `.pre-commit-config.yaml`.
- **Plan:** `ruff`, `ruff-format`, `mypy` (host only), `prettier` on `*.md` (README + docs).
- **Acceptance:** `pre-commit run --all-files` green.

### 5.5 — `.env` decision
- **Why:** `.env` is in the tree, not gitignored, and unused by code.
- **Files:** `.gitignore`, `host/.env.example`, README.
- **Plan:**
  - Create `.env.example` with the values the code actually reads (offset, baud, sync interval, disk mount, iface overrides — see 2.4).
  - `.gitignore` the real `.env`.
  - Remove the stray root `.env` or convert it to `.env.example`.
- **Acceptance:** fresh clone → no `.env` committed; `cp .env.example .env` → works.

### 5.6 — `tufty/` deploy helper
- **Why:** uploading `main.py` is manual (`mpremote` or Thonny).
- **Files:** `tufty/deploy.sh` (or a `make upload` target).
- **Plan:**
  - `mpremote fs ls` sanity check.
  - `mpremote cp tufty/main.py :main.py`.
  - `mpremote reset` + tail the REPL for 5 s to confirm boot.
- **Acceptance:** one command, works on Linux/Win/macOS.

---

## 6. Docs & ops

### 6.1 — README protocol section: make it normative
- **Why:** the README shows the frames but the parse rules (case, float coercion, `ETH`/`WIFI` as strings) only live in code.
- **Files:** `README.md`.
- **Plan:** a small table: field, type, units, example, notes. Link to `protocol.py` once 2.1 lands.
- **Acceptance:** a new contributor can implement a third client (e.g. an MQTT bridge) from the README alone.

### 6.2 — `docs/architecture.md`
- **Why:** the two-process + serial model is the crux of the project and currently only implicit.
- **Files:** `docs/architecture.md`.
- **Plan:** one diagram (mermaid), a paragraph on why the protocol is string-based, and a "what runs where" table.
- **Acceptance:** a new contributor can explain the system to someone else in 5 min.

### 6.3 — Troubleshooting section
- **Why:** `docs/setup_guide.md` covers install only; no "it doesn't work" path.
- **Files:** `docs/setup_guide.md`.
- **Plan:**
  - "Tufty shows COMM FAILURE after 5 s" → port, baud, USB cable, `lsusb` VID 0x2E8A.
  - "Host sees no port" → `ls /dev/ttyACM*`, udev rules on some distros.
  - "Wrong IP" → 1.6, `--eth-iface`.
  - "Service won't start" → `journalctl -u tufty-monitor -n 50`.
- **Acceptance:** each symptom → ≤ 5 steps to a working state.

### 6.4 — `docs/operations.md` (systemd)
- **Why:** the service unit is the main deployment target and the current docs split the info across README + setup_guide + the unit file itself.
- **Files:** `docs/operations.md`.
- **Plan:** install / uninstall / logs / rotate / upgrade (one-liner `git pull && systemctl restart tufty-monitor`) / resource limits (`CPUShares`? probably not needed).
- **Acceptance:** a Pi can be re-imaged and brought to "service active" with one link.

### 6.5 — Asset hygiene
- **Why:** `assets/*.png` are project photos; the README references some but not all, and the PDF in `docs/` is the only "real" documentation.
- **Files:** `assets/`, `README.md`.
- **Plan:**
  - One canonical hero image in README; the rest in a `docs/gallery/` (or keep in `assets/` but captioned).
  - Re-export the PDF as Markdown if the content is stable (or keep the PDF, it's fine).
- **Acceptance:** no orphan PNGs; every referenced image exists.

---

## 7. Feature ideas (post-stabilization)

> These are **not** on the critical path. Order them after §1–§4 are green.

- **7.1 — Alerts screen:** on the Tufty, a dedicated screen for "top 5 processes by CPU" or "biggest recent RAM spike" — host sends an `ALERT:` frame when a threshold crosses.
- **7.2 — Network detail screen:** per-interface RX/TX rates (host computes deltas; Tufty renders two small sparklines — watch RAM).
- **7.3 — Multi-host:** accept two serial lines (two Pis) and render side-by-side. Protocol gets a `HOST:<id>` prefix.
- **7.4 — Wi-Fi AP mode on the Tufty:** the Tufty becomes a small AP; host pushes over a local socket instead of serial (kills the USB dependency, adds latency).
- **7.5 — `tufty/` as a pip-installable MicroPython package:** vendor `picographics`/`pimoroni` into `tufty/vendor/` so the firmware is self-contained and version-pinned.
- **7.6 — Web dashboard (optional, separate repo):** a small FastAPI + WebSocket bridge that also reads the serial frames; same protocol, second consumer.

---

## Suggested issue ordering (one PR each, ~1–2 days apiece)

| # | Item | Section | Risk |
|---|------|---------|------|
| ~~1~~ | ~~1.1 Time-sync frame split~~ | ~~protocol~~ | ~~low~~ | ✅ #14 |
| ~~2~~ | ~~1.2 Heartbeat / liveness~~ | ~~protocol~~ | ~~low~~ | ✅ #15 |
| 3 | 1.3 SEQ or CRC frame integrity | protocol | low |
| 4 | 2.1 Package split (host) | code | low |
| 5 | 2.2 Structured logging | code | low |
| 6 | 2.3 SIGTERM / clean shutdown | code | low |
| 7 | 4.1 pytest + FakeSerial | tests | low |
| 8 | 4.4 CI (Actions) | tests | low |
| 9 | 5.2 setup_env.sh ↔ docs consistency | tooling | low |
| 10 | 5.5 `.env` decision | tooling | low |
| 11 | 1.5 / 1.6 disk + IP configurability | features | med |
| ~~12~~ | ~~3.1 Tufty state machine~~ | ~~code~~ | ~~med~~ | ✅ #12 |
| ~~13~~ | ~~3.2 Tufty data model~~ | ~~code~~ | ~~med~~ | ✅ #12 (bundled) |
| 14 | 4.3 shadow parser test | tests | med |
| 15 | 2.5 / 2.4 pinning + config | code | med |
| 16 | 4.5 mypy + 5.3 pyproject | code | low |
| 17 | 6.1–6.4 docs pass | docs | low |
| 18 | 5.1 Makefile + 5.6 tufty deploy helper | tooling | low |
| 19 | 3.3 Battery / 3.4 SHUTDOWN frame | features | low |
| ~~20~~ | ~~3.5 / 3.6 memory audit + debounce~~ | ~~code~~ | ~~low~~ | ✅ #12 (bundled) |

---

## Explicit non-goals (for future agents)
- Don't move the host sender to Go/Rust/C — the value is in keeping it in Python so the protocol is trivially readable.
- Don't add a database or a cloud layer to the default path — the product is a local USB monitor.
- Don't change the protocol to JSON or binary without a §1.x issue that documents the migration.
- Don't introduce a second display backend (e.g. e-ink) — the Tufty 2040 is the hardware target.
- Don't rename `sender.py` or move `tufty/main.py` without updating the systemd unit, `setup_env.sh`, and the README in the same PR.
