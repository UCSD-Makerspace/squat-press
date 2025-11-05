#include <Arduino.h>
#include "BasicStepperDriver.h"

#define MOTOR_STEPS 200
#define RPM 120

// Pin setup
#define DIR 18
#define STEP 19

// Optional microstep pins (unused for now)
#define MICROSTEP_1 22
#define MICROSTEP_2 23
#define MICROSTEP_3 1

// Microstepping mode (matches your driver switch setting)
#define MICROSTEPS 1

BasicStepperDriver stepper(MOTOR_STEPS, DIR, STEP);

void setup() {
    Serial.begin(115200);
    stepper.begin(RPM, MICROSTEPS);
    Serial.println("Stepper ready.");
}

void loop() {
    if (Serial.available() > 0) {
        string input = Serial.readStringUntil('\n');
        input.trim();

        if (input.length() > 0) {
            float degrees = input.toFloat();

            int steps = round(degrees / (360.0 / (MOTOR_STEPS * MICROSTEPS)));
            Serial.print("Received command: ");
            Serial.print(degrees);
            Serial.print(" degrees -> ");
            Serial.print(steps);
            Serial.println(" steps");

            stepper.rotate(steps);
        }
    }
}
