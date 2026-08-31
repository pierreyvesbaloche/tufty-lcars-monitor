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
# 1. HARDWARE & PIMORONI BUTTON INITIALIZATION
# ==============================================================================
display = None
try:
    gc.collect()
    display = PicoGraphics(display=DISPLAY_TUFTY_2040, pen_type=PEN_P4)
    rtc = RTC()

    # Tufty 2040 Light Sensor (ADC 26 + Power on GPIO 27)
    lux_pwr = Pin(27, Pin.OUT)
    lux_pwr.value(1)           # Power on phototransistor
    lux_sensor = ADC(26)       # Phototransistor on GPIO 26 / ADC 0

    # Tufty 2040 Buttons
    btn_a    = Button(7, invert=False)
    btn_b    = Button(8, invert=False)
    btn_c    = Button(9, invert=False)
    btn_up   = Button(22, invert=False)
    btn_down = Button(6, invert=False)    # GPIO 6 for DOWN

    log_debug("Hardware and buttons initialized successfully!")
except Exception as e:
    print(f"[CRITICAL ERROR] Hardware init failed: {e}")

if display is None:
    sys.exit()

import select

current_screen = 0
auto_brightness = True
manual_brightness = 0.8
current_brightness = 0.8
last_lux_print = 0
has_received_data = False  # Flag for initial boot state
last_rx_time = 0           # Timestamp of last valid serial packet
TIMEOUT_SECONDS = 5        # Timeout threshold to trigger connection lost screen

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

# Warning/Alert Colors
ORANGE_WARN = display.create_pen(255, 120, 0)  # Amber for >= 80%
RED_ALERT   = display.create_pen(255, 30, 30)   # Red for >= 90%

log_debug("Color palette initialized.")

# ==============================================================================
# 3. UTILITY FUNCTIONS & BACKLIGHT CONTROL
# ==============================================================================
def clear_screen():
    display.set_pen(BLACK)
    display.clear()

def set_hardware_brightness(level_float):
    """Adjusts backlight with a safe floor of 0.50 to avoid total blackout"""
    clamped = max(0.50, min(1.0, level_float))
    display.set_backlight(clamped)

def update_backlight():
    global current_brightness, last_lux_print
    if auto_brightness:
        try:
            lux_pwr.value(1)
            raw_lux = lux_sensor.read_u16()

            # Calibrated ADC range (300 to 5000)
            min_adc = 300
            max_adc = 5000

            clamped_adc = max(min_adc, min(max_adc, raw_lux))
            
            # Scales between 50% (darkness) and 100% (bright light)
            target = 0.50 + ((clamped_adc - min_adc) / (max_adc - min_adc)) * 0.50
            
            # Smooth transition
            current_brightness = current_brightness + (target - current_brightness) * 0.3

            # Console debug output (every 2 seconds)
            now_sec = time.time()
            if now_sec - last_lux_print >= 2:
                print(f"[AUTO-LUX] Raw ADC: {raw_lux} | Clamped: {clamped_adc} | Target: {target:.2f} | Brightness: {current_brightness:.2f}")
                last_lux_print = now_sec

        except Exception as e:
            print(f"[LUX ERROR] Sensor read failed: {e}")
            current_brightness = 0.8
    else:
        current_brightness = manual_brightness

    set_hardware_brightness(current_brightness)

def handle_buttons():
    global current_screen, auto_brightness, manual_brightness

    changed = False

    # Button A -> Metrics Screen
    if btn_a.is_pressed:
        if current_screen != 0:
            current_screen = 0
            changed = True
            time.sleep(0.15)

    # Button B -> Clock Screen
    elif btn_b.is_pressed:
        if current_screen != 1:
            current_screen = 1
            changed = True
            time.sleep(0.15)

    # Button C -> Toggle AUTO / MANUAL Mode
    elif btn_c.is_pressed:
        auto_brightness = not auto_brightness
        print(f"[MODE] Switched -> AUTO Mode: {auto_brightness}")
        update_backlight()
        changed = True
        time.sleep(0.2)

    # Button UP -> +10% Manual Brightness
    elif btn_up.is_pressed:
        auto_brightness = False
        manual_brightness = min(1.0, round(manual_brightness + 0.1, 1))
        update_backlight()
        changed = True
        time.sleep(0.15)

    # Button DOWN -> -10% Manual Brightness (Floor at 50%)
    elif btn_down.is_pressed:
        auto_brightness = False
        manual_brightness = max(0.50, round(manual_brightness - 0.1, 1))
        update_backlight()
        changed = True
        time.sleep(0.15)

    return changed

def sync_time(timestamp):
    if timestamp > 0:
        try:
            t = time.localtime(int(timestamp))
            rtc.datetime((t[0], t[1], t[2], t[6], t[3], t[4], t[5], 0))
        except Exception:
            pass

def get_gauge_color(pct, default_color):
    """Returns amber if >= 80% and red if >= 90%"""
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

# ==============================================================================
# 4. LCARS SCREENS
# ==============================================================================
def draw_waiting_screen():
    clear_screen()

    # Brightness Indicator
    display.set_pen(ORANGE_AUTO if auto_brightness else GRAY_TEXT)
    mode_str = f"AUTO {int(current_brightness*100)}%" if auto_brightness else f"MAN {int(current_brightness*100)}%"
    display.text(mode_str, 200, 5, scale=1)

    # LCARS Header Frame
    display.set_pen(GOLD_LCARS)
    display.rectangle(15, 15, 30, 210)
    display.set_pen(BLACK)
    display.rectangle(15, 70, 30, 10)
    display.rectangle(15, 150, 30, 10)

    # Status Message
    display.set_pen(ORANGE_WARN)
    display.text("SYSTEM STANDBY", 60, 35, scale=3)

    display.set_pen(CYAN_MAIN)
    display.text("AWAITING DATA FROM", 60, 90, scale=2)
    display.text("RASPBERRY PI...", 60, 120, scale=2)

    # Serial Status
    display.set_pen(GRAY_TEXT)
    display.text("SERIAL ACTIVE", 60, 175, scale=2)

    display.update()

def draw_connection_lost_screen():
    clear_screen()

    # Brightness Indicator
    display.set_pen(ORANGE_AUTO if auto_brightness else GRAY_TEXT)
    mode_str = f"AUTO {int(current_brightness*100)}%" if auto_brightness else f"MAN {int(current_brightness*100)}%"
    display.text(mode_str, 200, 5, scale=1)

    # Red LCARS Sidebar
    display.set_pen(RED_ALERT)
    display.rectangle(15, 15, 30, 210)
    display.set_pen(BLACK)
    display.rectangle(15, 70, 30, 10)
    display.rectangle(15, 150, 30, 10)

    # Alert Message
    display.set_pen(RED_ALERT)
    display.text("COMM FAILURE", 60, 35, scale=3)

    display.set_pen(ORANGE_WARN)
    display.text("CONNECTION LOST", 60, 90, scale=2)
    display.text("RASPBERRY PI OFFLINE", 60, 120, scale=2)

    display.set_pen(GRAY_TEXT)
    display.text("RETRYING SERIAL...", 60, 175, scale=2)

    display.update()

def draw_screen_metrics(d):
    if not has_received_data:
        draw_waiting_screen()
        return

    # Check connection timeout
    if time.time() - last_rx_time > TIMEOUT_SECONDS:
        draw_connection_lost_screen()
        return

    clear_screen()

    # Brightness Indicator
    display.set_pen(ORANGE_AUTO if auto_brightness else GRAY_TEXT)
    mode_str = f"AUTO {int(current_brightness*100)}%" if auto_brightness else f"MAN {int(current_brightness*100)}%"
    display.text(mode_str, 200, 5, scale=1)

    # CPU
    display.set_pen(WHITE)
    display.text("CPU UTILIZATION", 20, 10, scale=2)
    cpu_pct = d.get('cpu', 0)
    draw_horizontal_bar(20, 32, 280, 16, cpu_pct, CYAN_MAIN, CYAN_DARK)
    display.set_pen(get_gauge_color(cpu_pct, CYAN_MAIN))
    display.text(f"{int(cpu_pct)}%", 260, 10, scale=2)

    # RAM
    ram_pct, ram_u, ram_t = d.get('ram_pct', 0), d.get('ram_u', 0), d.get('ram_t', 0)
    display.set_pen(WHITE)
    display.text("MEMORY", 20, 58, scale=2)
    display.set_pen(GRAY_TEXT)
    display.text(f"{ram_u:.1f}/{ram_t:.1f} GB", 120, 58, scale=2)
    display.set_pen(get_gauge_color(ram_pct, CYAN_MAIN))
    display.text(f"{int(ram_pct)}%", 260, 58, scale=2)
    draw_horizontal_bar(20, 80, 280, 16, ram_pct, CYAN_MAIN, CYAN_DARK)

    # DISK
    disk_pct, disk_u, disk_t = d.get('disk_pct', 0), d.get('disk_u', 0), d.get('disk_t', 0)
    display.set_pen(WHITE)
    display.text("DISK", 20, 110, scale=2)
    display.set_pen(GRAY_TEXT)
    display.text(f"{int(disk_u)}/{int(disk_t)} GB", 95, 110, scale=2)
    display.set_pen(get_gauge_color(disk_pct, PURPLE_MAIN))
    display.text(f"{int(disk_pct)}%", 260, 110, scale=2)
    draw_horizontal_bar(20, 132, 280, 16, disk_pct, PURPLE_MAIN, PURPLE_DARK)

    # NETWORK
    display.set_pen(BLUE_LCARS)
    display.rectangle(20, 165, 280, 4)
    display.set_pen(GRAY_TEXT)
    display.text(f"ETH:  {d.get('eth', 'N/A')}", 20, 182, scale=2)
    display.text(f"WIFI: {d.get('wifi', 'N/A')}", 20, 208, scale=2)

    display.update()

def draw_screen_clock():
    clear_screen()

    # Brightness Indicator
    display.set_pen(ORANGE_AUTO if auto_brightness else GRAY_TEXT)
    mode_str = f"AUTO {int(current_brightness*100)}%" if auto_brightness else f"MAN {int(current_brightness*100)}%"
    display.text(mode_str, 200, 5, scale=1)

    display.set_pen(GOLD_LCARS)
    display.rectangle(15, 15, 30, 210)
    display.set_pen(BLACK)
    display.rectangle(15, 60, 30, 8)
    display.rectangle(15, 160, 30, 8)

    now = rtc.datetime()
    year, month, day, weekday = now[0], now[1], now[2], now[3]
    h, m, s = now[4], now[5], now[6]

    days_names = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    day_str = days_names[weekday] if 0 <= weekday < 7 else "DAY"

    time_str = f"{h:02d}:{m:02d}:{s:02d}"
    display.set_pen(CYAN_MAIN)
    display.text(time_str, 60, 55, scale=5)

    date_str = f"{day_str}  {day:02d}/{month:02d}/{year}"
    display.set_pen(PURPLE_MAIN)
    display.text(date_str, 60, 125, scale=3)

    stardate_str = f"STARDATE {year}.{month:02d}{day:02d}"
    display.set_pen(GRAY_TEXT)
    display.text(stardate_str, 60, 175, scale=2)

    display.update()

# ==============================================================================
# 5. MAIN LOOP
# ==============================================================================
update_backlight()

last_data = {}
draw_screen_metrics(last_data)

spoll = select.poll()
spoll.register(sys.stdin, select.POLLIN)

last_redraw = time.ticks_ms()
log_debug("Starting main loop.")

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
                    metrics = {}
                    parts = line.strip().split('|')
                    for part in parts:
                        if ':' in part:
                            k, v = part.split(':', 1)
                            k = k.lower()
                            if k in ['eth', 'wifi']:
                                metrics[k] = v
                            else:
                                try:
                                    metrics[k] = float(v)
                                except ValueError:
                                    pass
                    
                    if 'time' in metrics:
                        sync_time(metrics['time'])
                    
                    if metrics:
                        last_data = metrics
                        data_received = True
                        has_received_data = True
                        last_rx_time = time.time()  # Reset reception timer
                except Exception:
                    pass

        now_ms = time.ticks_ms()
        if btn_changed or data_received or time.ticks_diff(now_ms, last_redraw) >= 1000:
            if current_screen == 0:
                draw_screen_metrics(last_data)
            else:
                draw_screen_clock()
            last_redraw = now_ms
            gc.collect()

        time.sleep(0.01)

    except Exception as e:
        print(f"[LOOP ERROR] {e}")
        time.sleep(1)