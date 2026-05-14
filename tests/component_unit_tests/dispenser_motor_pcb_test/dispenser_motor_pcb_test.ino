#include <Arduino.h>
#include "A4988.h"

#define MOTOR_STEPS 200
#define NORMAL_RPM 2
#define FAST_RPM 4
#define MICROSTEPS 16

#define STEP_PIN 3
#define DIR_PIN 2
#define EN_PIN 12
#define RST_PIN 5
#define SLP_PIN 4
#define FEED_BTN 15
#define MS1_PIN 11
#define MS2_PIN 10
#define MS3_PIN 9

// #define BEAM_BREAK_PIN 16

A4988 stepper(MOTOR_STEPS, DIR_PIN, STEP_PIN, EN_PIN, MS1_PIN, MS2_PIN, MS3_PIN);

void dispense() {
  Serial.println("STATUS:DISPENSING");
  stepper.enable();
  delay(50);

  stepper.setRPM(NORMAL_RPM);
  stepper.rotate(3.15);

  delay(100);

  stepper.setRPM(NORMAL_RPM);
  stepper.rotate(-1);

  // future: if(digitalRead(BEAM_BREAK_PIN) == LOW) { Serial.println("STATUS:SUCCESS"); }

  stepper.disable();
  Serial.println("STATUS:READY");
}

void setup() {
  Serial.begin(115200);

  pinMode(EN_PIN, OUTPUT);
  pinMode(RST_PIN, OUTPUT);
  pinMode(SLP_PIN, OUTPUT);
  pinMode(FEED_BTN, INPUT_PULLDOWN);
  // pinMode(BEAM_BREAK_PIN, INPUT_PULLUP);

  digitalWrite(RST_PIN, HIGH);
  digitalWrite(SLP_PIN, HIGH);
  digitalWrite(EN_PIN, LOW);

  stepper.begin(NORMAL_RPM, MICROSTEPS);
  stepper.setSpeedProfile(BasicStepperDriver::LINEAR_SPEED, 200, 200);
  stepper.setEnableActiveState(LOW);
  stepper.disable();

  Serial.println("SYSTEM:INITIALIZED");
}

void loop() {
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();

    if (input.equalsIgnoreCase("d")) {
      dispense();
    } else if (input.length() > 0) {
      int degrees = input.toInt();
      Serial.print("ROTATING:");
      Serial.println(degrees);
      stepper.enable();
      stepper.rotate(degrees);
      stepper.disable();
    }
  }

  if (digitalRead(FEED_BTN) == HIGH) {
    delay(50);
    dispense();
    while (digitalRead(FEED_BTN) == HIGH);
  }
}
