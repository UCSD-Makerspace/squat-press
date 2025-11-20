#include <Arduino.h>
#include "A4988.h"
#include <SPI.h>

#define MOTOR_STEPS 200
#define NORMAL_RPM 10
#define FAST_RPM 20

// Pin setup
#define DIR 13
#define STEP 12
#define UART_RX 15
#define UART_TX 14

// #define MS1 22
// #define MS2 23
// #define MS3 21
#define SLP 5

// Microstepping mode
#define MICROSTEPS 1

A4988 stepper(MOTOR_STEPS, DIR, STEP, SLP);
HardwareSerial SerialUART(1);

const SPISettings spiSettings(14000000, MSBFIRST, SPI_MODE0);
uint16_t value;

void setup()
{
    SerialUART.begin(115200);
    SPI.begin(SCK, MISO, MOSI, 10);
    HardwareSerial SerialUART(1);
    SerialUART.begin(115200, SERIAL_8N1, UART_RX, UART_TX);

    delay(5000);

    stepper.begin(NORMAL_RPM, MICROSTEPS);
    stepper.setEnableActiveState(HIGH);
    stepper.disable();

    SerialUART.println("Stepper ready.");
    delay(1000);
}

void dispense_pellet() {
    stepper.enable();
    delay(50);
    SerialUART.println("Pellet dispense begun");
    stepper.setRPM(NORMAL_RPM);
    stepper.rotate(55);
    SerialUART.println("Rotated 55 degrees");

    delay(100); // experiment with this timing. we want this as fast as possible
    stepper.setRPM(NORMAL_RPM);
    stepper.rotate(-10);
    SerialUART.println("Rotated -10 degrees");
    stepper.disable();
}

uint8_t i = 0;
void loop() {
    i++;
    if (i >= 5)
    {
        i = 0;
        SPI.beginTransaction(spiSettings);
        SerialUART.print("Reading value: ");
        value = SPI.transfer16(0);
        SerialUART.println(value);
        SPI.endTransaction();
    }

    if (SerialUART.available() > 0) {
        String input = SerialUART.readStringUntil('\n');
        input.trim();

        if (input.equalsIgnoreCase("d")) {
            SerialUART.println("Dispensing pellet..."); 
            dispense_pellet(); 
        } else if (input.length() > 0) {
            int degrees = input.toInt();

            SerialUART.print("Received command: ");
            SerialUART.println(degrees);

            stepper.rotate(degrees);
        }
    }
    else
    {
        delay(200);
    }
}
