# Squat-Press

Repository for the mice squat press system.

```
.                                                                                                       
├── ADC       - Python package for the MCP3201 ADC (used by dispenser, lx3302a)   
├── dispenser - Python package for the dispenser   
├── lx3302a   - Python package for the LX3302A inductive sensor   
├── pi        - Database source code   
└── tests     - Testing scripts   
```

## Installation

Run `install.sh` to install all required dependencies. 

'''
./install.sh
'''

## Hardware Setup

This system requires the [LX3302AL012 50mm Linear Inductive Position Sensor](https://www.microchip.com/en-us/development-tool/lxk3302al012) and a Raspberry Pi 4. (Note: A Pi 5 will not work with pigpio)

### Wiring

Use female-to-female dupont jumper wires to connect:
| PI               | LX3302A     |
| ---------------- | ----------- |
| Ground           | Ground      |
| 5v Power         | +5v supply  |
| GPIO 18 (pin 12) | IO 2 (SENT) |

![LX3302A](https://github.com/user-attachments/assets/7223d5bf-0087-47ec-a62d-9505fc646243)

![LX3302A Pinout](https://github.com/user-attachments/assets/a61832e2-810b-4193-ae6a-5ce1c3c29b71)

![Labeled Pi Pinout](https://github.com/user-attachments/assets/ff602767-0d61-4f26-b470-7c4de1c079db)




## Usage 

Run `run.sh` to run the basic SENT reader.
```
./run.sh
```

