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

void checkStatus(const TMC2209::Status &status)
{
    uint32_t bits = 0;
    memcpy(&bits, &status, sizeof(bits));
    Serial0.print("TMC2209 Status: 0x");
    for (int bit = 31; bit >= 0; --bit)
    {
        Serial0.print((bits >> bit) & 1U);
        if (bit % 4 == 0 && bit != 0)
            Serial0.print('|');
    }
    Serial0.println();

    if (status.over_temperature_warning)
    {
        overheated = true;
    }
    if (status.over_temperature_shutdown)
    {
        overheated_shutdown = true;
    }
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

void checkForOverheat()
{
    // Wait extra time if overheated
    if (overheated)
    {
        Serial0.println("Overheated!");
        delay(8000);
        overheated = false;
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

void loop()
{
    stepper_driver.disableStealthChop();
    checkEnablePin();

    connected = stepper_driver.isSetupAndCommunicating();
    if (!connected)
    {
        Serial0.println("Stepper disconnected!");
        connectAndSetDefaultConfig();
        delay(500);
    }
    status = stepper_driver.getStatus();
    checkStatus(status);
    checkForOverheat();
    delay(200);

    stepper_driver.disableInverseMotorDirection();
    Serial0.println("Moving up");
    indicateMoving();
    bool gpio_write_done = false;
    for (int i = 0; i < NUM_STEPS; i++)
    {
        stepper_driver.moveAtVelocity(velocities[i]);
        if (gpio_write_done == false) {
            digitalWrite(RPI_SYNC_PIN, HIGH);
        }
        gpio_write_done = true;
        delay(waitTimesMs[i] / 2);
        status = stepper_driver.getStatus();
        checkStatus(status);
        delay(waitTimesMs[i] / 2);
    }

    checkForOverheat();
    stepper_driver.moveAtVelocity(0);
    stepper_driver.enableInverseMotorDirection();
    status = stepper_driver.getStatus();
    checkStatus(status);
    delay(100);

    Serial0.println("Moving down");
    for (int i = 0; i < NUM_STEPS; i++)
    {
        stepper_driver.moveAtVelocity(velocities[i]);
        delay(waitTimesMs[i] * 0.75);
        status = stepper_driver.getStatus();
        checkStatus(status);
    }
    stepper_driver.moveAtVelocity(0);
    delay(100);
    stepper_driver.setRunCurrent(5);
    stepper_driver.enableStealthChop();
    stepper_driver.setStallGuardThreshold(100);
    stepper_driver.moveAtVelocity(250 * MICROSTEP_VALUE);
    delay(50);
    int timeElapsedMS = 0;
    uint16_t sgStatus;
    while (timeElapsedMS < 2000)
    {
        status = stepper_driver.getStatus();
        sgStatus = stepper_driver.getStallGuardResult();
        Serial0.printf("SG: %d\n", sgStatus);
        if (sgStatus < 100)
        {
            digitalWrite(RPI_SYNC_PIN, LOW);
            break;
        }
        delay(5);
    }

    stepper_driver.disableStealthChop();
    stepper_driver.moveAtVelocity(0);
    stepper_driver.disable();
    indicateStopped();
    
    checkForOverheat();
    checkEnablePin();
    // Kill program entirely if shutdown
    if (overheated_shutdown)
    {
        while (true)
        {
            Serial0.println("Overtemperature shutdown! Stopping Test.");
            delay(10000);
        }
    }
    delay(2000);
    stepper_driver.enable();
    stepper_driver.setStandstillMode(TMC2209::StandstillMode::BRAKING);
    stepper_driver.setRunCurrent(50);
}