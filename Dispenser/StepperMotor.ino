const int DIR = 4;
const int STEP = 2;
const int microMode = 8; // microstep mode, default is 1/8 so 8; ex: 1/16 would be 16
// full rotation * microstep divider
const int steps = 200 * microMode;
bool dir = LOW;

void setup()
{
    // setup step and dir pins as outputs
    pinMode(STEP, OUTPUT);
    pinMode(DIR, OUTPUT);
    Serial.begin(9600);
}

void loop()
{
    // change direction every loop
    dir = !dir;
    digitalWrite(DIR, dir);
    Serial.printf("Direction: %d\n", dir);
    // toggle STEP to move
    for (int x = 0; x < steps; x++)
    {
        digitalWrite(STEP, HIGH);
        delay(2);
        digitalWrite(STEP, LOW);
        delay(2);
    }
    delay(1000); // 1 second delay
}