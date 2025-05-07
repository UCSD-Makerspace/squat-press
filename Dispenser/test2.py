from enum import Enum
from typing import Tuple

class MicrosteppingMode(Enum):
    FULL = 1
    HALF = 2
    QUARTER = 4
    EIGHTH = 8
    SIXTEENTH = 16

    @property
    def pin_values(self) -> Tuple[int, int]:
        _pin_values = {
            MicrosteppingMode.FULL: (0, 0),
            MicrosteppingMode.HALF: (1, 0),
            MicrosteppingMode.QUARTER: (0, 1),
            MicrosteppingMode.EIGHTH: (1, 1),
            MicrosteppingMode.SIXTEENTH: (1, 1),
        }
        return _pin_values[self]


a = MicrosteppingMode.EIGHTH
b,c = a.pin_values
print(a,b,c)
