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

    # Light sensor (ADC 26 + Power GPIO 27)
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

current_screen = 0
auto_brightness = True
manual_brightness = 0.8
current_brightness = 0.8
last_lux_print = 0
has_received_data = False 
last_rx_time = 0          
TIMEOUT_SECONDS = 5       

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

log_debug("Color palette initialized.")

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

def handle_buttons():
    global current_screen, auto_brightness, manual_brightness

    changed = False

    if btn_a.is_pressed:
        if current_screen != 0:
            current_screen = 0
            changed = True
            time.sleep(0.15)

    elif btn_b.is_pressed:
        if current_screen != 1:
            current_screen = 1
            changed = True
            time.sleep(0.15)

    elif btn_c.is_pressed:
        auto_brightness = not auto_brightness
        print(f"[MODE] Switched -> AUTO Mode: {auto_brightness}")
        update_backlight()
        changed = True
        time.sleep(0.2)

    elif btn_up.is_pressed:
        auto_brightness = False
        manual_brightness = min(1.0, round(manual_brightness + 0.1, 1))
        update_backlight()
        changed = True
        time.sleep(0.15)

    elif btn_down.is_pressed:
        auto_brightness = False
        manual_brightness = max(0.50, round(manual_brightness - 0.1, 1))
        update_backlight()
        changed = True
        time.sleep(0.15)

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
    if current_screen == 0:
        display.set_pen(GOLD_LCARS)
        display.text("STATS", 55, 228, scale=1)
        display.rectangle(55, 238, 40, 2)
    else:
        display.set_pen(GRAY_TEXT)
        display.text("STATS", 55, 228, scale=1)

    # Button B (CLOCK) - x = 145
    if current_screen == 1:
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
    cpu_pct = d.get('cpu', 0)
    draw_horizontal_bar(20, 30, 280, 15, cpu_pct, CYAN_MAIN, CYAN_DARK)
    display.set_pen(get_gauge_color(cpu_pct, CYAN_MAIN))
    display.text(f"{int(cpu_pct)}%", 260, 10, scale=2)

    # RAM
    ram_pct, ram_u, ram_t = d.get('ram_pct', 0), d.get('ram_u', 0), d.get('ram_t', 0)
    display.set_pen(WHITE)
    display.text("MEMORY", 20, 52, scale=2)
    display.set_pen(GRAY_TEXT)
    display.text(f"{ram_u:.1f}/{ram_t:.1f} GB", 115, 52, scale=2)
    display.set_pen(get_gauge_color(ram_pct, CYAN_MAIN))
    display.text(f"{int(ram_pct)}%", 260, 52, scale=2)
    draw_horizontal_bar(20, 72, 280, 15, ram_pct, CYAN_MAIN, CYAN_DARK)

    # DISK
    disk_pct, disk_u, disk_t = d.get('disk_pct', 0), d.get('disk_u', 0), d.get('disk_t', 0)
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
    display.text(f"ETH:  {d.get('eth', 'N/A')}", 20, 155, scale=2)
    display.text(f"WIFI: {d.get('wifi', 'N/A')}", 20, 180, scale=2)

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

    draw_button_labels()
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
                           
                            # Handle time sync payload
                            if k == "INIT_TIME":
                                sync_rtc(v)
                                continue
                               
                            k_lower = k.lower()
                            if k_lower in ['eth', 'wifi']:
                                metrics[k_lower] = v
                            else:
                                try:
                                    metrics[k_lower] = float(v)
                                except ValueError:
                                    pass
                   
                    if metrics:
                        last_data = metrics
                        data_received = True
                        has_received_data = True
                        last_rx_time = time.time()
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