#include <Arduino.h>
#include "A4988.h"

#define MOTOR_STEPS 200
#define RPM 10

// Pin setup
#define DIR 13
#define STEP 12

// #define MS1 22
// #define MS2 23
// #define MS3 21
#define SLP 5

// Microstepping mode
#define MICROSTEPS 1

A4988 stepper(MOTOR_STEPS, DIR, STEP, SLP);

void setup() {
    Serial.begin(115200);
    delay(1000);
    stepper.begin(RPM);
    stepper.setEnableActiveState(LOW);
    stepper.enable();
    // stepper.setMicrostep(MICROSTEPS);
    Serial.println("Stepper ready.");
    delay(1000);
}

void loop() {
    if (Serial.available() > 0) {
        String input = Serial.readStringUntil('\n');
        input.trim();

        if (input.equals("d") || input.equals("D")) {
            dispense_degrees(45); 
        } else if (input.length() > 0) {
            int degrees = input.toInt();

            Serial.print("Received command: ");
            Serial.print(degrees);

            stepper.rotate(degrees);
        }
    }
    delay(1000);
}
