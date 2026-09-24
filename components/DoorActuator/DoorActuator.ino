// DoorActuator.ino — cycle a Glideforce GF01-120503-1-66 micro linear actuator
// (12 V, 30 mm stroke, 150 mA no-load / 400 mA max, BUILT-IN limit switches)
// N times at a slow speed to simulate a mouse door opening and closing.
// Runs STANDALONE: plug in 12 V and it starts; no computer needed.
//
// Hardware: Arduino UNO R3 + HW-130 shield (L293D, Adafruit Motor Shield v1 clone)
//   actuator red/black -> shield M1 terminal (swap the two wires if open/close are reversed)
//   12 V DC supply     -> shield EXT_PWR (+ / GND)
//   PWR jumper ON      -> the 12 V also feeds the Uno's Vin, so no USB is needed
// Library: "Adafruit Motor Shield library" (v1, AFMotor.h)
//
// The actuator's internal limit switches cut the motor at each end of travel, so
// STROKE_MS only has to be LONGER than the real travel time — overshooting is harmless
// (the motor draws ~0 mA while parked on a limit switch).
//
// Status LED (on-board L / D13):  ON = cycling,  slow blink = all cycles done.
// Power-cycle (or press RESET) to run again.

#include <AFMotor.h>

// ---------------- tunables ----------------
const int      N_CYCLES        = 100;   // up+down pairs
const uint8_t  SPEED           = 140;   // 0-255 PWM. 255 = full speed (~22 mm/s through the L293D).
                                        // Below ~90-100 the little gearmotor may hum without moving.
const uint32_t STROKE_MS       = 6000;  // drive time per direction (> travel time; limit switch stops it)
const uint32_t DWELL_OPEN_MS   = 3000;  // pause at the top (door open)
const uint32_t DWELL_CLOSED_MS = 3000;  // pause at the bottom (door closed) before the next lift
const uint32_t STARTUP_MS      = 1500;  // grace period after power-on before the first move
const bool     INVERT          = false; // set true if the rod EXTENDS during "homing (retract)" —
                                        // same as swapping the two wires at M1, but in software

// Even slower than PWM allows? Pulse full-speed bursts instead (no stalling at low duty).
const bool     PULSED       = false;
const uint32_t PULSE_ON_MS  = 60;    // ~20% average speed with 60 on / 240 off
const uint32_t PULSE_OFF_MS = 240;
// ------------------------------------------

AF_DCMotor door(1);   // M1 terminal. Use AF_DCMotor door(1, MOTOR12_64KHZ) for quieter PWM.

// Logical directions; INVERT decides which H-bridge polarity each one is.
const uint8_t UP   = INVERT ? BACKWARD : FORWARD;   // extend = door open
const uint8_t DOWN = INVERT ? FORWARD  : BACKWARD;  // retract = door closed

// Drive in one direction for `ms`, then coast.
void drive(uint8_t dir, uint32_t ms) {
  uint32_t t0 = millis();
  if (!PULSED) {
    door.setSpeed(SPEED);
    door.run(dir);
    while (millis() - t0 < ms) {}
  } else {
    door.setSpeed(255);
    while (millis() - t0 < ms) {
      door.run(dir);     delay(PULSE_ON_MS);
      door.run(RELEASE); delay(PULSE_OFF_MS);
    }
  }
  door.run(RELEASE);
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);          // "running"
  Serial.begin(115200);                     // harmless with no USB attached
  door.run(RELEASE);
  delay(STARTUP_MS);

  Serial.println("Door cycle test: homing (retract = closed)...");
  drive(DOWN, STROKE_MS);
  delay(DWELL_CLOSED_MS);

  uint32_t tStart = millis();
  for (int i = 1; i <= N_CYCLES; i++) {
    Serial.print("cycle "); Serial.print(i); Serial.print("/"); Serial.print(N_CYCLES);
    Serial.print("  up...");
    drive(UP, STROKE_MS);          // extend = open
    delay(DWELL_OPEN_MS);
    Serial.print(" down...");
    drive(DOWN, STROKE_MS);        // retract = close
    delay(DWELL_CLOSED_MS);
    Serial.print("  t="); Serial.print((millis() - tStart) / 1000); Serial.println(" s");
  }

  door.run(RELEASE);
  Serial.println("DONE - all cycles complete. Power-cycle or RESET to run again.");
}

void loop() {
  // finished: slow blink forever
  digitalWrite(LED_BUILTIN, HIGH); delay(1000);
  digitalWrite(LED_BUILTIN, LOW);  delay(1000);
}
