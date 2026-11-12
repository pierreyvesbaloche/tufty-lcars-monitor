import gc
import sys
import time

# 1. MEMORY OPTIMIZATION BEFORE IMPORTS
gc.collect()

import micropython
micropython.alloc_emergency_exception_buf(100)

from machine import ADC, Pin, RTC

gc.collect()
from picographics import PicoGraphics, DISPLAY_TUFTY_2040, PEN_P4
from pimoroni import Button

def log_debug(msg):
    gc.collect()
    free_ram = gc.mem_free()
    alloc_ram = gc.mem_alloc()
    print(f"[DEBUG][RAM Free: {free_ram} B | Alloc: {alloc_ram} B] -> {msg}")

log_debug("Initializing system...")

# ==============================================================================
# 1. HARDWARE & BUTTONS INITIALIZATION
# ==============================================================================
display = None
try:
    gc.collect()
    display = PicoGraphics(display=DISPLAY_TUFTY_2040, pen_type=PEN_P4)
    rtc = RTC()

    # Light sensor (ADC 26) + shared GPIO 27.
    # NOTE: GPIO 27 is shared with the battery voltage-reference mux
    # (see BATTERY section below). `lux_pwr` is the *default* state
    # (lux enabled); the battery reader briefly asserts the pin LOW
    # around each VREF read, then restores this value. Do not drive
    # GPIO 27 to a fixed value from anywhere else in this file.
    lux_pwr = Pin(27, Pin.OUT)
    lux_pwr.value(1)
    lux_sensor = ADC(26)

    # Tufty 2040 Buttons
    btn_a    = Button(7, invert=False)
    btn_b    = Button(8, invert=False)
    btn_c    = Button(9, invert=False)
    btn_up   = Button(22, invert=False)
    btn_down = Button(6, invert=False)

    log_debug("Hardware and buttons initialized successfully!")
except Exception as e:
    print(f"[CRITICAL ERROR] Hardware init failed: {e}")

if display is None:
    sys.exit()

import select

# ------------------------------------------------------------------------------
# SCREEN TABLE (3.1)
# ------------------------------------------------------------------------------
# Logical screen ids. `STATS` is the default landing screen.
SCREEN_STATS = 0
SCREEN_CLOCK = 1
CURRENT_SCREEN = SCREEN_STATS

# ------------------------------------------------------------------------------
# TELEMETRY DATA MODEL (3.2)
# ------------------------------------------------------------------------------
# Replaces the previous flat `last_data` dict. Numeric fields are floats;
# string fields (eth/wifi) stay as strings. `ts` is the time.time() stamp of
# the frame the host sent. The Tufty is the only writer to this object; the
# draw functions only read from it.
TELEMETRY = {
    "cpu": 0.0,
    "ram_pct": 0.0,
    "ram_u": 0.0,
    "ram_t": 0.0,
    "disk_pct": 0.0,
    "disk_u": 0.0,
    "disk_t": 0.0,
    "eth": "N/A",
    "wifi": "N/A",
    "ts": 0.0,
}

# ------------------------------------------------------------------------------
# SHARED UI STATE (3.1 / 3.6)
# ------------------------------------------------------------------------------
auto_brightness = True
manual_brightness = 0.8
current_brightness = 0.8
last_lux_print = 0
has_received_data = False
last_rx_time = 0
TIMEOUT_SECONDS = 5

# ------------------------------------------------------------------------------
# BUTTON DEBOUNCE (3.6)
# ------------------------------------------------------------------------------
# 15 ms per-edge debounce: a press has to hold for 15 ms before it is accepted,
# and a release has to hold for 15 ms before the button is considered free.
# This kills single-frame glitches (100 Hz main loop → 10 ms per tick) and
# accidental mode flips, without eating real short presses.
# (Was 30 ms; reduced after field test showed button presses not registering.)
DEBOUNCE_MS = 15
_btn_states = {
    "a":    {"cur": False, "prev": False, "t": 0},
    "b":    {"cur": False, "prev": False, "t": 0},
    "c":    {"cur": False, "prev": False, "t": 0},
    "up":   {"cur": False, "prev": False, "t": 0},
    "down": {"cur": False, "prev": False, "t": 0},
}
_btn_objects = {
    "a": btn_a, "b": btn_b, "c": btn_c, "up": btn_up, "down": btn_down,
}

# ==============================================================================
# 2. LCARS COLOR PALETTE (PEN_P4)
# ==============================================================================
BLACK       = display.create_pen(8, 10, 18)
WHITE       = display.create_pen(240, 245, 255)
CYAN_MAIN   = display.create_pen(0, 220, 210)
CYAN_DARK   = display.create_pen(0, 60, 70)
PURPLE_MAIN = display.create_pen(170, 90, 230)
PURPLE_DARK = display.create_pen(50, 25, 75)
BLUE_LCARS  = display.create_pen(60, 130, 240)
GRAY_TEXT   = display.create_pen(140, 160, 190)
ORANGE_AUTO = display.create_pen(255, 140, 0)
GOLD_LCARS  = display.create_pen(240, 180, 40)

# Alert colors
ORANGE_WARN = display.create_pen(255, 120, 0)  # Amber >= 80%
RED_ALERT   = display.create_pen(255, 30, 30)   # Red >= 90%

# Battery icon colors (3.3). GREEN_BAT reuses the existing CYAN_MAIN pen
# (no new pen — PEN_P4 is at the 16-color cap); RED_ALERT is reused for
# the low-battery state.
GREEN_BAT = CYAN_MAIN

log_debug("Color palette initialized.")

# ==============================================================================
# 2b. BATTERY / POWER (3.3)
# ==============================================================================
# The Tufty 2040 can run off USB, AAA/AA battery pack (JST-PH), or an
# optional LiPo. Battery voltage is measured on ADC 29 with an onboard
# voltage-reference mux on GPIO 27 (shared with the lux sensor — see the
# NOTE in the hardware init block above).
#
# IMPORTANT: there is NO Pimoroni `BATTERY` / fuel-gauge class in the
# Pimoroni MicroPython firmware for the Tufty 2040. The `pimoroni.py`
# module only ships `Button`, `Analog`, `AnalogMux`, `LED`, `RGBLED`.
# The official `battery.py` example (micropython/examples/tufty2040/
# battery.py) implements the measurement inline using raw ADC/Pin.
# We do the same here, adapted for shared-GPIO-27 and PEN_P4.
#
# The icon is *informational only* — it does not drive brightness,
# alerts, or any other behaviour. If the measurement fails (no battery
# connected, or the vref mux is busy), the icon simply does not render.

# Battery full/empty reference voltages. Default to the Pimoroni example
# values for a Galleon 400 mAh LiPo; adjust for your cell if needed.
BATT_FULL_V = 3.7
BATT_EMPTY_V = 2.5
BATT_LOW_PCT = 20          # icon goes red at/below this
BATT_REFRESH_S = 2.0       # re-measure every 2 s (main-loop gated)

battery_pct = -1           # -1 = "no battery / unknown" (icon hidden)
last_batt_refresh = 0

# ADC 29 = battery voltage input, ADC 28 = vref divider readout.
# GPIO 27 = vref enable (shared with lux sensor — see NOTE above).
# GPIO 24 = USB VBUS detect (1 = USB power connected).
try:
    vbat_adc = ADC(29)
    vref_adc = ADC(28)
    vref_en  = Pin(27, Pin.OUT)
    vref_en.value(0)        # start with vref OFF (lux sensor works)
    usb_detect = Pin(24, Pin.IN)
except Exception as e:
    print(f"[BATT INIT WARN] {e} — battery icon disabled")
    vbat_adc = None
    vref_adc = None
    vref_en  = None
    usb_detect = None

def refresh_battery():
    """Measure battery voltage and update `battery_pct`. Call at most
    once per `BATT_REFRESH_S` seconds (main-loop gated).

    Returns the new percentage (0-100) or -1 if no battery is
    connected / measurement failed. The GPIO 27 vref-enable pin is
    asserted LOW around the read, then restored to its previous
    value (1 = lux enabled) so the auto-brightness path keeps working.
    """
    global battery_pct
    if vbat_adc is None:
        return -1
    try:
        # GPIO 27 is shared: capture current value, assert vref (LOW),
        # read, restore. The lux sensor sees a ~1 ms glitch per
        # refresh, which is invisible at the 2 s refresh rate.
        prev = vref_en.value()
        vref_en.value(0)
        vdd  = 1.24 * (65535 / vref_adc.read_u16())
        vbat = (vbat_adc.read_u16() / 65535) * 3 * vdd   # 3 = ADC gain
        vref_en.value(prev)

        # Heuristic: no battery → vbat reads ~0 V.
        if vbat < 1.0:
            battery_pct = -1
            return -1

        pct = 100 * ((vbat - BATT_EMPTY_V) / (BATT_FULL_V - BATT_EMPTY_V))
        battery_pct = int(max(0, min(100, pct)))
        return battery_pct
    except Exception as e:
        print(f"[BATT ERROR] {e}")
        battery_pct = -1
        return -1

def draw_battery_icon(x, y, w, h):
    """Draw a small battery outline + fill at (x, y) with size (w, h).

    Pen budget (PEN_P4, 16 pens max — already at cap):
      outline  -> GRAY_TEXT   (reused)
      fill     -> CYAN_MAIN   (reused, alias GREEN_BAT) when pct > 20
      fill     -> RED_ALERT   (reused) when pct <= 20
      USB bolt -> GOLD_LCARS  (reused, drawn only when USB is connected)
    No new pens are created; the 16-pen cap is respected.
    """
    # Outline (hollow)
    display.set_pen(GRAY_TEXT)
    display.rectangle(x, y, w, h)
    display.set_pen(BLACK)
    display.rectangle(x + 2, y + 2, w - 4, h - 4)
    # Nub (the little + terminal on the right)
    display.set_pen(GRAY_TEXT)
    display.rectangle(x + w, y + h // 4, 3, h // 2)

    if battery_pct < 0:
        return                       # no battery -> outline only

    # Fill
    fill_pen = RED_ALERT if battery_pct <= BATT_LOW_PCT else GREEN_BAT
    fill_w = int((battery_pct / 100.0) * (w - 4))
    if fill_w > 0:
        display.set_pen(fill_pen)
        display.rectangle(x + 2, y + 2, fill_w, h - 4)

    # USB bolt (top-right of the icon) when USB is connected
    if usb_detect is not None and usb_detect.value() == 1:
        display.set_pen(GOLD_LCARS)
        display.rectangle(x + w - 6, y - 3, 2, 6)
        display.rectangle(x + w - 8, y - 1, 2, 2)


# ==============================================================================
# 3. UTILITY FUNCTIONS & BRIGHTNESS CONTROL
# ==============================================================================
def clear_screen():
    display.set_pen(BLACK)
    display.clear()

def set_hardware_brightness(level_float):
    clamped = max(0.50, min(1.0, level_float))
    display.set_backlight(clamped)

def update_backlight():
    global current_brightness, last_lux_print
    if auto_brightness:
        try:
            lux_pwr.value(1)
            raw_lux = lux_sensor.read_u16()

            min_adc = 300
            max_adc = 5000

            clamped_adc = max(min_adc, min(max_adc, raw_lux))
            target = 0.50 + ((clamped_adc - min_adc) / (max_adc - min_adc)) * 0.50

            current_brightness = current_brightness + (target - current_brightness) * 0.3

            now_sec = time.time()
            # Log lux only every 30 seconds to avoid overflowing serial buffer
            if now_sec - last_lux_print >= 30:
                print(f"[AUTO-LUX] Raw ADC: {raw_lux} | Target: {target:.2f} | Brightness: {current_brightness:.2f}")
                last_lux_print = now_sec

        except Exception as e:
            print(f"[LUX ERROR] Sensor read failed: {e}")
            current_brightness = 0.8
    else:
        current_brightness = manual_brightness

    set_hardware_brightness(current_brightness)

# ------------------------------------------------------------------------------
# BUTTON SAMPLING + DEBOUNCING (3.6)
# ------------------------------------------------------------------------------
# Poll each physical button, fold the 30 ms debounce, and return a set of
# *newly-pressed* logical buttons. The main loop calls this once per tick;
# the returned names are dispatched by `_on_button()`.
def _sample_buttons():
    """Poll every physical button, fold the edge-hold debounce, and return
    the list of names that transitioned to *pressed* this tick.

    The Pimoroni `Button` class already applies its own internal filtering;
    this layer adds a `DEBOUNCE_MS` edge-hold on top, which is what kills
    single-frame glitches at the 100 Hz main-loop cadence.
    """
    out = []
    now_ms = time.ticks_ms()
    for name, obj in _btn_objects.items():
        st = _btn_states[name]
        raw = bool(obj.is_pressed)
        if raw != st["cur"]:
            if time.ticks_diff(now_ms, st["t"]) >= DEBOUNCE_MS:
                st["cur"] = raw
                st["t"] = now_ms
                if raw:
                    out.append(name)
            else:
                # Edge seen, but not held long enough — restart the timer.
                st["t"] = now_ms
        st["prev"] = raw
    return out

def _on_button(name):
    """Apply the action for a single debounced press. Returns True if the UI
    changed as a result (drives the main-loop redraw flag)."""
    global auto_brightness, manual_brightness, CURRENT_SCREEN
    changed = False

    if name == "a":
        if CURRENT_SCREEN != SCREEN_STATS:
            CURRENT_SCREEN = SCREEN_STATS
            changed = True
            time.sleep(0.15)
    elif name == "b":
        if CURRENT_SCREEN != SCREEN_CLOCK:
            CURRENT_SCREEN = SCREEN_CLOCK
            changed = True
            time.sleep(0.15)
    elif name == "c":
        auto_brightness = not auto_brightness
        print(f"[MODE] Switched -> AUTO Mode: {auto_brightness}")
        update_backlight()
        changed = True
        time.sleep(0.2)
    elif name == "up":
        auto_brightness = False
        manual_brightness = min(1.0, round(manual_brightness + 0.1, 1))
        update_backlight()
        changed = True
        time.sleep(0.15)
    elif name == "down":
        auto_brightness = False
        manual_brightness = max(0.50, round(manual_brightness - 0.1, 1))
        update_backlight()
        changed = True
        time.sleep(0.15)

    return changed

def handle_buttons():
    """Sample all buttons, debounce, dispatch. Returns True if any UI changed."""
    changed = False
    for name in _sample_buttons():
        if _on_button(name):
            changed = True
    return changed

def sync_rtc(time_str):
    """Synchronizes RP2040 RTC from formatted string 'YYYY,MM,DD,HH,MM,SS'."""
    try:
        parts = [int(p) for p in time_str.split(',')]
        year, month, day, hour, minute, second = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]

        now = rtc.datetime()
        # Adjust only if there is a discrepancy in hour, minute, or >= 2 seconds
        if abs(now[4] - hour) >= 1 or abs(now[5] - minute) >= 1 or abs(now[6] - second) >= 2:
            # RP2040 Tuple: (year, month, day, weekday, hour, minute, second, subsecond)
            rtc.datetime((year, month, day, 0, hour, minute, second, 0))
            print(f"[RTC SYNC] Drift corrected. RTC set to {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")
    except Exception as e:
        print(f"[RTC ERROR] Sync failed: {e}")

def get_gauge_color(pct, default_color):
    if pct >= 90:
        return RED_ALERT
    elif pct >= 80:
        return ORANGE_WARN
    return default_color

def draw_horizontal_bar(x, y, w, h, pct, color_fg, color_bg):
    display.set_pen(color_bg)
    display.rectangle(x, y, w, h)

    fill_w = int((min(max(pct, 0), 100) / 100.0) * w)
    if fill_w > 0:
        active_color = get_gauge_color(pct, color_fg)
        display.set_pen(active_color)
        display.rectangle(x, y, fill_w, h)

def draw_button_labels():
    # Button A (STATS) - x = 55
    if CURRENT_SCREEN == SCREEN_STATS:
        display.set_pen(GOLD_LCARS)
        display.text("STATS", 55, 228, scale=1)
        display.rectangle(55, 238, 40, 2)
    else:
        display.set_pen(GRAY_TEXT)
        display.text("STATS", 55, 228, scale=1)

    # Button B (CLOCK) - x = 145
    if CURRENT_SCREEN == SCREEN_CLOCK:
        display.set_pen(GOLD_LCARS)
        display.text("CLOCK", 145, 228, scale=1)
        display.rectangle(145, 238, 40, 2)
    else:
        display.set_pen(GRAY_TEXT)
        display.text("CLOCK", 145, 228, scale=1)

    # Button C (LIGHT) - x = 235
    if not auto_brightness:
        display.set_pen(ORANGE_AUTO)
        display.text("LIGHT", 235, 228, scale=1)
        display.rectangle(235, 238, 40, 2)
    else:
        display.set_pen(GRAY_TEXT)
        display.text("LIGHT", 235, 228, scale=1)

# ------------------------------------------------------------------------------
# BATTERY ICON PLACEMENT (3.3)
# ------------------------------------------------------------------------------
# Top-right corner, just left of the mode string (which starts at x=200).
# 24x12 px outline; fill width tracks `battery_pct`.
def draw_battery_icon_on_screen():
    draw_battery_icon(170, 5, 24, 12)

# ==============================================================================
# 4. LCARS VIEWS
# ==============================================================================
def draw_waiting_screen():
    clear_screen()

    display.set_pen(ORANGE_AUTO if auto_brightness else GRAY_TEXT)
    mode_str = f"AUTO {int(current_brightness*100)}%" if auto_brightness else f"MAN {int(current_brightness*100)}%"
    display.text(mode_str, 200, 5, scale=1)

    display.set_pen(GOLD_LCARS)
    display.rectangle(15, 15, 30, 200)
    display.set_pen(BLACK)
    display.rectangle(15, 65, 30, 10)
    display.rectangle(15, 140, 30, 10)

    display.set_pen(ORANGE_WARN)
    display.text("SYSTEM STANDBY", 60, 30, scale=3)

    display.set_pen(CYAN_MAIN)
    display.text("AWAITING DATA FROM", 60, 80, scale=2)
    display.text("COMPUTER...", 60, 110, scale=2)

    display.set_pen(GRAY_TEXT)
    display.text("SERIAL ACTIVE", 60, 160, scale=2)

    draw_battery_icon_on_screen()
    draw_button_labels()
    display.update()

def draw_connection_lost_screen():
    clear_screen()

    display.set_pen(ORANGE_AUTO if auto_brightness else GRAY_TEXT)
    mode_str = f"AUTO {int(current_brightness*100)}%" if auto_brightness else f"MAN {int(current_brightness*100)}%"
    display.text(mode_str, 200, 5, scale=1)

    display.set_pen(RED_ALERT)
    display.rectangle(15, 15, 30, 200)
    display.set_pen(BLACK)
    display.rectangle(15, 65, 30, 10)
    display.rectangle(15, 140, 30, 10)

    display.set_pen(RED_ALERT)
    display.text("COMM FAILURE", 60, 30, scale=3)

    display.set_pen(ORANGE_WARN)
    display.text("CONNECTION LOST", 60, 80, scale=2)
    display.text("COMPUTER OFFLINE", 60, 110, scale=2)

    display.set_pen(GRAY_TEXT)
    display.text("RETRYING SERIAL...", 60, 160, scale=2)

    draw_battery_icon_on_screen()
    draw_button_labels()
    display.update()

def draw_screen_metrics(d):
    if not has_received_data:
        draw_waiting_screen()
        return

    if time.time() - last_rx_time > TIMEOUT_SECONDS:
        draw_connection_lost_screen()
        return

    clear_screen()

    display.set_pen(ORANGE_AUTO if auto_brightness else GRAY_TEXT)
    mode_str = f"AUTO {int(current_brightness*100)}%" if auto_brightness else f"MAN {int(current_brightness*100)}%"
    display.text(mode_str, 200, 5, scale=1)

    # CPU
    display.set_pen(WHITE)
    display.text("CPU UTILIZATION", 20, 10, scale=2)
    cpu_pct = d["cpu"]
    draw_horizontal_bar(20, 30, 280, 15, cpu_pct, CYAN_MAIN, CYAN_DARK)
    display.set_pen(get_gauge_color(cpu_pct, CYAN_MAIN))
    display.text(f"{int(cpu_pct)}%", 260, 10, scale=2)

    # RAM
    ram_pct, ram_u, ram_t = d["ram_pct"], d["ram_u"], d["ram_t"]
    display.set_pen(WHITE)
    display.text("MEMORY", 20, 52, scale=2)
    display.set_pen(GRAY_TEXT)
    display.text(f"{ram_u:.1f}/{ram_t:.1f} GB", 115, 52, scale=2)
    display.set_pen(get_gauge_color(ram_pct, CYAN_MAIN))
    display.text(f"{int(ram_pct)}%", 260, 52, scale=2)
    draw_horizontal_bar(20, 72, 280, 15, ram_pct, CYAN_MAIN, CYAN_DARK)

    # DISK
    disk_pct, disk_u, disk_t = d["disk_pct"], d["disk_u"], d["disk_t"]
    display.set_pen(WHITE)
    display.text("DISK", 20, 95, scale=2)
    display.set_pen(GRAY_TEXT)
    display.text(f"{int(disk_u)}/{int(disk_t)} GB", 95, 95, scale=2)
    display.set_pen(get_gauge_color(disk_pct, PURPLE_MAIN))
    display.text(f"{int(disk_pct)}%", 260, 95, scale=2)
    draw_horizontal_bar(20, 115, 280, 15, disk_pct, PURPLE_MAIN, PURPLE_DARK)

    # NETWORK
    display.set_pen(BLUE_LCARS)
    display.rectangle(20, 142, 280, 3)
    display.set_pen(GRAY_TEXT)
    display.text(f"ETH:  {d['eth']}", 20, 155, scale=2)
    display.text(f"WIFI: {d['wifi']}", 20, 180, scale=2)

    draw_battery_icon_on_screen()
    draw_button_labels()
    display.update()

def draw_screen_clock():
    clear_screen()

    display.set_pen(ORANGE_AUTO if auto_brightness else GRAY_TEXT)
    mode_str = f"AUTO {int(current_brightness*100)}%" if auto_brightness else f"MAN {int(current_brightness*100)}%"
    display.text(mode_str, 200, 5, scale=1)

    display.set_pen(GOLD_LCARS)
    display.rectangle(15, 15, 30, 200)
    display.set_pen(BLACK)
    display.rectangle(15, 55, 30, 8)
    display.rectangle(15, 145, 30, 8)

    # DIRECT READ FROM HARDWARE RTC (RP2040)
    now = rtc.datetime()
    year, month, day = now[0], now[1], now[2]
    weekday = now[3]
    h, m, s = now[4], now[5], now[6]

    days_names = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    day_str = days_names[weekday] if 0 <= weekday < 7 else "DAY"

    time_str = f"{h:02d}:{m:02d}:{s:02d}"
    display.set_pen(CYAN_MAIN)
    display.text(time_str, 60, 45, scale=5)

    date_str = f"{day_str}  {day:02d}/{month:02d}/{year}"
    display.set_pen(PURPLE_MAIN)
    display.text(date_str, 60, 115, scale=3)

    stardate_str = f"STARDATE {year}.{month:02d}{day:02d}"
    display.set_pen(GRAY_TEXT)
    display.text(stardate_str, 60, 165, scale=2)

    draw_battery_icon_on_screen()
    draw_button_labels()
    display.update()

# ------------------------------------------------------------------------------
# SCREEN DISPATCH (3.1)
# ------------------------------------------------------------------------------
# The main loop used to branch on `current_screen` with an if/else. Centralising
# it here means adding a screen is: add a draw function + add a branch below.
# The `TELEMETRY` arg is only passed to screens that need it (the clock screen
# reads the RTC directly and takes no data argument).
def draw_current_screen():
    if CURRENT_SCREEN == SCREEN_CLOCK:
        draw_screen_clock()
    else:
        draw_screen_metrics(TELEMETRY)

# ==============================================================================
# 5. MAIN LOOP
# ==============================================================================
update_backlight()

draw_current_screen()

spoll = select.poll()
spoll.register(sys.stdin, select.POLLIN)

last_redraw = time.ticks_ms()
log_debug("Starting main loop.")

# 3.5 — startup headroom check. We want at least 8 KB of free heap before we
# start the main loop, otherwise a new screen will OOM the device.
if gc.mem_free() < 8192:
    print("[CRITICAL ERROR] Insufficient free heap (< 8 KB). Refusing to start main loop.")
    sys.exit()

while True:
    try:
        btn_changed = handle_buttons()

        if auto_brightness:
            update_backlight()

        data_received = False
        if spoll.poll(1):
            line = sys.stdin.readline()
            if line:
                try:
                    frame = {}
                    parts = line.strip().split('|')
                    for part in parts:
                        if ':' in part:
                            k, v = part.split(':', 1)

                            # Handle time sync payload
                            if k == "INIT_TIME":
                                sync_rtc(v)
                                continue

                            k_lower = k.lower()
                            if k_lower in ['eth', 'wifi']:
                                frame[k_lower] = v
                            else:
                                try:
                                    frame[k_lower] = float(v)
                                except ValueError:
                                    pass

                    if frame:
                        TELEMETRY.update(frame)
                        data_received = True
                        has_received_data = True
                        last_rx_time = time.time()
                except Exception:
                    pass

        now_ms = time.ticks_ms()

        # 3.3 — refresh the battery icon at most once per BATT_REFRESH_S.
        # Gated on `vbat_adc is not None` so a failed init (icon disabled)
        # costs zero cycles. The GPIO-27 vref assert is a ~1 ms glitch
        # on the lux sensor, invisible at the 2 s refresh rate.
        if vbat_adc is not None and time.time() - last_batt_refresh >= BATT_REFRESH_S:
            last_batt_refresh = time.time()
            refresh_battery()

        if btn_changed or data_received or time.ticks_diff(now_ms, last_redraw) >= 1000:
            draw_current_screen()
            last_redraw = now_ms
            gc.collect()

        time.sleep(0.01)

    except Exception as e:
        print(f"[LOOP ERROR] {e}")
        time.sleep(1)
