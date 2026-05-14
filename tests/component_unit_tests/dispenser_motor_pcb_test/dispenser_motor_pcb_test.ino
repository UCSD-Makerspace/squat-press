#include <Arduino.h>
#include "A4988.h"

#define MOTOR_STEPS 200
#define RPM 30

#define STEP_PIN 3
#define DIR_PIN 2
#define EN_PIN 9
#define RST_PIN 5
#define SLP_PIN 4
#define FEED_BTN 15

// #define BEAM_BREAK_PIN 16 

A4988 stepper(MOTOR_STEPS, DIR_PIN, STEP_PIN, EN_PIN);

void dispense() {
  Serial.println("STATUS:DISPENSING");
  digitalWrite(SLP_PIN, HIGH); // Wake up driver
  delay(2);                    // Minimal wake-up time for A4988
  
  stepper.rotate(51);
  
  // Optional: Check beam break here to verify pellet drop
  // if(digitalRead(BEAM_BREAK_PIN) == LOW) { Serial.println("STATUS:SUCCESS"); }
  
  digitalWrite(SLP_PIN, LOW);  // Put driver back to sleep to save power/heat
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
  digitalWrite(SLP_PIN, LOW);  // Start in sleep mode to prevent motor hiss
  digitalWrite(EN_PIN, LOW);
  
  stepper.begin(RPM);
  stepper.setEnableActiveState(LOW);
  stepper.enable();
  
  Serial.println("SYSTEM:INITIALIZED");
}

void loop() {
  // 1. Check for Command from Raspberry Pi (USB Serial)
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == 'D') {          // 'D' for Dispense
      dispense();
    }
  }

  // 2. Check for Physical Manual Feed Button
  if (digitalRead(FEED_BTN) == HIGH) {
    delay(50);                 // Debounce
    dispense();
    while(digitalRead(FEED_BTN) == HIGH); // Wait for release
  }
}