#!/usr/bin/env python3
"""
Raspberry Pi Metric Collector & Serial Streamer for Tufty 2040 LCARS Monitor.
Gathers CPU, RAM, Disk usage, active IP addresses, and UNIX timestamp,
then streams formatted lines via Serial (USB).
"""

import time
import sys
import socket
import psutil
import serial
import serial.tools.list_ports

# Configuration
BAUD_RATE = 115200
SEND_INTERVAL = 1.0  # seconds between metric pushes


def find_tufty_port():
    """Auto-detects the Tufty 2040 / Pico serial port (/dev/ttyACM*)."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        # Check by device name pattern or USB Vendor/Product ID if needed
        if "ttyACM" in port.device or "Pico" in port.description or "Tufty" in port.description:
            return port.device
    
    # Fallback to standard Pico serial path on RPi if not matched by description
    if ports:
        return ports[0].device
    return None


def get_ip_address(interface_prefix):
    """Retrieves the IPv4 address for a given network interface prefix (e.g. 'eth', 'wlan')."""
    try:
        interfaces = psutil.net_if_addrs()
        for iface_name, addrs in interfaces.items():
            if iface_name.startswith(interface_prefix):
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        return addr.address
    except Exception:
        pass
    return "N/A"


def gather_metrics():
    """Collects current system metrics and formats them for the Tufty 2040 display."""
    # CPU percentage (over a 0.2s interval)
    cpu_pct = psutil.cpu_percent(interval=0.2)

    # RAM stats (converted to GB)
    ram = psutil.virtual_memory()
    ram_pct = ram.percent
    ram_used_gb = ram.used / (1024 ** 3)
    ram_total_gb = ram.total / (1024 ** 3)

    # Disk stats for root '/' (converted to GB)
    disk = psutil.disk_usage('/')
    disk_pct = disk.percent
    disk_used_gb = disk.used / (1024 ** 3)
    disk_total_gb = disk.total / (1024 ** 3)

    # Network IPs
    eth_ip = get_ip_address('eth')
    if eth_ip == "N/A":
        eth_ip = get_ip_address('enp')  # Fallback for alternative ethernet naming conventions

    wifi_ip = get_ip_address('wlan')
    if wifi_ip == "N/A":
        wifi_ip = get_ip_address('wlp')  # Fallback for alternative wifi naming conventions

    # Current epoch timestamp for Tufty RTC sync
    timestamp = int(time.time())

    # Format line: CPU:val|RAM_PCT:val|RAM_U:val|RAM_T:val|...|TIME:val\n
    payload = (
        f"CPU:{cpu_pct:.1f}|"
        f"RAM_PCT:{ram_pct:.1f}|"
        f"RAM_U:{ram_used_gb:.1f}|"
        f"RAM_T:{ram_total_gb:.1f}|"
        f"DISK_PCT:{disk_pct:.1f}|"
        f"DISK_U:{disk_used_gb:.1f}|"
        f"DISK_T:{disk_total_gb:.1f}|"
        f"ETH:{eth_ip}|"
        f"WIFI:{wifi_ip}|"
        f"TIME:{timestamp}\n"
    )
    return payload


def main():
    print("[INFO] Starting Tufty 2040 LCARS Telemetry Sender...")
    
    ser = None
    while True:
        try:
            # Reconnect loop
            if ser is None or not ser.is_open:
                port_path = find_tufty_port()
                if not port_path:
                    print("[WARN] Tufty 2040 not detected. Retrying in 3 seconds...")
                    time.sleep(3)
                    continue

                print(f"[INFO] Connecting to serial port: {port_path} at {BAUD_RATE} baud...")
                ser = serial.Serial(port_path, BAUD_RATE, timeout=2)
                time.sleep(1)  # Brief pause after opening port
                print("[SUCCESS] Serial connection established!")

            # Collect and transmit payload
            payload = gather_metrics()
            ser.write(payload.encode('utf-8'))
            ser.flush()
            
            time.sleep(SEND_INTERVAL)

        except (serial.SerialException, OSError) as e:
            print(f"[ERROR] Serial disconnected or failure: {e}")
            if ser:
                try:
                    ser.close()
                except Exception:
                    pass
            ser = None
            time.sleep(2)

        except KeyboardInterrupt:
            print("\n[INFO] Exiting monitor sender...")
            if ser and ser.is_open:
                ser.close()
            sys.exit(0)


if __name__ == "__main__":
    main()