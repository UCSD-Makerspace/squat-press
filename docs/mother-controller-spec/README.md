# Mother Controller — spec bundle

Design constraints + context for the **mother controller** board (sensor integrated on-board,
pump as its own separate PCB; rail and scale excluded). This is a *deliverable/spec snapshot*,
not live code.

**The documentation is the source of truth in the wiki:**

- Compiled page: [`wiki/mother-controller.md`](../../wiki/mother-controller.md)
- Raw design docs (immutable sources): [`wiki/sources/mother-controller/`](../../wiki/sources/mother-controller/)
  — system overview, sensor subsystem, pump subsystem, integration constraints, design checklist,
  sensor calibration protocol, and the LX3302A EEPROM dump.

**Firmware to carry forward lives with the code, not here** (no duplicated copies):

- Pump (Pico + TMC2209): [`components/PeristalticPump/`](../../components/PeristalticPump/)
- Sensor decoder (PIO-SENT): [`components/LinearSensor/pico_viewer/`](../../components/LinearSensor/pico_viewer/)

**Shippable bundle:** the zipped hand-off given to an external builder is
`Downloads\mother_controller_handoff.zip` (a point-in-time export). Regenerate it from the wiki
sources + the `components/` firmware when the design advances.
