#!/usr/bin/env python3
"""
Simple TCP-to-serial bridge for myCobot 280 Pi.

MyCobot280Socket (pymycobot v4.x) sends raw binary protocol frames
over TCP. This server relays them to/from the serial port (/dev/ttyAMA0).

Deploy on the Raspberry Pi:
    python3 tcp_serial_bridge.py

The server listens on 0.0.0.0:9000 and bridges to /dev/ttyAMA0 at 1000000 baud.
"""

import socket
import serial
import threading
import time
import sys

SERIAL_PORT = "/dev/ttyAMA0"
SERIAL_BAUD = 1000000
TCP_HOST = "0.0.0.0"
TCP_PORT = 9000


def serial_to_tcp(ser, conn, stop_event):
    """Read from serial, send to TCP client."""
    while not stop_event.is_set():
        try:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                if data:
                    conn.sendall(data)
            else:
                time.sleep(0.001)
        except Exception as e:
            print(f"serial_to_tcp error: {e}")
            break


def tcp_to_serial(conn, ser, stop_event):
    """Read from TCP client, send to serial."""
    while not stop_event.is_set():
        try:
            data = conn.recv(4096)
            if not data:
                print("Client disconnected.")
                break
            ser.write(data)
            ser.flush()
        except Exception as e:
            print(f"tcp_to_serial error: {e}")
            break


def main():
    print(f"Opening serial port {SERIAL_PORT} at {SERIAL_BAUD} baud...")
    ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=0.1)
    time.sleep(0.5)
    print("Serial port opened.")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((TCP_HOST, TCP_PORT))
    srv.listen(1)
    print(f"Listening on {TCP_HOST}:{TCP_PORT} ...")

    while True:
        print("Waiting for client connection...")
        conn, addr = srv.accept()
        print(f"Client connected from {addr}")

        stop_event = threading.Event()

        t1 = threading.Thread(target=serial_to_tcp, args=(ser, conn, stop_event), daemon=True)
        t2 = threading.Thread(target=tcp_to_serial, args=(conn, ser, stop_event), daemon=True)
        t1.start()
        t2.start()

        # Wait until one thread exits
        t2.join()
        stop_event.set()
        t1.join(timeout=2)

        try:
            conn.close()
        except:
            pass
        print("Client disconnected. Waiting for new connection...\n")


if __name__ == "__main__":
    main()
