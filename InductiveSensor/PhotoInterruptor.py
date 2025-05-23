from DAC import DAC


class PhotoInterruptor(DAC):
    def __init__(self, pi=None, clk=1_600_000, threshold=0.08) -> None:
        super().__init__(pi, clk)
        self._detected = False
        self.threshold = threshold

    def get_detected(self) -> bool:
        return self._detected

    def update(self) -> bool:
        super().update()
        self._detected = super().get_data_percent() < self.threshold
        return self._detected


if __name__ == "__main__":
    import time
    sensor = PhotoInterruptor()
    while True:
        sensor.update()
        print(f"Detected: {sensor.get_detected()}, Data: {sensor.get_data_percent():0.5f}")
        time.sleep(0.05)
