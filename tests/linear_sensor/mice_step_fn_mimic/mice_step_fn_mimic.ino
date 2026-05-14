#include <TMC2209.h>

TMC2209 stepper_driver;

HardwareSerial &serial_stream = Serial2;
const long SERIAL_BAUD_RATE = 115200;

// --------- Pin Definitions ---------
const int RX_PIN = 16;
const int TX_PIN = 17;
const int ENABLE_PIN = 19;

const int RPI_SYNC_PIN = 5;
const int GREEN_LED_PIN = 2;
const int RED_LED_PIN = 4;

bool connected = false;

// --------- Physical Definitions -----------
constexpr int MICROSTEP_VALUE = 16;
constexpr float MICROSTEPS_PER_MM = 458.0f;
constexpr float SPEED_MULTIPLIER = 1.45f;
constexpr float UP_TRIM = 1.025f; // compensates for per-segment ramp-up lag; tune until reaching 19.5mm

// ── Motion profile (mouse lift CSV @ 120fps, step-function segments) ─────────
// frame  mm     Δmm    Δframes  Δt(ms)   v(mm/s)    v(usteps/s)
//  1      0.0
// 12      0.5   +0.5    11       92        5.5        2498
// 19      1.5   +1.0     7       58       17.1        7851
// 25      3.5   +2.0     6       50       40.0       18320
// 32      6.0   +2.5     7       58       42.9       19628
// 38      9.0   +3.0     6       50       60.0       27480
// 45     14.0   +5.0     7       58       85.7       39257
// 52     17.0   +3.0     7       58       51.4       23554
// 59     19.0   +2.0     7       58       34.3       15703
// 64     19.5   +0.5     5       42       12.0        5496
// ── hold 17ms at peak 19.5mm (frames 64-66) ──────────────────────────────────
// 82     14.5   -5.0    16      448       10.05      10050  (down, 33% slower, constant)
// 112     0.0  -14.5    30      440       10.05      10050  (down, 33% slower, constant)

const int NUM_UP_SEGMENTS = 9;
const int NUM_DOWN_SEGMENTS = 2;
const int HOLD_PEAK_MS = 17;

const int upVelocities[NUM_UP_SEGMENTS]     = { 2498,  7851, 18320, 19628, 27480, 39257, 23554, 15703,  5496};
const int upTimesMs[NUM_UP_SEGMENTS]        = {   92,    58,    50,    58,    50,    58,    58,    58,    42};

const int downVelocities[NUM_DOWN_SEGMENTS] = {10050, 10050};
const int downTimesMs[NUM_DOWN_SEGMENTS]    = {  448,   440};

void connectAndSetDefaultConfig()
{
    stepper_driver.setHardwareEnablePin(23);
    stepper_driver.setup(serial_stream, SERIAL_BAUD_RATE, TMC2209::SERIAL_ADDRESS_0, RX_PIN, TX_PIN);

    Serial0.print("Connecting to driver...");

    connected = stepper_driver.isSetupAndCommunicating();
    while (!connected)
    {
        Serial0.print(".");
        delay(500);
        stepper_driver.setup(serial_stream, SERIAL_BAUD_RATE, TMC2209::SERIAL_ADDRESS_0, RX_PIN, TX_PIN);

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

void checkEnablePin()
{
    if (!(digitalRead(ENABLE_PIN)))
    {
        for (int i = 0; i < 10; i++) {
            delay(1);
            if (digitalRead(ENABLE_PIN))
                return;
        }
        stepper_driver.disable();
        Serial0.println("Stopping! En pin not pulled high");
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

void stepperTest()
{
    // --- 2x step-function mimic of mouse lift (CSV @ 120fps) ---
    // segment 1: initiation, 0mm -> 0.5mm
    // segments 2-6: acceleration, 0.5mm -> 14mm
    // segments 7-9: deceleration to peak, 14mm -> 19.5mm
    while (true)
    {
        checkEnablePin();
        stepper_driver.enable();

        // -- upward phase --
        stepper_driver.disableInverseMotorDirection();
        digitalWrite(RPI_SYNC_PIN, HIGH);
        for (int i = 0; i < NUM_UP_SEGMENTS; i++)
        {
            stepper_driver.moveAtVelocity(static_cast<int>(upVelocities[i] * SPEED_MULTIPLIER * UP_TRIM));
            delay(static_cast<int>(upTimesMs[i] / SPEED_MULTIPLIER));
        }

        // -- hold at 19.5mm peak --
        stepper_driver.moveAtVelocity(0);
        delay(static_cast<int>(HOLD_PEAK_MS / SPEED_MULTIPLIER));

        // -- downward phase --
        stepper_driver.enableInverseMotorDirection();
        for (int i = 0; i < NUM_DOWN_SEGMENTS; i++)
        {
            stepper_driver.moveAtVelocity(static_cast<int>(downVelocities[i] * SPEED_MULTIPLIER * UP_TRIM));
            delay(static_cast<int>(downTimesMs[i] / SPEED_MULTIPLIER));
        }
        stepper_driver.moveAtVelocity(0);
        digitalWrite(RPI_SYNC_PIN, LOW);

        // disable motor and wait before next rep
        stepper_driver.disable();
        delay(5500);
        
    }

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
        Serial0.println("Not connected to driver! Restarting...");
        connectAndSetDefaultConfig();
        delay(500);
    }

    stepperTest();
}
