#include <TMC2209.h>

TMC2209 stepper_driver;

HardwareSerial &serial_stream = Serial2;
const long SERIAL_BAUD_RATE = 115200;
const int RX_PIN = 16;
const int TX_PIN = 17;
const uint8_t REPLY_DELAY = 4;
const int ENABLE_PIN = 19;
const int RPI_SYNC_PIN = 5;

const int GREEN_LED_PIN = 2;
const int RED_LED_PIN = 4;

bool connected = false;
bool overheated = false;
bool overheated_shutdown = false;

TMC2209::Status status;
constexpr int NUM_STEPS = 9;
constexpr int MICROSTEP_VALUE = 16;
constexpr float UP_SPEED_SCALE = 0.75f;
const int velocities[NUM_STEPS] = {250 * MICROSTEP_VALUE, 500 * MICROSTEP_VALUE, 1000 * MICROSTEP_VALUE, 1500 * MICROSTEP_VALUE, 2000 * MICROSTEP_VALUE, 3000 * MICROSTEP_VALUE, 4000 * MICROSTEP_VALUE, 2000 * MICROSTEP_VALUE, 500 * MICROSTEP_VALUE};
const int waitTimesMs[NUM_STEPS] = {60, 60, 40, 40, 40, 40, 50, 40, 40};

void connectAndSetDefaultConfig()
{
    stepper_driver.setHardwareEnablePin(23);
    stepper_driver.setup(serial_stream, SERIAL_BAUD_RATE, TMC2209::SERIAL_ADDRESS_0, RX_PIN, TX_PIN);
    stepper_driver.setReplyDelay(REPLY_DELAY);

    Serial0.print("Connecting to driver...");

    connected = stepper_driver.isSetupAndCommunicating();
    while (!connected)
    {
        Serial0.print(".");
        delay(500);
        stepper_driver.setup(serial_stream, SERIAL_BAUD_RATE, TMC2209::SERIAL_ADDRESS_0, RX_PIN, TX_PIN);
        stepper_driver.setReplyDelay(REPLY_DELAY);

        connected = stepper_driver.isSetupAndCommunicating();
    }
    Serial0.println("\nConnected!\n");
    delay(500);

    stepper_driver.setMicrostepsPerStep(MICROSTEP_VALUE);
    stepper_driver.enableAutomaticCurrentScaling();
    stepper_driver.disableStealthChop();
    stepper_driver.setStandstillMode(TMC2209::StandstillMode::BRAKING);
    stepper_driver.setRunCurrent(50);
    stepper_driver.setHoldCurrent(20);
}

// If the enable pin is not pulled high, restart the ESP32.
void checkEnablePin()
{
    if (!digitalRead(ENABLE_PIN))
    {
        for (int i = 0; i < 3; i++)
        {
            delay(1);
            if (digitalRead(ENABLE_PIN))
            {
                return;
            }
        }
        stepper_driver.disable();
        Serial0.println("Stopping!");
        delay(200);
        ESP.restart();
    }
}

void indicateMoving()
{
    digitalWrite(GREEN_LED_PIN, HIGH);
    digitalWrite(RED_LED_PIN, LOW);
}

void indicateStopped()
{
    digitalWrite(GREEN_LED_PIN, LOW);
    digitalWrite(RED_LED_PIN, HIGH);
}

void setup()
{
    delay(500);
    Serial0.begin(115200);
    pinMode(ENABLE_PIN, INPUT_PULLDOWN);
    pinMode(GREEN_LED_PIN, OUTPUT);
    pinMode(RED_LED_PIN, OUTPUT);
    pinMode(RPI_SYNC_PIN, OUTPUT);
    digitalWrite(GREEN_LED_PIN, LOW);
    digitalWrite(RED_LED_PIN, HIGH);

    Serial0.print("Waiting for enable to be pulled high...");
    while (!digitalRead(ENABLE_PIN))
    {
        Serial0.print(".");
        delay(1000);
    }
    Serial0.println("\nEnabled! Starting program.");

    connectAndSetDefaultConfig();

    stepper_driver.enable();
}

void jitterTest()
{
    const int velocity = 2000 * MICROSTEP_VALUE;

    const uint32_t interval_us = 5000; // 5ms
    uint32_t last_switch = micros();
    bool moving_up = true;

    stepper_driver.disableStealthChop();
    
    while (true) {

        checkEnablePin();

        uint32_t now = micros();

        if (now - last_switch >= interval_us) {

            last_switch = now;

            if (moving_up) 
            {
                stepper_driver.disableInverseMotorDirection();
                stepper_driver.moveAtVelocity(velocity);
                digitalWrite(RPI_SYNC_PIN, HIGH);
            } 
            else 
            {
                stepper_driver.enableInverseMotorDirection();
                stepper_driver.moveAtVelocity(velocity);
                digitalWrite(RPI_SYNC_PIN, LOW);
            }
            moving_up = !moving_up;
        }
        delayMicroseconds(50);
    }
}

void loop()
{
    checkEnablePin();

    connected = stepper_driver.isSetupAndCommunicating();
    if (!connected)
    {
        Serial0.println("Stepper disconnected!");
        connectAndSetDefaultConfig();
        delay(500);
    }

    jitterTest();
}