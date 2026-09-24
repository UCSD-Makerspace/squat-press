"""
pump.py - peristaltic reward-pump driver for the RP2040 (Pico) + TMC2209 SilentStepStick.

OPTIMIZED (2026-09-01): PIO step train (PIO0 SM0, jerk-limited S-curve) PLUS a single-wire
TMC2209 UART on GP19 (PIO1) used strictly TRANSIENTLY - brought up only to configure the chip
and to ramp current down, then torn down, so it NEVER coexists with the step train during a
dose (a persistent UART on PIO1 silently stops the step pulses on PIO0 - the hard-won lesson).

UART-enabled features (dose volume is untouched - still pure PIO step count):
  * StealthChop2 + 256-microstep interpolation (MicroPlyer)     -> smooth, quiet motion
  * tuned current: IRUN=31 during a dose, IHOLD=0, EN-off between doses -> minimal heat/load
  * SILENT SOFT-OFF: ramp coil current down over UART before EN-off -> no end-of-dose click
  * self-healing run current (re-armed at the start of every dose) + read-back-verified config
Fully guarded: any UART failure leaves _uart_ok=False and the proven standalone dose path intact,
so Pump() can never fail to construct and dosing never breaks.

Requires the module's PDN_UART select jumper bridged to the GP19 pad (done 2026-09-01).
Pins: STEP=GP17 DIR=GP16 EN=GP26 MS1=GP22 MS2=GP21 ; UART=GP19 ; GP18 isolated (never drive).
"""
import rp2
import machine
from machine import Pin
from time import sleep_ms, sleep_us, ticks_ms, ticks_add, ticks_diff
from array import array

# ---------------------------------------------------------------- board wiring
PIN_STEP, PIN_DIR = 17, 16              # rev3 PCB: STEP=GP17, DIR=GP16
PIN_SLEEP, PIN_ENABLE, PIN_RESET = 18, 26, 19   # EN=GP26; GP18 = isolated PDN pad (Hi-Z); GP19 = PDN_UART
PIN_MS1, PIN_MS2 = 22, 21              # MS1=GP22, MS2=GP21 (both low = 1/8, also UART node 0)
PIN_SPREAD = 20                        # MS3/SPREAD pad; drive low for deterministic StealthChop

# ------------------------------------------------------------ motor and pump
MOTOR_STEPS_PER_REV = 200
UL_PER_REV = 12.60             # gravimetric 2026-09-01: 15.69 mg / 1.245 rev -> 12.60 mg/rev,
                               # so a requested "uL" now equals the mg delivered (density ~1)
DOSE_RPM = 52.0
DOSE_UL = 15.0                 # 15 uL @ 12.60 uL/rev = 1.190 rev = 1904 steps -> 15.00 mg

# ------------------------------------------------------------------- PIO: steps
SM_FREQ = 1_000_000
_PULSE = 7
_OVERHEAD_US = 2 + 2 * (_PULSE + 1)


@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def _step_train():
    pull(block)
    mov(x, osr)
    set(pins, 1)[7]
    set(pins, 0)[7]
    label("idle")
    jmp(x_dec, "idle")


# ------------------------------------------------- PIO: single-wire TMC2209 UART
_UART_BAUD = 115200
_SYNC = 0x05
_MASTER = 0xFF
_PADS_BANK0 = 0x4001C000


def _crc8(data):
    crc = 0
    for b in data:
        cur = b
        for _ in range(8):
            if ((crc >> 7) ^ (cur & 1)) & 1:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
            cur >>= 1
    return crc & 0xFF


@rp2.asm_pio(out_init=rp2.PIO.OUT_HIGH, set_init=rp2.PIO.OUT_HIGH, out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def _uart_tx():
    label("idle")
    set(pindirs, 0)
    pull()
    set(pindirs, 1)
    set(pins, 0)          [6]
    set(x, 7)
    label("bit")
    out(pins, 1)          [6]
    jmp(x_dec, "bit")
    set(pins, 1)          [6]
    jmp("idle")


@rp2.asm_pio(in_shiftdir=rp2.PIO.SHIFT_RIGHT, fifo_join=rp2.PIO.JOIN_RX)
def _uart_rx():
    label("start")
    wait(0, pin, 0)
    set(x, 7)             [10]
    label("bit")
    in_(pins, 1)
    jmp(x_dec, "bit")     [6]
    jmp(pin, "good")
    wait(1, pin, 0)
    jmp("start")
    label("good")
    push(block)


class Pump:
    """Peristaltic pump on a TMC2209, PIO-stepped. Phase 1: UART read-only, dose path unchanged."""

    _MS_TABLE = {8: (0, 0), 2: (1, 0), 4: (0, 1), 16: (1, 1)}   # (MS1, MS2); dose path uses 8

    def __init__(self, microstep=8, ul_per_rev=UL_PER_REV, sm_id=0):
        self._dir = Pin(PIN_DIR, Pin.OUT, value=0)
        self._slp = Pin(PIN_SLEEP, Pin.IN)               # GP18 = isolated PDN pad -> Hi-Z, never drive
        self._en = Pin(PIN_ENABLE, Pin.OUT, value=1)     # active-low: 1 = disabled (safe boot)
        self._ms = (Pin(PIN_MS1, Pin.OUT), Pin(PIN_MS2, Pin.OUT))

        self.ul_per_rev = float(ul_per_rev)
        self.set_microstep(microstep)

        # step train: PIO0 SM0 (remove_program is on PIO0 only, BEFORE loading the step program)
        try:
            rp2.PIO(sm_id // 4).remove_program()
        except Exception:
            pass
        self._sm = rp2.StateMachine(sm_id, _step_train, freq=SM_FREQ, set_base=Pin(PIN_STEP))
        self._sm.active(1)                                # parks on pull(); no motion until fed

        # ---- Phase 1: single-wire UART on PIO1 (read-only). Fully guarded: never breaks dosing. ----
        self._uart_ok = False
        self._config_ok = False
        self._version = None
        self._utx = None
        self._urx = None
        self._upin = None
        # TRANSIENT UART: bring up, read VERSION, then ALWAYS tear down so the dose path runs
        # byte-identical to the proven backup (no UART SMs active on PIO1 during stepping).
        try:
            self._uart_setup()
            v = None
            for _ in range(4):                            # 1st read after setup often needs settling
                v = self._uart_read(0x06)                 # IOIN
                if v is not None:
                    break
                sleep_ms(5)
            if v is not None:
                self._version = (v >> 24) & 0xFF
                self._uart_ok = (self._version == 0x21)
                if self._uart_ok:
                    self._tmc_config()                    # PHASE 2: write optimized config, verify
            else:
                print("PUMP_UART: no IOIN reply")         # temp debug
        except Exception as e:
            print("PUMP_UART_ERR", e)                     # temp debug
            self._uart_ok = False
        finally:
            self._uart_teardown()                         # ALWAYS release GP19 + clear PIO1 before dosing

    # ----------------------------------------------------------------- UART (PIO1)
    def _uart_setup(self):
        try:
            rp2.PIO(1).remove_program()                  # clear PIO1 ONLY - never PIO0 (step train)
        except Exception:
            pass
        pin = Pin(PIN_RESET, Pin.IN, Pin.PULL_UP)        # GP19 = PDN_UART; idle HIGH
        self._upin = pin
        self._utx = rp2.StateMachine(4, _uart_tx, freq=8 * _UART_BAUD, out_base=pin, set_base=pin)  # PIO1 SM0
        self._urx = rp2.StateMachine(5, _uart_rx, freq=8 * _UART_BAUD, in_base=pin, jmp_pin=pin)    # PIO1 SM1
        pad = _PADS_BANK0 + 0x04 + PIN_RESET * 4
        machine.mem32[pad] = (machine.mem32[pad] | (1 << 3) | (1 << 6)) & ~(1 << 2)  # PUE+IE, clear PDE
        self._urx.active(1)
        self._utx.active(1)
        sleep_ms(2)
        self._uart_flush()

    def _uart_teardown(self):
        for sm in (self._utx, self._urx):
            try:
                if sm:
                    sm.active(0)
            except Exception:
                pass
        self._utx = self._urx = None
        try:
            rp2.PIO(1).remove_program()                   # fully clear PIO1 (leave it untouched like the backup)
        except Exception:
            pass
        try:
            Pin(PIN_RESET, Pin.IN)                        # restore GP19 Hi-Z (no pull) = legacy state
        except Exception:
            pass

    def _uart_flush(self):
        try:
            while self._urx.rx_fifo():
                self._urx.get()
        except Exception:
            pass

    def _uart_write(self, reg, val, settle_ms=12):
        """Write a TMC register (used in later phases). Conservative settle for config/re-arm."""
        dg = bytearray(8)
        dg[0] = _SYNC
        dg[1] = 0
        dg[2] = (reg & 0x7F) | 0x80
        dg[3] = (val >> 24) & 0xFF
        dg[4] = (val >> 16) & 0xFF
        dg[5] = (val >> 8) & 0xFF
        dg[6] = val & 0xFF
        dg[7] = _crc8(dg[:7])
        self._uart_flush()
        for b in dg:
            self._utx.put(b & 0xFF)
        sleep_ms(settle_ms)

    def _find_reply(self, raw, reg):
        end = len(raw) - 7
        i = 0
        while i < end:
            if raw[i] == _SYNC and raw[i + 1] == _MASTER and (raw[i + 2] & 0x7F) == reg:
                fr = bytes(raw[i:i + 8])
                if _crc8(fr[:7]) == fr[7]:
                    return (fr[3] << 24) | (fr[4] << 16) | (fr[5] << 8) | fr[6]
            i += 1
        return None

    def _uart_read(self, reg, timeout_ms=50):
        reg &= 0x7F
        req = bytearray(4)
        req[0] = _SYNC
        req[1] = 0
        req[2] = reg
        req[3] = _crc8(req[:3])
        self._uart_flush()
        for b in req:
            self._utx.put(b & 0xFF)
        raw = bytearray()
        deadline = ticks_add(ticks_ms(), timeout_ms)
        while ticks_diff(deadline, ticks_ms()) > 0:
            if self._urx.rx_fifo():
                raw.append((self._urx.get() >> 24) & 0xFF)
                if len(raw) >= 8:
                    v = self._find_reply(raw, reg)
                    if v is not None:
                        return v
                if len(raw) >= 24:
                    break
        return self._find_reply(raw, reg)

    def _tmc_config(self):
        """PHASE 2: write the optimized config over the (currently-up) UART, then read-back verify.
        GCONF StealthChop+pdn_disable; IHOLD_IRUN IRUN=31/IHOLD=0/IHOLDDELAY=8; TPOWERDOWN=20;
        TPWMTHRS=0. CHOPCONF/PWMCONF stay at POR (intpol=1, pwm_autoscale=1) - verify only."""
        ifa = self._uart_read(0x02)                   # IFCNT before
        self._uart_write(0x00, 0x00000141)            # GCONF
        self._uart_write(0x10, 0x00081F00)            # IHOLD_IRUN
        self._uart_write(0x11, 0x00000014)            # TPOWERDOWN = 20
        self._uart_write(0x13, 0x00000000)            # TPWMTHRS = 0 (pure StealthChop)
        ifb = self._uart_read(0x02)                   # IFCNT after (delta = writes accepted)
        g = self._uart_read(0x00)                     # GCONF read-back
        c = self._uart_read(0x6C)                     # CHOPCONF POR (TOFF>=1, intpol=1)
        pw = self._uart_read(0x70)                    # PWMCONF POR (pwm_autoscale=1)
        ok = (g is not None) and (((g >> 6) & 1) == 1) and (((g >> 2) & 1) == 0)  # pdn_disable, StealthChop
        if ifa is not None and ifb is not None:
            ok = ok and (((ifb - ifa) & 0xFF) >= 4)   # >=4 writes accepted
        if c is not None:
            ok = ok and (c & 0x0F) >= 1 and ((c >> 28) & 1) == 1   # TOFF>=1, intpol=1
        if pw is not None:
            ok = ok and ((pw >> 18) & 1) == 1                       # pwm_autoscale=1
        self._config_ok = bool(ok)
        return self._config_ok

    def _arm_current(self):
        """PHASE 3: set full run current (IRUN=31) for the coming dose via a transient UART session.
        Self-healing: recovers even if a prior soft-off left IRUN low or a re-arm frame dropped."""
        if not self._uart_ok:
            return
        try:
            self._uart_setup()
            self._uart_write(0x10, 0x00081F00)           # IHOLD_IRUN: IRUN=31, IHOLD=0, IHOLDDELAY=8
        except Exception:
            pass
        finally:
            self._uart_teardown()

    def _soft_off(self):
        """PHASE 3: ramp coil current down over UART before EN-off, so the field collapses gradually
        (no detent snap = no click). Transient UART; motor is still EN-low at standstill when called."""
        if not self._uart_ok:
            return
        try:
            self._uart_setup()
            for irun in (18, 12, 7, 4, 2, 1):
                self._uart_write(0x10, irun | (irun << 8) | (8 << 16), settle_ms=3)  # IHOLD=IRUN=irun
        except Exception:
            pass
        finally:
            self._uart_teardown()

    # ------------------------------------------------------------- configuration
    def set_microstep(self, m):
        if m not in self._MS_TABLE:
            raise ValueError("microstep must be 8, 4, 2 or 16 (TMC2209 MS1/MS2)")
        for pin, val in zip(self._ms, self._MS_TABLE[m]):
            pin.value(val)
        self.microstep = m
        self.steps_per_rev = MOTOR_STEPS_PER_REV * m

    # ------------------------------------------------------------------- power
    def enable(self):
        self._en.value(0)

    def disable(self):
        self._en.value(1)                                # de-energize: no torque, no heat, no buzz

    def sleep(self):
        self.disable()

    # -------------------------------------------------------------------- motion
    def _idle_us(self, rpm):
        sps = self.steps_per_rev * abs(rpm) / 60.0
        if sps <= 0:
            return 60000
        return max(1, int(1_000_000 / sps) - _OVERHEAD_US)

    def move_steps(self, steps, rpm=DOSE_RPM, accel_frac=0.35, start_frac=0.06, hold=False):
        """Jerk-limited S-curve move. PHASE 1: ends in the legacy hard disable() (unchanged)."""
        steps = int(steps)
        if steps == 0:
            return
        self._dir.value(1 if steps > 0 else 0)
        n = abs(steps)
        _m = self.microstep
        n = int(round(n / _m)) * _m or _m               # land on a full-step detent

        v_cruise = self.steps_per_rev * abs(rpm) / 60.0
        v_start = max(v_cruise * start_frac, 1.0)
        ramp = min(int(n * accel_frac), n // 2)

        tbl = array("I", bytes(4 * n))
        span = v_cruise - v_start
        for i in range(n):
            if ramp and i < ramp:
                s = (i + 1) / ramp
            elif ramp and i >= n - ramp:
                s = (n - i) / ramp
            else:
                s = 1.0
            f = s * s * (3.0 - 2.0 * s)
            v = v_start + span * f
            d = int(1_000_000.0 / v) - _OVERHEAD_US
            tbl[i] = d if d > 1 else 1

        if self._uart_ok:
            self._arm_current()                          # PHASE 3: full IRUN for this dose (UART down after)
        self.enable()
        sleep_us(300)
        put = self._sm.put
        for d in tbl:
            put(d)
        sleep_ms(int(4 * tbl[-1] / 1000) + 30)
        if not hold:
            if self._uart_ok:
                self._soft_off()                         # PHASE 3: ramp current down -> no click
            self.disable()                               # EN high; current already ~0 -> no snap

    def revolutions(self, rev, rpm=DOSE_RPM, hold=False):
        self.move_steps(round(rev * self.steps_per_rev), rpm, hold=hold)

    def dose_ul(self, microlitres, rpm=DOSE_RPM):
        self.revolutions(float(microlitres) / self.ul_per_rev, rpm)

    def _prime_delay(self, rpm):
        rpm = min(abs(rpm), 120.0)
        v = self.steps_per_rev * rpm / 60.0
        d = int(1_000_000.0 / v) - _OVERHEAD_US
        return d if d > 1 else 1, v

    def prime(self, seconds, rpm=100.0):
        d, v = self._prime_delay(rpm)
        n = int(v * seconds)
        self._dir.value(1)
        self.enable(); sleep_us(300)
        put = self._sm.put
        try:
            for _ in range(n):
                put(d)
        finally:
            self.disable()

    def prime_run(self, rpm=100.0):
        d, _ = self._prime_delay(rpm)
        self._dir.value(1)
        self.enable(); sleep_us(300)
        put = self._sm.put
        try:
            while True:
                put(d)
        finally:
            self.disable()

    # -------------------------------------------------------------------- status
    def status(self):
        return {
            "microstep": self.microstep,
            "steps_per_rev": self.steps_per_rev,
            "ul_per_rev": self.ul_per_rev,
            "enabled": self._en.value() == 0,
            "driver": "TMC2209",
            "uart_ok": self._uart_ok,
            "config_ok": self._config_ok,
            "version": self._version,
            "tx_fifo": self._sm.tx_fifo(),
        }
