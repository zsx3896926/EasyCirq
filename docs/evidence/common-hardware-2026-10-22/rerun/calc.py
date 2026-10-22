"""Independent arithmetic for the five audited fixes (no repo imports)."""
import math


def boost(vin, vout, iout, eta, fsw, l, ilim):
    d = 1 - vin * eta / vout
    iin = iout / (1 - d)
    dil = vin * d / (fsw * l)
    peak = iin + dil / 2
    valley = (1 - d) * (ilim + dil / 2)
    peak_limit = (1 - d) * (ilim - dil / 2)
    old = ilim * (1 - d) - dil / 2
    return dict(D=d, IIN=iin, dIL=dil, ISW_peak=peak,
                IOUT_valley=valley, IOUT_peaklimit=peak_limit, IOUT_old=old)


def relay(l, r, i0, vf, vrev=None):
    tau = l / r
    v = vf if vrev is None else vrev
    t = tau * math.log(1 + i0 * r / v)
    return tau, t


def tach_divider(vin, rtop, rbot):
    return vin * rbot / (rtop + rbot)


def ds18b20_read_time(n, bit_us=61, bits_per_device=8 + 64 + 8 + 9 * 8, reset_us=960):
    # Match ROM command (8) + 64-bit ROM + Read Scratchpad command (8)
    # + 9 data bytes (72); 61 us/bit = 60 us slot + 1 us recovery.
    return n * (reset_us + bits_per_device * bit_us) / 1e6


print('Boost TPS61023 3.3->5V/0.5A:', boost(3.135, 5, 0.5, 0.9, 1e6, 1e-6, 2.7))
print('Boost PWR-03 3.3->12V/0.4A ILIM=3.0:', boost(3.135, 12, 0.4, 0.85, 600e3, 10e-6, 3.0))
print('Boost PWR-03 3.3->12V/0.4A ILIM=2.5:', boost(3.135, 12, 0.4, 0.85, 600e3, 10e-6, 2.5))
for name, vf, vrev in [('diode', 0.7, None), ('diode+24V zener', 0.7, 24.7)]:
    tau, t = relay(0.5, 400, 0.030, vf, vrev)
    print(f'relay {name}: tau={tau*1e3:.3f} ms, coil_to_zero={t*1e3:.3f} ms, '
          f'system_with_5ms_mech={t*1e3+5:.3f} ms')
for rbot in (3.6e3, 3.3e3):
    print(f'tach 10k/{rbot/1e3:.1f}k: 12V={tach_divider(12, 10e3, rbot):.3f} V, '
          f'12.6V={tach_divider(12.6, 10e3, rbot):.3f} V')
print(f'DS18B20 8 devices standard-speed read phase ~= {ds18b20_read_time(8):.3f} s; '
      f'+750 ms conversion = {ds18b20_read_time(8)+0.75:.3f} s')
