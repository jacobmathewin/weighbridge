#!/usr/bin/env python3
import argparse
import sys
import time
import serial

ASCII_SAFE = set(range(32, 127)) | {9, 10, 13}

def to_ascii(data: bytes) -> str:
	return ''.join(chr(b) if b in ASCII_SAFE else '.' for b in data)


def main():
	parser = argparse.ArgumentParser(description="Sniff serial port and print hex + ASCII")
	parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port, e.g., /dev/ttyUSB0 or COM3")
	parser.add_argument("--baudrate", type=int, default=9600, help="Baud rate")
	parser.add_argument("--bytesize", type=int, default=8, choices=[7, 8], help="Byte size")
	parser.add_argument("--parity", default="N", choices=["N", "E", "O"], help="Parity")
	parser.add_argument("--stopbits", type=float, default=1, choices=[1, 1.5, 2], help="Stop bits")
	parser.add_argument("--timeout", type=float, default=0.5, help="Read timeout seconds")
	parser.add_argument("--newline", action="store_true", help="Print a newline between read chunks")
	args = parser.parse_args()

	try:
		ser = serial.Serial(
			port=args.port,
			baudrate=args.baudrate,
			bytesize=args.bytesize,
			parity=args.parity,
			stopbits=args.stopbits,
			timeout=args.timeout,
		)
	except Exception as e:
		print(f"Failed to open {args.port}: {e}")
		sys.exit(1)

	print(f"Opened {args.port} @ {args.baudrate},{args.bytesize}{args.parity}{args.stopbits}")
	print("Press Ctrl+C to stop.")
	try:
		while True:
			data = ser.read(256)
			if data:
				hex_str = ' '.join(f"0x{b:02x}" for b in data)
				ascii_str = to_ascii(data)
				print(f"HEX: {hex_str}")
				print(f"ASCII: {ascii_str}")
				if args.newline:
					print()
			else:
				time.sleep(0.05)
	except KeyboardInterrupt:
		pass
	finally:
		ser.close()
		print("Closed")

if __name__ == "__main__":
	main()
