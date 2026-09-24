# Integration Constraints — the electrical must-reads

These are the hard constraints that cost the most bench time to discover. Violating any of them produces
**intermittent, misleading** failures (data corruption, USB dropouts, freezes) that look like software bugs.
Read this before laying out either board or the interconnect.

---

## 1. ⚠ 24 V → SENT coupling — the #1 reason the pump is a SEPARATE board

**Finding (A/B confirmed, vetted by adversarial review):** with the pump's **24 V rail ON**, the decoded SENT
count on the sensor **collapsed / scrambled to CRC 0 %**; with **24 V OFF** it was clean (~700 fps, CRC 100 %).

- **It is electrical noise from the 24 V subsystem, not CPU load, not the code, not the stepper chopper**
  (the motor is de-energized at idle). SENT is uniquely fragile: all its information is in **falling-edge
  timing** (±0.5 tick ≈ ±3 µs at a 6 µs tick), while USB is differential/error-corrected — so SENT dies while
  USB survives.
- **Path PROVEN conducted through the shared USB ground** between the pump Pico and the host: with 24 V ON but
  the pump Pico's **USB unplugged**, SENT went back to CRC 100 % / count steady. Mains-earth/radiated ruled out.
- **⚠ Setup-dependent:** the corruption was on an **older PCB sensor build**; the **v1 breadboard** sensor node +
  its wiring showed **no coupling** (CRC 100 % through a live dose, 24 V on). So the coupling depends on the
  sensor node's ground path. **Design defensively — assume it will couple — and always re-test CRC with 24 V on.**

**Design rules for the mother controller:**
1. **Keep the pump's 24 V return current OUT of the sensor's SENT ground.** The pump being a separate PCB is
   the first line of defense; the second is **galvanic isolation at the pump interface**.
2. **Put a USB isolator on the pump link** (bench-proven fix = "keep data, break ground" = the unplug test):
   **ADuM4160 / ADuM3160** USB isolator (both Full-Speed; they differ in isolation kV, not speed). Power the
   pump-side of the isolator from an **isolated 24 V→5 V DC-DC (~1–2 W)** referenced to driver ground, and
   **set the Full-Speed strap.**
3. Alternative if you can cleanly separate ground planes: a digital isolator (ISO7741/ADuM1401) on
   STEP/DIR/EN — cheaper, but needs a ground-plane cut and pulling MS1/MS2 low + editing `pump.py` to stop
   driving them. The USB isolator is usually the more practical choice.
4. **Star/separate grounds:** sensor analog/SENT ground must not be a return path for motor current. Treat the
   24 V motor loop as a dirty domain and keep it physically and electrically away from the SENT trace and the
   sensor 5 V/3V3.

---

## 2. ⚠ USB inrush — the pump cannot share a loaded USB controller

Plugging the pump Pico directly into a **busy** Pi USB controller (even with **24 V OFF**) stalled the whole
controller: pump `can't set config #1, error -62` (→ no serial port), and it **took the rail's CP210x down with
it** (`-110`), needing a reboot. Root cause = **inrush/contention on an already-loaded bus**, not a broken board
(with the bus otherwise empty the pump enumerates clean and dispenses fine).

**Design rules:**
- Route the pump through a **powered USB hub** (or the isolator's own powered side) so its inrush is absorbed and
  doesn't fault the host controller. This is also where the §1 USB isolator lives.
- If the mother controller provides the USB host directly, give the **pump port its own power budget / current
  limiting / soft-start**, isolated from the sensor port.
- Connect-order-dependent coexistence (pump first, then others) works hub-free on the bench but is **fragile**
  (any mid-run re-enumeration breaks it). For an unattended product, **isolate/hub it properly** — don't rely on order.

---

## 3. ⚠ 24 V power sequencing

- **Never toggle 24 V while the system is running.** The transient knocks the pump Pico (and any shared serial
  device) off the USB bus and freezes the host.
- **Sequence:** bring **24 V up before** launching the control software; bring it **down after** stopping it.
- If the mother controller controls the 24 V rail, gate it so it can't be switched mid-session, and expose a
  clean "arm 24 V → start" / "stop → disarm 24 V" order.

---

## 4. Grounding, shorts, and physical robustness

- **No board on bare metal.** On the bench a board resting on metal shorted underside pads and produced
  *constantly changing* symptoms (power dropout, USB flapping, signal flipping). On the PCB: solid ground
  plane, no exposed shortable pads, proper standoffs/enclosure. **Rule of thumb: intermittent power/USB/signal
  that keeps changing character = suspect a physical short before cables/firmware.**
- **USB connector mechanical robustness is a top reliability item.** The bench's chronic "won't arm" was the
  sensor Pico's **USB connector flapping** (marginal connector/cable). Use solid, strain-relieved USB connectors
  — ideally board-integrated rather than a mini/micro dongle that can wiggle.

---

## 5. Device identity (if the host sees multiple USB serial devices)

USB port names **shuffle** between boots/reconnects (the same device has appeared as ACM0, ACM1, ACM2). The
bench software resolves devices **by content, never by fixed port**:
- **pump** = the RP2040 whose flash carries `pump.py`
- **sensor** = the bare RP2040 (no stored program)

If the mother controller enumerates both Picos over USB, preserve this content-based detection (or give each a
distinct, stable USB serial number / VID:PID) so the host binds the right role every time.

---

## 6. Summary of galvanic domains

```
   ┌─ SENSOR / LOGIC domain ─────────────┐        ┌─ PUMP / 24 V domain (DIRTY) ──────────┐
   │  5 V (Pico VBUS) → sensor + shifter  │        │  24 V motor rail → TMC2209 → ST42     │
   │  3V3 logic, SENT (timing-critical)   │  ⇎     │  driver ground = motor return         │
   │  host USB ground                     │ ISOLATE│  pump-Pico 5 V from isolated DC-DC    │
   └──────────────────────────────────────┘        └───────────────────────────────────────┘
        keep SENT ground clean                 USB isolator (ADuM4160) breaks the ground tie
```

The single most important layout goal: **the timing-critical SENT ground and the 24 V motor return must be in
separate, isolated domains, joined only through a data-only (galvanically isolated) link.**
