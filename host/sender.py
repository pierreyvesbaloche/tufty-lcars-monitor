import argparse
import sys
import time
import psutil
import serial
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

def main():
    parser = argparse.ArgumentParser(description="LCARS Telemetry & Time Sender for Tufty 2040")
    parser.add_argument("port", help="Serial port (e.g. COM7 or /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baudrate (default: 115200)")
    parser.add_argument("-o", "--offset", type=int, default=0, help="Timezone offset in hours (e.g. 2 for UTC+2)")
    parser.add_argument("-d", "--debug", action="store_true", help="Display Tufty 2040 incoming logs")
    args = parser.parse_args()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
        print(f"Connected to {args.port} at {args.baud} baud (UTC offset: {args.offset:+d}h).")
        if args.debug:
            print("Debug mode active: showing logs from Tufty.")
    except Exception as e:
        print(f"Error opening serial port {args.port}: {e}")
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