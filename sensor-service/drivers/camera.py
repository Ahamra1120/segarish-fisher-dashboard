"""IMX135 camera over the CSI ribbon cable, via libcamera/picamera2.

picamera2 is normally installed system-wide via `apt install
python3-picamera2` on Raspberry Pi OS (it wraps libcamera, which needs
matching native bindings — a plain `pip install` won't work), so the venv
running sensor-service on the Pi should be created with
`--system-site-packages` to see it. See README.md for the exact setup.
"""
import io
import logging

log = logging.getLogger(__name__)

try:
    from picamera2 import Picamera2

    _HARDWARE_AVAILABLE = True
except ImportError:
    _HARDWARE_AVAILABLE = False


class CameraDriver:
    def __init__(self, config):
        self.cfg = config
        self._cam = None
        if not _HARDWARE_AVAILABLE:
            return
        try:
            self._cam = Picamera2()
            still_config = self._cam.create_still_configuration(
                main={"size": (config.CAMERA_WIDTH, config.CAMERA_HEIGHT)}
            )
            self._cam.configure(still_config)
            self._cam.start()
        except Exception as e:  # noqa: BLE001
            log.warning("Camera: failed to init picamera2 (%s)", e)
            self._cam = None

    @property
    def available(self):
        return self._cam is not None

    def capture_jpeg_bytes(self) -> bytes:
        stream = io.BytesIO()
        self._cam.capture_file(stream, format="jpeg")
        return stream.getvalue()

    def close(self):
        if self._cam:
            self._cam.close()
