"""Independent DS18B20 8-device timing arithmetic.

Basis: Maxim DS18B20 19-7487 Rev 6 (7/19).
- AC Electrical Characteristics (p.3): tCONV max 93.75/187.5/375/750 ms
  for 9/10/11/12-bit; tSLOT min 60 us; tREC min 1 us; reset low/high
  min 480 us each.
- 1-Wire Signaling (p.15-16): reset low >=480 us, reset high >=480 us;
  write/read slots >=60 us with >=1 us recovery.
- Transaction Sequence (p.10): reset + ROM command (8 bits) + optional
  64-bit ROM + function command (8 bits) + data.
- Read Scratchpad (p.11): up to 9 bytes (72 bits).
"""

N = 8
TCONV_MS = 750.0          # 12-bit max, guaranteed
SLOT_US = 60.0            # minimum legal time slot
REC_US = 1.0              # minimum recovery between slots
RESET_US = 480.0 + 480.0  # reset low + reset high, both minimum
BITS_PER_BYTE = 8
ROM_BITS = 64

def txn_us(rom_cmd_bits, rom_code_bits, func_bits, data_bits):
    bits = rom_cmd_bits + rom_code_bits + func_bits + data_bits
    return RESET_US + bits * (SLOT_US + REC_US), bits

def ms(us):
    return us / 1000.0

# Broadcast conversion: reset + Skip ROM (0xCC, 8) + Convert T (0x44, 8)
t_convert_cmd_us, convert_bits = txn_us(8, 0, 8, 0)
# Per-device read: reset + Match ROM (0x55, 8) + 64-bit ROM + Read
# Scratchpad (0xBE, 8) + 9 bytes (72 bits)
t_read9_us, read9_bits = txn_us(8, ROM_BITS, 8, 9 * BITS_PER_BYTE)
t_read2_us, read2_bits = txn_us(8, ROM_BITS, 8, 2 * BITS_PER_BYTE)
# Per-device conversion transaction: reset + Match ROM + 64-bit ROM + Convert T
t_devconv_us, devconv_bits = txn_us(8, ROM_BITS, 8, 0)

print("=== per-transaction ===")
print(f"broadcast convert cmd: {t_convert_cmd_us:.0f} us = {ms(t_convert_cmd_us):.3f} ms ({convert_bits} bits)")
print(f"read 9B/device:        {t_read9_us:.0f} us = {ms(t_read9_us):.3f} ms ({read9_bits} bits)")
print(f"read 2B/device:        {t_read2_us:.0f} us = {ms(t_read2_us):.3f} ms ({read2_bits} bits)")
print(f"convert cmd/device:    {t_devconv_us:.0f} us = {ms(t_devconv_us):.3f} ms ({devconv_bits} bits)")

print("\n=== round totals ===")
read9_total_ms = N * ms(t_read9_us)
read2_total_ms = N * ms(t_read2_us)
print(f"broadcast + 750 ms + 8x9B: {ms(t_convert_cmd_us) + TCONV_MS + read9_total_ms:.3f} ms")
print(f"broadcast + 750 ms + 8x2B: {ms(t_convert_cmd_us) + TCONV_MS + read2_total_ms:.3f} ms")
print(f"conversion alone:          {TCONV_MS:.3f} ms")
print(f"8x9B readback alone:       {read9_total_ms:.3f} ms")
print(f"8x2B readback alone:       {read2_total_ms:.3f} ms")

serialized_ms = N * (ms(t_devconv_us) + TCONV_MS + ms(t_read9_us))
print(f"serialized individual:     {serialized_ms:.3f} ms")
pipelined_ms = N * ms(t_devconv_us) + TCONV_MS + read9_total_ms
print(f"back-to-back individual (inference, unverified): {pipelined_ms:.3f} ms")

print("\n=== reconciliation with existing rerun/calc.py ===")
# Existing script: 64 + 8 + 9*8 = 144 bits/device, 60 us/bit, 960 us reset
existing_bits = 64 + 8 + 9 * 8
existing_read_ms = N * (960 + existing_bits * 60) / 1000.0
print(f"existing formula: {N} * (960 + {existing_bits}*60) us = {existing_read_ms:.3f} ms")
print(f"existing + 750 ms = {existing_read_ms + TCONV_MS:.3f} ms")
missing_cmd_ms = N * 8 * 60 / 1000.0
missing_rec_ms = N * read9_bits * 1 / 1000.0
broadcast_ms = ms(t_convert_cmd_us)
print(f"add missing 8-bit command: {missing_cmd_ms:.3f} ms")
print(f"add 1 us recovery/bit:     {missing_rec_ms:.3f} ms")
print(f"add broadcast cmd overhead:{broadcast_ms:.3f} ms")
print(f"reconciled total:          {existing_read_ms + TCONV_MS + missing_cmd_ms + missing_rec_ms + broadcast_ms:.3f} ms")

print("\n=== 9-bit table check ===")
for bits, t in [(9, 93.75), (10, 187.5), (11, 375.0), (12, 750.0)]:
    print(f"{bits}-bit: {t} ms")
