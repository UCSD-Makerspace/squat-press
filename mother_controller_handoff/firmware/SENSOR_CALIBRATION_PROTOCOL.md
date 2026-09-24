# LX3302A Sensor Calibration Protocol (rail-assisted region cal → SENT for the Pico)

Calibrate the LX3302A inductive sensor to the **region of interest (0–25 mm)** so it uses the
full output range over that window, using the **linear rail as the precision reference ruler**,
and output **SENT** so the Pico pipeline (`pico_pc.py`) can read it.

Last good run: **2026-06-29**, chip **ID 6880**, result **Max Error 0.195 % (8 LSB)**.

---

## Equipment / connections
- **IPCE** (Integrated Programming & Calibration Environment, v2.27.5) + **Microchip LXM9518 dongle** → enumerates as a COM port (e.g. **COM4**). Tabs: Settings / Measurement / Analysis.
- **Linear rail** (AZD-KD over RS-485) on **COM7**, driven by `rail_caljog.py` (Tkinter jog GUI) for precise 0.5 mm steps. *(Both tools run at once; different COM ports, no conflict.)*
- The sensor's target/slider is moved by the rail; the sensor measures its lift.

---

## 0. Prep (Settings tab)
1. **Back up the factory EEPROM**: `Save EEPROM to file`. (So you can `Load EEPROM from file` to restore if needed.)
2. **Set the SENT framing for the Pico** (must match the decoder):
   - **REFRESH = 500 Hz** (Miscellaneous Config)
   - **SENT CLK = 6 µs** (SENT Interface)
   - **WDSCALE = 2** (Miscellaneous Config)
   - **IO2 = `0101 = PP SENT`** (IO Select) — the output the Pico decodes.
3. **DEBUG = Enable** (Misc Calibration) — required so the Measurement tab streams live data for capture.
4. `Program eeprom to chip`.

## 1. Collect the bench sweep (Measurement tab)
1. Rail GUI: jog the slider to the **bottom/rest** (lift = 0), then **SET ZERO**.
2. IPCE: select **IO2 (SENT)** radio; confirm **No Fault**; click **Clear Data**.
3. At **0.00 mm** click **Capture Data**.
4. Rail GUI **JOG +0.5 ▲** → wait ~1 s to settle → IPCE **Capture Data**.
5. Repeat to **25.0 mm** → **51 captures total** (0, 0.5, … 25.0), each exactly 0.5 mm apart.
6. **Save Data** to an `.xlsx`.
7. ⚠️ **Check the Position column = 0…25 in 0.5 steps** (EP position = 25). If it saved as **0…50**
   (integer index), the tool assumed 1.0 mm/step (2× wrong) — set **End position = 25** so it is
   0, 0.5, … 25.0 (51 values). The *shape* of the cal is unaffected, but the mm axis must be honest.

## 2. Build the region linearization (Analysis tab)
1. **Load Bench Data From File** → the sweep you saved.
2. **Start position = 0**, **End position = 25**.
3. **START/END Output:Analog** = the analog endpoints (default 0.5 / 4.5 V). The **digital SENT range
   is the clamps** `HCLMP 3686 / LCLMP 409` (left side) — those are already set; you do **not** type
   them in the Output boxes.
4. **phase Cal = UNCHECKED**, **linear Cal = CHECKED**.
   - *Do NOT run phase cal on a region sweep* — phase/AFE cal needs the full signal swing; a partial
     window makes it worse. Phase cal is a one-time factory step.
5. Click **Auto Calibration**.
   - If you get **"Slope Data is negative but required output is positive — interchange START/END
     Output"**: swap the two Output:Analog values (→ START 4.5, END 0.5) and re-run. This makes the
     output **decrease with lift** (0 mm = high, 25 mm = low), matching the sensor's natural direction
     and the Pico `calibration.json`.
6. **Check Maximum Error** → should be **< ~1 %** (we got 0.195 %). The plotted curve should lie on
   the dotted diagonal.
7. **Update IC Settings**.

## 3. Program & deploy (Settings tab)
1. **DEBUG = Disable** ← important: DEBUG left on changes the output and **breaks the Pico's SENT decode**.
2. `Program eeprom to chip`.
3. **Verify**: jog 0 → 25 mm and confirm the SENT output swings **~3686 → ~409**, smoothly.
   - Best check is reading it on the **Pico** (the real deployment path).
   - In-tool: the GUI's IO2 SENT readout only refreshes in DEBUG mode, so with DEBUG off it can look
     stale — cross-check with IO1 PWM / IO3 DAC (they should be at the low end at 25 mm), or briefly
     re-enable DEBUG to watch IO2, then disable + re-program.

## 4. Update the Pico pipeline
- Set `calibration.json` (next to `pico_pc.py`) to the new linear map:
  ```json
  {"table": [[0, 3686], [25, 409]]}
  ```
- `pico_pc.py` fallback constants updated to `LCLMP, HCLMP, TRAVEL_MM = 3686, 409, 25.0`.
- Push `calibration.json` to the Pi (`~/induction/`) so the live dashboard uses it.

---

## Gotchas (learned the hard way)
- **Position must be real mm** (0.5 mm step, EP = 25), not the capture index (0–50) — else the stroke
  is 2× off.
- **phase Cal off** for region cals.
- **Negative-slope warning** → swap START/END Output.
- **DEBUG: Enable to capture, Disable to deploy.**
- **SENT framing 500 Hz / 6 µs / WDSCALE 2** must match what the Pico decoder expects (chip ID 6880).
- **Back up the factory EEPROM first.**

---

## TODO next calibration — drift headroom (deferred 2026-06-29)
Right now the chip **clamps** the SENT output at `HCLMP 3686 / LCLMP 409`, so beyond 0–25 mm it just
pins at the ends — drift below 0 mm or above 25 mm is invisible (the count can't pass 3686/409).
The Pico side is already ready for it: `pico_pc.py` `to_mm()` now **extrapolates** past the ends
(count > 3686 → negative mm, count < 409 → > 25 mm) and the plot y‑axis goes to −0.4 cm.

To make drift actually show, at the next cal **give the chip headroom**:
1. **Settings tab → Output Calibration:** raise **HCLMP** (3686 → e.g. 4000, or 4095 max) and lower
   **LCLMP** (409 → e.g. 200, or 0). Then **Program eeprom to chip**.
2. **Verify empirically:** push the slider just below 0 mm and confirm the SENT count climbs **past
   3686** (not just pins). If it still pins even with HCLMP raised, the limit is the **linearization**
   (X1–X7/Y1–Y7 flat‑lining past the last breakpoint), so instead **rebuild the cal with margin** —
   map 0–25 mm to ~**3500 → 600** so there's room inside the breakpoints.
3. (Separate knob: `DIAGPO` is for a real hard out‑of‑range FAULT, if ever wanted instead of drift.)
