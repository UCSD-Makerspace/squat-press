#!/bin/bash

# Start the pigpio daemon
sudo pigpiod

# Run the SENT reader script
python3 tests/SENTTest.py

