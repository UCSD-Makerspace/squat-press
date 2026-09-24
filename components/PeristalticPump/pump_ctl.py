# Pi-side helper for the reward pump. Drives pump.py on the pump Pico over its USB-CDC REPL.
#
# Auto-detects the pump by looking for pump.py on the Pico's flash -- NOT by port number, because
# the ACM ports shuffle on reboot and the SENSOR Pico is the other ACM. That means this keeps
# working after a replug, and can never grab the sensor by mistake.
#
# Verified board pin map lives in pump.py:
#   STEP=GP3  DIR=GP2  SLEEP=GP4  RESET=GP5  ENABLE=GP9  MS1=GP8  MS2=GP7   (1/8 microstep)
import serial, time, glob, threading

DEFAULT_DOSE_UL = 15.0          # reward per delivery; keep in step with pump.DOSE_UL on the Pico
UL_PER_REV = 12.60               # PharMed BPT 1.6 mm ID -- REPLACE with the gravimetric value
DOSE_RPM = 52.0


def find_pump_port(exclude=()):
    """Return the /dev/ttyACM* whose flash carries pump.py, else None."""
    for p in sorted(glob.glob("/dev/ttyACM*")):
        if p in exclude:
            continue
        try:
            s = serial.Serial(p, 115200, timeout=0.5); time.sleep(0.3)
            s.write(b"\x03\x03"); time.sleep(0.2); s.reset_input_buffer()
            s.write(b"import os\r\nprint('FS', os.listdir('/'))\r\n"); time.sleep(0.5)
            out = s.read(s.in_waiting or 1).decode("utf-8", "replace"); s.close()
            if "pump.py" in out:
                return p
        except Exception:
            pass
    return None


class Pump:
    """Reward pump. Thread-safe; every dose de-energizes the motor when it finishes."""

    def __init__(self, port, dose_ul=DEFAULT_DOSE_UL, ul_per_rev=UL_PER_REV):
        self.port = port
        self.dose_ul = float(dose_ul)
        self.ul_per_rev = float(ul_per_rev)
        self._lock = threading.Lock()
        self.busy = False
        self.doses = 0                      # session tally
        self.total_ul = 0.0
        self.last_error = ""

        self.s = serial.Serial(port, 115200, timeout=1, write_timeout=2); time.sleep(0.4)  # write_timeout: a re-enumerated (stale) pump handle raises instead of blocking the thread forever
        self._raw("\x03\x03", 0.4)                              # interrupt anything running
        self._raw("import sys", 0.2)
        self._raw("sys.modules.pop('pump', None)", 0.2)         # force a fresh import
        self._raw("import pump", 0.4)
        self._raw("_p = pump.Pump()", 0.6)                      # 1/8 microstep, starts DISABLED
        self._raw("_p.ul_per_rev = %r" % self.ul_per_rev, 0.3)

    # ---------------------------------------------------------------- internals
    def _raw(self, cmd, wait=0.3):
        self.s.write(cmd.encode() + b"\r\n")
        time.sleep(wait)
        return self.s.read(self.s.in_waiting or 1)

    def _move_seconds(self, ul):
        """Generous wall-clock estimate for a dose, including ramp and FIFO drain."""
        rev = abs(ul) / self.ul_per_rev
        return rev * 60.0 / DOSE_RPM * 1.6 + 0.6

    # ------------------------------------------------------------------- dosing
    def dose(self, ul=None):
        """Dispense one reward. BLOCKING -- call from a worker thread, not the GUI thread."""
        ul = self.dose_ul if ul is None else float(ul)
        with self._lock:
            self.busy = True
            try:
                self.s.reset_input_buffer()
                # push live calibration to the Pico every dose -- it was only sent once at
                # init, so GUI/config changes to uL/rev never reached the chip (dosed at 60 forever)
                self.s.write(("_p.ul_per_rev = %r\r\n" % self.ul_per_rev).encode())
                time.sleep(0.05)
                self.s.write(("_p.dose_ul(%r)\r\n" % ul).encode())
                time.sleep(self._move_seconds(ul))
                self.s.read(self.s.in_waiting or 1)
                self.doses += 1
                self.total_ul += ul
                self.last_error = ""
            except Exception as e:
                self.last_error = str(e)
            finally:
                self.busy = False
        return self.last_error == ""

    def prime(self, seconds=5.0):
        """Run continuously to fill the tubing before a session."""
        with self._lock:
            self.busy = True
            try:
                self.s.write(("_p.prime(%r)\r\n" % float(seconds)).encode())
                time.sleep(seconds * 1.3 + 1.0)
                self.s.read(self.s.in_waiting or 1)
            finally:
                self.busy = False

    def prime_start(self, rpm=100.0):
        """Begin a hold-to-run prime: kick off a continuous run on the Pico and DON'T wait.
        prime_stop() ends it. Uses prime_run() (streams steps, O(1) RAM -- a long prime via the old
        table-based path would MemoryError on the Pico)."""
        with self._lock:
            self.busy = True
            self.s.reset_input_buffer()
            self.s.write(("_p.prime_run(%r)\r\n" % float(rpm)).encode())

    def prime_stop(self):
        """Interrupt the running prime and de-energize. Ctrl-C raises KeyboardInterrupt inside
        prime_run(), whose finally de-energizes; the extra disable() is belt-and-suspenders."""
        try:
            self.s.write(b"\x03")            # interrupt the continuous loop
            time.sleep(0.15)
            self.s.write(b"_p.disable()\r\n")
            time.sleep(0.1)
            self.s.reset_input_buffer()
        finally:
            self.busy = False

    def off(self):
        """De-energize immediately (safety)."""
        with self._lock:
            self._raw("_p.disable()", 0.15)

    def close(self):
        try:
            self.off(); self.s.close()
        except Exception:
            pass
