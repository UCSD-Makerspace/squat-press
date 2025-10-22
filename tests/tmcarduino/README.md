# TMCArduino

Basic arduino code for controlling the TMC2209 using an ESP32.

This uses the Arduino package [TMC2209](https://github.com/janelia-arduino/TMC2209)

## Wiring

|ESP32|TMC2209|
|-----|-------|
| D23 | EN    |
| 3v3 | VDD   |
| GND | GND   |

## Single-wire UART

The ESP32 is connected to the TMC2209 over a single-wire UART interface on serial port 2.

TX2 and RX2 are connected together with a 1k resistor, and the combined wire goes straight to the UART pin on the TMC2209.

## Dev environment

This uses the Arduino Community Edition vscode extension.

1. Open the folder in vscode
2. Install ESP32 boards in the arduino board manager
3. Set the board to ESP32 Dev Module
4. Deploy

On linux, you may have to change the permissions on the serial port to be writable by the active user.