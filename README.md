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



## Usage 

Run `run.sh` to run the basic SENT reader.
```
./run.sh
```

