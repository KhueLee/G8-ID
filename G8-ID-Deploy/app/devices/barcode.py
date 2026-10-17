"""Đầu đọc mã vạch RS232 kiểu Honeywell: kích đọc 16 54 0D, tắt kích 16 55 0D (như bản cũ)."""
import logging
import threading
import time

from .scale import open_serial

log = logging.getLogger("device.barcode")
raw_log = logging.getLogger("raw.barcode")

TRIGGER_ON = b"\x16T\r"
TRIGGER_OFF = b"\x16U\r"


class SerialBarcode:
    name = "BARCODE"

    def __init__(self, cfg, raw=False):
        self.cfg, self.raw = cfg, raw
        self._ser = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._error = "chưa kết nối"

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._keepalive, name="barcode", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        with self._lock:
            self._close()

    def _close(self):
        ser, self._ser = self._ser, None
        if ser is not None:
            try:
                ser.write(TRIGGER_OFF)
            except Exception:
                pass
            try:
                ser.close()
                log.info("Đã đóng cổng đầu đọc %s", self.cfg["port"])
            except Exception as e:
                log.warning("Lỗi đóng cổng đầu đọc: %s", e)

    def _open(self):
        self._ser = open_serial(self.cfg, timeout=0.1)
        self._error = ""
        log.info("Mở cổng đầu đọc %s @%s OK", self.cfg["port"], self.cfg["baudrate"])

    def _keepalive(self):
        """Giữ cổng luôn mở; rớt thì tự nối lại (3 -> 30 s)."""
        if not self.cfg.get("port"):
            self._error = "không dùng (cổng None)"
            return
        backoff = 3
        while not self._stop.is_set():
            with self._lock:
                if self._ser is None:
                    try:
                        self._open()
                        backoff = 3
                    except Exception as e:
                        self._error = f"không mở được {self.cfg['port']}: {e}"
                        log.warning("Đầu đọc: %s - thử lại sau %d s", self._error, backoff)
            wait = 2 if self._ser is not None else backoff
            if self._ser is None:
                backoff = min(backoff * 2, 30)
            self._stop.wait(wait)

    @property
    def connected(self):
        return self._ser is not None

    def read(self, timeout_ms=5000, abort=None):
        """Kích đọc và chờ một mã. Trả '' nếu hết giờ / lỗi / bị dừng."""
        with self._lock:
            ser = self._ser
            if ser is None:
                return ""
            try:
                ser.reset_input_buffer()
                ser.write(TRIGGER_ON)
                deadline = time.time() + timeout_ms / 1000.0
                buf = b""
                while time.time() < deadline and not (abort and abort.is_set()):
                    chunk = ser.read(128)
                    if chunk:
                        if self.raw:
                            raw_log.info("RX %s", chunk.hex(" "))
                        buf += chunk
                        if buf.endswith((b"\r", b"\n")):
                            break
                    elif buf:
                        break  # đã có dữ liệu và đường truyền im 100 ms => hết bản tin
                ser.write(TRIGGER_OFF)
                return buf.decode("utf-8", "ignore").strip()
            except Exception as e:
                self._error = f"lỗi đọc: {e}"
                log.warning("Đầu đọc: %s - sẽ mở lại cổng", self._error)
                self._close()
                return ""

    def status(self):
        return {"ok": self.connected, "detail": self._error or self.cfg["port"]}
