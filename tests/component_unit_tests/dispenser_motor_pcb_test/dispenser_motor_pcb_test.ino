#include <Arduino.h>
#include "A4988.h"

#define MOTOR_STEPS 200
#define RPM 10

// Pin mapping from your PCB layout
#define EN 12
#define MS1 11
#define MS2 10
#define MS3 9
#define RST 7
#define SLP 6
#define STEP 5
#define DIR 4

// Use the 7-argument constructor supported by your library
// Format: steps, dir, step, enable, ms1, ms2, ms3
A4988 stepper(MOTOR_STEPS, DIR, STEP, EN, MS1, MS2, MS3);

void setup()
{
  Serial.begin(115200);

  // Manually handle the pins the library doesn't cover
  pinMode(RST, OUTPUT);
  pinMode(SLP, OUTPUT);

  // A4988 requires RST and SLP to be HIGH to run
  digitalWrite(RST, HIGH);
  digitalWrite(SLP, HIGH);

  delay(1000);

  stepper.begin(RPM);
  stepper.setEnableActiveState(LOW);
  stepper.enable();

  // Set microstepping to 1 (Full Step)
  stepper.setMicrostep(1);

  Serial.println("Stepper ready and awake.");
}

void loop()
{
  Serial.println("Rotating 45 degrees...");
  stepper.rotate(45);
  delay(10000);
}