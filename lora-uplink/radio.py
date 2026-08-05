"""SX1276/RFM95 LoRa radio over SPI, via adafruit-circuitpython-rfm9x
(Blinka), plus a simulated fallback with the same interface.

No delivery-ACK protocol exists yet (there's no gateway to define one
with) — `receive()` is here so `LORA_WAIT_ACK` can be flipped on later
once a gateway that replies with a short ack packet exists, without
touching app.py's send loop.
"""
import logging
import random

log = logging.getLogger(__name__)

try:
    import board
    import busio
    import digitalio
    import adafruit_rfm9x

    _HARDWARE_AVAILABLE = True
except (ImportError, NotImplementedError):
    # NotImplementedError: Blinka raises this on platforms with no GPIO
    # support at all (e.g. a plain Windows/Linux dev machine).
    _HARDWARE_AVAILABLE = False


class Rfm9xRadio:
    def __init__(self, config):
        self.cfg = config
        self._rfm = None
        if not _HARDWARE_AVAILABLE:
            return
        try:
            spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
            cs = digitalio.DigitalInOut(getattr(board, config.LORA_CS_PIN))
            reset = digitalio.DigitalInOut(getattr(board, config.LORA_RESET_PIN))
            rfm = adafruit_rfm9x.RFM9x(spi, cs, reset, config.LORA_FREQ_MHZ)
            rfm.tx_power = config.LORA_TX_POWER_DBM
            rfm.spreading_factor = config.LORA_SPREADING_FACTOR
            rfm.signal_bandwidth = config.LORA_BANDWIDTH_HZ
            rfm.coding_rate = config.LORA_CODING_RATE
            self._rfm = rfm
        except Exception as e:  # noqa: BLE001
            log.warning("RFM9x: failed to init radio (%s)", e)
            self._rfm = None

    @property
    def available(self):
        return self._rfm is not None

    def send(self, data: bytes) -> bool:
        self._rfm.send(data)
        return True

    def receive(self, timeout=1.0):
        return self._rfm.receive(timeout=timeout)


class SimulatedRadio:
    """No radio hardware present (or LORA_MODE=simulate) -- logs what
    would have been transmitted and reports success, with an optional
    forced failure rate (SIMULATE_FAIL_RATE) so the buffer/retry path can
    be exercised without real hardware."""

    def __init__(self, config):
        self.cfg = config

    @property
    def available(self):
        return True

    def send(self, data: bytes) -> bool:
        if random.random() < self.cfg.SIMULATE_FAIL_RATE:
            log.info("LoRa TX (simulated) FAILED (%d bytes): %s", len(data), data[:120])
            return False
        log.info("LoRa TX (simulated) OK (%d bytes): %s", len(data), data[:120])
        return True

    def receive(self, timeout=1.0):
        return None
