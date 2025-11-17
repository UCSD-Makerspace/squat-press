#include <Arduino.h>
#include "A4988.h"

#define MOTOR_STEPS 200
#define NORMAL_RPM 10
#define FAST_RPM 20

// Pin setup
#define DIR 13
#define STEP 12

// #define MS1 22
// #define MS2 23
// #define MS3 21
#define SLP 5

// Microstepping mo de
#define MICROSTEPS 1

A4988 stepper(MOTOR_STEPS, DIR, STEP, SLP);

void setup() {
    Serial.begin(115200);
    delay(1000);

    stepper.begin(NORMAL_RPM, MICROSTEPS);
    stepper.setEnableActiveState(HIGH);
    stepper.disable();

    Serial.println("Stepper ready.");
    delay(1000);
}

void dispense_pellet() {
    stepper.enable();
    delay(50);
    Serial.println("Pellet dispense begun");
    stepper.setRPM(NORMAL_RPM);
    stepper.rotate(55);
    Serial.println("Rotated 55 degrees");

    delay(100); // experiment with this timing. we want this as fast as possible
    stepper.setRPM(FAST_RPM);
    stepper.rotate(-10);
    Serial.println("Rotated -10 degrees");
    stepper.disable();
}

void loop() {
    if (Serial.available() > 0) {
        String input = Serial.readStringUntil('\n');
        input.trim();

        if (input.equalsIgnoreCase("d")) {
            dispense_pellet(); 
        } else if (input.length() > 0) {
            int degrees = input.toInt();

            Serial.print("Received command: ");
            Serial.println(degrees);

            stepper.rotate(degrees);
        }
    }
    else
    {
        delay(200);
    }
}
