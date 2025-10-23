#include <TMC2209.h>

TMC2209 stepper_driver;

HardwareSerial &serial_stream = Serial2;
const long SERIAL_BAUD_RATE = 115200;
const int RX_PIN = 16;
const int TX_PIN = 17;
const uint8_t REPLY_DELAY = 4;

bool connected = false;

TMC2209::Status status;
constexpr int NUM_STEPS = 9;
const int velocities[NUM_STEPS] = {250, 500, 1000, 1500, 2000, 3000, 4000, 2000, 500};
const int waitTimesMs[NUM_STEPS] = {40, 40,  40,   40,   40,   40,   100,  40,   40};

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

    stepper_driver.setMicrostepsPerStep(1);
    stepper_driver.enableAutomaticCurrentScaling();
    stepper_driver.disableStealthChop();
    stepper_driver.setStandstillMode(TMC2209::StandstillMode::BRAKING);
    stepper_driver.setRunCurrent(50);
    stepper_driver.setHoldCurrent(10);
}

void printBinaryWithNibbles(uint32_t value)
{
    for (int bit = 31; bit >= 0; --bit)
    {
        Serial.print((value >> bit) & 1U);
        if (bit % 4 == 0 && bit != 0)
            Serial.print('|');
    }
    Serial.println();
}

void printStatusBitfield(const TMC2209::Status &status)
{
    uint32_t bits = 0;
    memcpy(&bits, &status, sizeof(bits));
    Serial.print("TMC2209 Status: 0x");
    // Serial.printf("%08X  ", bits);
    printBinaryWithNibbles(bits);
}

void setup()
{
    delay(500);
    Serial0.begin(115200);

    connectAndSetDefaultConfig();
    
    stepper_driver.enable();
}

void loop()
{
    connected = stepper_driver.isSetupAndCommunicating();
    if (!connected)
    {
        Serial0.println("Stepper disconnected!");
        connectAndSetDefaultConfig();
        delay(500);
    }
    status = stepper_driver.getStatus();
    printStatusBitfield(status);

    stepper_driver.disableInverseMotorDirection();
    Serial0.println("Moving up");
    for (int i = 0; i < NUM_STEPS; i++)
    {
        stepper_driver.moveAtVelocity(velocities[i]);
        delay(waitTimesMs[i] / 2);
        status = stepper_driver.getStatus();
        printStatusBitfield(status);
        delay(waitTimesMs[i] / 2);
    }
    
    stepper_driver.moveAtVelocity(0);
    stepper_driver.enableInverseMotorDirection();
    status = stepper_driver.getStatus();
    printStatusBitfield(status);
    delay(100);

    Serial0.println("Moving down");
    for (int i = 0; i < NUM_STEPS; i++)
    {
        stepper_driver.moveAtVelocity(velocities[i]);
        delay(waitTimesMs[i] / 2);
        status = stepper_driver.getStatus();
        printStatusBitfield(status);
        delay(waitTimesMs[i] / 2);
    }

    stepper_driver.moveAtVelocity(0);
    delay(50);
    stepper_driver.setStandstillMode(TMC2209::StandstillMode::NORMAL);
    delay(1000);
    stepper_driver.setStandstillMode(TMC2209::StandstillMode::BRAKING);
}