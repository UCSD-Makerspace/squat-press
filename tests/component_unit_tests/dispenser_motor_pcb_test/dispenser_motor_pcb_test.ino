#include <Arduino.h>
#include "A4988.h"

#define MOTOR_STEPS 200
#define RPM 10

// Pin mapping from your PCB layout
#define STEP_PIN 3
#define DIR_PIN 2
#define EN_PIN 9
#define RST_PIN 5
#define SLP_PIN 4
#define FEED_BTN 15

// Use the 7-argument constructor supported by your library
// Format: steps, dir, step, enable, ms1, ms2, ms3
A4988 stepper(MOTOR_STEPS, DIR_PIN, STEP_PIN, EN_PIN, RST_PIN, SLP_PIN, FEED_BTN);

void setup()
{
  Serial.begin(115200);

  // Manually handle the pins the library doesn't cover
  pinMode(RST_PIN, OUTPUT);
  pinMode(SLP_PIN, OUTPUT);

  // A4988 requires RST and SLP to be HIGH to run
  digitalWrite(RST_PIN, HIGH);
  digitalWrite(SLP_PIN, HIGH);

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