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

// ── Motion calibration ────────────────────────────────────────
constexpr int MICROSTEP_VALUE = 16;
constexpr float MICROSTEPS_PER_MM = 458.0f * MICROSTEP_VALUE;

// ── Sampling stats ────────────────────────────────────────────
volatile uint32_t total_switches = 0;
volatile uint32_t session_start_us = 0;

// ─────────────────────────────────────────────────────────────

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

// ─────────────────────────────────────────────────────────────

void checkEnablePin()
{
    if (!digitalRead(ENABLE_PIN))
    {
        for (int i = 0; i < 3; i++)
        {
            delay(1);
            if (digitalRead(ENABLE_PIN))
                return;
        }

        stepper_driver.disable();
        Serial0.println("\n\nStopping — printing session stats...");

        if (total_switches > 0 && session_start_us > 0)
        {
            uint32_t elapsed_us = micros() - session_start_us;
            float elapsed_s = elapsed_us / 1e6f;
            float avg_hz = total_switches / elapsed_s;
            Serial0.printf("Total direction switches : %lu\n", total_switches);
            Serial0.printf("Total elapsed time       : %.2f s\n", elapsed_s);
            Serial0.printf("Average switch rate      : %.1f Hz\n", avg_hz);
        }
        else
        {
            Serial0.println("No data recorded.");
        }

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

// ─────────────────────────────────────────────────────────────
// Sync pulse to Pi:
//   200us HIGH = UP stroke
//   600us HIGH = DOWN stroke
// Pi measures pulse width on the falling edge to determine direction.

void syncStrokeStart(bool going_up)
{
    digitalWrite(RPI_SYNC_PIN, HIGH);
    delayMicroseconds(going_up ? 200 : 600);
    digitalWrite(RPI_SYNC_PIN, LOW);
    delayMicroseconds(100); // brief settle before motor starts
}

// ─────────────────────────────────────────────────────────────

void printMotionProfile(int velocity_usteps, uint32_t stroke_us)
{
    float stroke_s = stroke_us / 1e6f;
    float mm_moved = ((float)velocity_usteps * stroke_s) / MICROSTEPS_PER_MM;
    float mm_per_sec = (float)velocity_usteps / MICROSTEPS_PER_MM;
    float full_travel_mm = mm_moved * 2;

    Serial0.println("════════════════════════════════════════");
    Serial0.println("  MOTION PROFILE (ground truth)");
    Serial0.println("════════════════════════════════════════");
    Serial0.printf("  Velocity          : %d usteps/s\n", velocity_usteps);
    Serial0.printf("  Velocity          : %.3f mm/s\n", mm_per_sec);
    Serial0.printf("  Stroke duration   : %lu us (%.1f ms)\n", stroke_us, stroke_us / 1000.0f);
    Serial0.printf("  Distance/stroke   : %.4f mm\n", mm_moved);
    Serial0.printf("  Full cycle (up+dn): %.4f mm\n", full_travel_mm);
    Serial0.printf("  Microsteps/mm     : %.1f\n", MICROSTEPS_PER_MM);
    Serial0.println("════════════════════════════════════════");
    Serial0.println("  Sync pin: 200us pulse = UP, 600us pulse = DOWN");
    Serial0.println("  Pi matches pulse timestamp to sensor window.");
    Serial0.println("════════════════════════════════════════\n");
}

// ─────────────────────────────────────────────────────────────

void jitterTest()
{
    const int velocity = 2000 * MICROSTEP_VALUE;
    const uint32_t STROKE_DURATION_US = 5000;      // 5ms per half-stroke
    const uint32_t COAST_DOWN_MS = 100;            // settle between strokes
    const int NUM_STROKES_PER_BURST = 2;           // 2 full up+down cycles per burst
    const uint32_t PAUSE_BETWEEN_BURSTS_MS = 1000; // 1s between bursts

    uint32_t report_window_start = micros();
    uint32_t switches_this_window = 0;

    stepper_driver.disableStealthChop();
    stepper_driver.enable();
    indicateMoving();

    printMotionProfile(velocity, STROKE_DURATION_US);

    session_start_us = micros();
    Serial0.println("Jitter test started. Pull ENABLE low to stop and print stats.");
    Serial0.println("stroke_no | direction | expected_mm | actual_us");

    while (true)
    {
        for (int stroke = 0; stroke < NUM_STROKES_PER_BURST * 2; stroke++)
        {
            checkEnablePin();

            bool going_up = (stroke % 2 == 0);
            // ── 1. Set direction ───────────────────────────────────────
            if (going_up)
                stepper_driver.disableInverseMotorDirection();
            else
                stepper_driver.enableInverseMotorDirection();

            // ── 2. Fire sync pulse to Pi (encodes direction in width) ──
            //       Do this BEFORE moveAtVelocity so Pi timestamp aligns
            //       with actual motion start as closely as possible.
            syncStrokeStart(going_up);

            // ── 3. Start motor ─────────────────────────────────────────
            stepper_driver.moveAtVelocity(velocity);

            // ── 4. Hold for stroke duration ────────────────────────────
            uint32_t stroke_start = micros();
            while (micros() - stroke_start < STROKE_DURATION_US)
            { /* spin */
            }
            uint32_t actual_us = micros() - stroke_start;

            // ── 5. Brake ───────────────────────────────────────────────
            stepper_driver.moveAtVelocity(0);

            // ── 6. Log ground truth for this stroke ────────────────────
            float actual_mm = ((float)velocity * (actual_us / 1e6f)) / MICROSTEPS_PER_MM;
            Serial0.printf("%9lu | %9s | %11.4f mm | %lu us\n",
                           total_switches,
                           going_up ? "UP" : "DOWN",
                           actual_mm,
                           actual_us);

            total_switches++;
            switches_this_window++;

            // ── 7. Settle before next stroke ───────────────────────────
            indicateStopped();
            delay(COAST_DOWN_MS);
            indicateMoving();
        }

        // ── End of burst ───────────────────────────────────────────────
        stepper_driver.moveAtVelocity(0);
        indicateStopped();

        uint32_t now = micros();
        if (now - report_window_start >= 1000000)
        {
            float elapsed_s = (now - report_window_start) / 1e6f;
            Serial0.printf("── window: %lu switches | %.1f Hz | total: %lu ──\n",
                           switches_this_window,
                           switches_this_window / elapsed_s,
                           total_switches);
            switches_this_window = 0;
            report_window_start = now;
        }

        uint32_t pause_start = millis();
        while (millis() - pause_start < PAUSE_BETWEEN_BURSTS_MS)
        {
            checkEnablePin();
            delay(10);
        }

        indicateMoving();
    }
}

// ─────────────────────────────────────────────────────────────

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
    digitalWrite(RPI_SYNC_PIN, LOW);

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

// ─────────────────────────────────────────────────────────────

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