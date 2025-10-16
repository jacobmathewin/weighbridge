#!/usr/bin/env python3
import argparse
import time
from typing import List, Tuple

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

# Minimal interpretations for common scales

def decode_u16_list(registers: List[int]) -> List[int]:
	return [r & 0xFFFF for r in registers]


def decode_s16_list(registers: List[int]) -> List[int]:
	values: List[int] = []
	for r in registers:
		v = r & 0xFFFF
		if v & 0x8000:
			v = v - 0x10000
		values.append(v)
	return values


def decode_u32_pairs(registers: List[int], big_endian: bool = True) -> List[int]:
	values: List[int] = []
	for i in range(0, len(registers) - 1, 2):
		hi, lo = (registers[i], registers[i + 1]) if big_endian else (registers[i + 1], registers[i])
		values.append(((hi & 0xFFFF) << 16) | (lo & 0xFFFF))
	return values


def decode_s32_pairs(registers: List[int], big_endian: bool = True) -> List[int]:
	values: List[int] = []
	for i in range(0, len(registers) - 1, 2):
		hi, lo = (registers[i], registers[i + 1]) if big_endian else (registers[i + 1], registers[i])
		u = ((hi & 0xFFFF) << 16) | (lo & 0xFFFF)
		if u & 0x80000000:
			u = u - 0x100000000
		values.append(u)
	return values


def pretty_candidates(registers: List[int]) -> str:
	u16 = decode_u16_list(registers)
	s16 = decode_s16_list(registers)
	u32_be = decode_u32_pairs(registers, True)
	u32_le = decode_u32_pairs(registers, False)
	s32_be = decode_s32_pairs(registers, True)
	s32_le = decode_s32_pairs(registers, False)
	parts = []
	parts.append(f"u16={u16[:6]}")
	parts.append(f"s16={s16[:6]}")
	if u32_be:
		parts.append(f"u32_BE={u32_be[:3]}")
	if u32_le:
		parts.append(f"u32_LE={u32_le[:3]}")
	if s32_be:
		parts.append(f"s32_BE={s32_be[:3]}")
	if s32_le:
		parts.append(f"s32_LE={s32_le[:3]}")
	return " | ".join(parts)


def probe(client: ModbusSerialClient, units: List[int], address_start: int, address_end: int, counts: List[int], delay: float, kind: str) -> List[Tuple[int, int, int, List[int]]]:
	results = []
	for unit in units:
		for address in range(address_start, address_end + 1):
			for count in counts:
				try:
					if kind == "holding":
						resp = client.read_holding_registers(address=address, count=count, unit=unit)
					else:
						resp = client.read_input_registers(address=address, count=count, unit=unit)
					if hasattr(resp, 'isError') and not resp.isError() and hasattr(resp, 'registers') and resp.registers:
						results.append((unit, address, count, resp.registers))
						print(f"OK unit={unit} addr={address} count={count} -> {resp.registers[:6]} | {pretty_candidates(resp.registers)}")
					else:
						# Uncomment to see errors/no data
						# print(f"ERR unit={unit} addr={address} count={count} -> {resp}")
						pass
				except ModbusException as e:
					# print(f"ModbusException unit={unit} addr={address} count={count}: {e}")
					pass
				except Exception:
					# Serial timeouts etc.
					pass
				time.sleep(delay)
	return results


def main():
	parser = argparse.ArgumentParser(description="Probe Modbus RTU device to discover unit/address/count for registers")
	parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port, e.g., /dev/ttyUSB0 or COM3")
	parser.add_argument("--baudrate", type=int, default=9600, help="Baud rate")
	parser.add_argument("--parity", default="N", choices=["N", "E", "O"], help="Parity")
	parser.add_argument("--stopbits", type=int, default=1, choices=[1, 2], help="Stop bits")
	parser.add_argument("--bytesize", type=int, default=8, choices=[7, 8], help="Byte size")
	parser.add_argument("--timeout", type=float, default=1.0, help="Request timeout seconds")
	parser.add_argument("--units", default="1", help="Comma-separated list or range for unit IDs, e.g., 1 or 1,2,3 or 1-10")
	parser.add_argument("--addr-range", default="0-20", help="Address range to scan, e.g., 0-200")
	parser.add_argument("--counts", default="1,2,4,8", help="Comma-separated counts to try, e.g., 1,2,4")
	parser.add_argument("--delay", type=float, default=0.05, help="Delay between requests in seconds")
	parser.add_argument("--kind", default="holding", choices=["holding", "input"], help="Register type to read")
	args = parser.parse_args()

	def parse_units(units_str: str) -> List[int]:
		units: List[int] = []
		for part in units_str.split(','):
			part = part.strip()
			if '-' in part:
				lo, hi = part.split('-', 1)
				units.extend(range(int(lo), int(hi) + 1))
			else:
				units.append(int(part))
		return sorted(set(units))

	def parse_range(rng: str) -> Tuple[int, int]:
		lo_s, hi_s = rng.split('-', 1)
		return int(lo_s), int(hi_s)

	def parse_counts(counts_str: str) -> List[int]:
		return [int(c.strip()) for c in counts_str.split(',') if c.strip()]

	units = parse_units(args.units)
	addr_lo, addr_hi = parse_range(args.addr_range)
	counts = parse_counts(args.counts)

	client = ModbusSerialClient(
		method='rtu',
		port=args.port,
		baudrate=args.baudrate,
		parity=args.parity,
		stopbits=args.stopbits,
		bytesize=args.bytesize,
		timeout=args.timeout,
	)

	if not client.connect():
		print(f"Failed to connect on {args.port} @ {args.baudrate}bps")
		return

	print(f"Connected on {args.port}. Scanning units={units}, addr={addr_lo}-{addr_hi}, counts={counts}, kind={args.kind}")
	try:
		probe(client, units, addr_lo, addr_hi, counts, args.delay, args.kind)
	finally:
		client.close()
		print("Disconnected")

if __name__ == "__main__":
	main()
