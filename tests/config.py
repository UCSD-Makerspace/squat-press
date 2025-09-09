from dataclasses import dataclass

@dataclass
class SystemConfig:
    SAMPLE_TIME: float = 0.2
    RUN_TIME: float = 6000000000.0
    THRESHOLD: float = 0.7
    ALPHA: float = 0.6
    SENT_GPIO: int = 18
    DISPENSE_ANGLE: float = 180.0
    DISPENSE_DIR: int = 1
    MOTOR_COOLDOWN: float = 1.0