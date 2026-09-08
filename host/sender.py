import argparse
import sys
import time
import psutil
import serial
import serial.tools.list_ports
import socket

def get_ip_addresses():
    """Retrieve physical IP addresses (Ethernet & Wi-Fi) on Windows/Linux/macOS."""
    eth_ip = "N/A"
    wifi_ip = "N/A"
    
    try:
        interfaces = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        
        for iface_name, addrs in interfaces.items():
            # Filter common virtual interfaces
            name_lower = iface_name.lower()
            if any(ignored in name_lower for ignored in ['loopback', 'veth', 'docker', 'tun', 'tap', 'vethernet', 'host-only']):
                continue
                
            # Check if interface is UP
            if iface_name in stats and not stats[iface_name].isup:
                continue

            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    if any(w in name_lower for w in ['wi-fi', 'wifi', 'wlan', 'wireless']):
                        wifi_ip = addr.address
                    elif any(e in name_lower for e in ['ethernet', 'eth', 'lan']):
                        eth_ip = addr.address
                    elif eth_ip == "N/A":
                        eth_ip = addr.address
    except Exception:
        pass

    return eth_ip, wifi_ip

def detect_and_select_port(target_port=None):
    """Scans serial ports, displays their status, and returns the Tufty/RP2040 port."""
    ports = serial.tools.list_ports.comports()
    
    print("\n" + "=" * 70)
    print(" SERIAL PORT SCAN ")
    print("=" * 70)

    if not ports:
        print("[!] No serial ports detected on the system.")
        print("=" * 70 + "\n")
        return None

    print(f"{'PORT':<10} | {'STATUS':<12} | {'DEVICE DESCRIPTION'}")
    print("-" * 70)

    tufty_port = None

    for p in ports:
        # Check port availability
        is_busy = False
        try:
            s = serial.Serial(p.device)
            s.close()
        except (serial.SerialException, OSError):
            is_busy = True

        status = "BUSY" if is_busy else "AVAILABLE"

        # Build description
        details = p.description
        if p.vid and p.pid:
            details += f" (VID:{p.vid:04X} PID:{p.pid:04X})"

        # Identify RP2040 / Tufty (Raspberry Pi Foundation VID = 0x2E8A)
        is_tufty = (p.vid == 0x2E8A)
        if is_tufty:
            details += " <-- [Tufty 2040 / RP2040]"
            if not is_busy or target_port == p.device:
                tufty_port = p.device

        print(f"{p.device:<10} | {status:<12} | {details}")

    print("=" * 70)

    # Manual port specified
    if target_port:
        print(f"--> Using user-specified port: {target_port}\n")
        return target_port

    # Auto-detected port
    if tufty_port:
        print(f"--> Auto-detected Tufty 2040 on port: {tufty_port}\n")
        return tufty_port

    # Warning if no Tufty found
    print("[ALERT] No Tufty 2040 (RP2040) detected or available!")
    print("      Please verify USB cable connection or specify port manually.\n")
    return None

def main():
    parser = argparse.ArgumentParser(description="LCARS Telemetry & Time Sender for Tufty 2040")
    parser.add_argument("port", nargs="?", default=None, help="Serial port (optional, e.g. COM7 or /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baudrate (default: 115200)")
    parser.add_argument("-o", "--offset", type=int, default=0, help="Timezone offset in hours (e.g. 2 for UTC+2)")
    parser.add_argument("-d", "--debug", action="store_true", help="Display Tufty 2040 incoming logs and time sync events")
    args = parser.parse_args()

    # Scan ports and resolve target port
    selected_port = detect_and_select_port(args.port)

    if not selected_port:
        sys.exit(1)

    try:
        ser = serial.Serial(selected_port, args.baud, timeout=1)
        print(f"Connected to {selected_port} at {args.baud} baud (UTC offset: {args.offset:+d}h).")
        if args.debug:
            print("Debug mode active: showing logs from Tufty and sync events.")
    except Exception as e:
        print(f"Error opening serial port {selected_port}: {e}")
        sys.exit(1)

    # Initialize psutil.cpu_percent
    psutil.cpu_percent(interval=None)

    # Allow serial handshake time
    time.sleep(1.5)

    last_sync_time = 0
    SYNC_INTERVAL = 60  # Send time sync every 60 seconds

    while True:
        try:
            current_now = time.time()
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            eth, wifi = get_ip_addresses()

            # Prepare telemetry payload
            payload = (
                f"CPU:{cpu:.1f}|"
                f"RAM_PCT:{ram.percent:.1f}|RAM_U:{ram.used / 1e9:.1f}|RAM_T:{ram.total / 1e9:.1f}|"
                f"DISK_PCT:{disk.percent:.1f}|DISK_U:{disk.used / 1e9:.1f}|DISK_T:{disk.total / 1e9:.1f}|"
                f"ETH:{eth}|WIFI:{wifi}"
            )

            # Append time synchronization if 60 seconds have passed
            if current_now - last_sync_time >= SYNC_INTERVAL:
                # Calculate target time with timezone offset
                target_time = time.gmtime(current_now + (args.offset * 3600))
                time_str = time.strftime("%Y,%m,%d,%H,%M,%S", target_time)
                
                payload += f"|INIT_TIME:{time_str}"
                last_sync_time = current_now
                
                # Display time sync message ONLY in debug mode
                if args.debug:
                    print(f"[TIME SYNC] Sent time payload: {time_str} (Offset {args.offset:+d}h)")

            payload += "\n"
            ser.write(payload.encode('utf-8'))

            if args.debug:
                while ser.in_waiting:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        print(f"[TUFTY LOG] {line}")

            time.sleep(1)

        except KeyboardInterrupt:
            print("\nStopping sender...")
            ser.close()
            break
        except Exception as e:
            print(f"Error in send loop: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()

