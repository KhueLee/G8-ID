"""Cân điện tử RS232 (cân phát liên tục từng dòng khối lượng, g hoặc kg).

Khác bản cũ:
  - Một luồng đọc riêng có timeout, không dùng sự kiện DataReceived (nguyên nhân treo khi
    đóng cổng ở bản WinForms) -> đóng cổng luôn trả về trong < 1 s.
  - Quá stale_s không có dòng mới => coi như MẤT CÂN (không dùng lại số cũ).
  - Quá reopen_s không có dữ liệu => tự đóng/mở lại cổng; mở lỗi thì thử lại, lùi dần 3->30 s.
"""
import logging
import re
import threading
import time

import serial

log = logging.getLogger("device.scale")
raw_log = logging.getLogger("raw.scale")

_NUM = re.compile(r"[-+]?\s*\d+(?:\.\d+)?")


def parse_weight(line):
    """'ST,GS,+  1.234kg' -> 1234 ; '  300 g' -> 300 ; không có số -> None."""
    m = _NUM.search(line)
    if not m:
        return None
    value = float(m.group(0).replace(" ", ""))
    if "kg" in line.lower():
        value *= 1000
    return int(round(value))


def open_serial(cfg, timeout):
    return serial.Serial(port=cfg["port"], baudrate=int(cfg["baudrate"]),
                         bytesize=int(cfg.get("bytesize", 8)),
                         parity=str(cfg.get("parity", "N"))[:1].upper(),
                         stopbits=float(cfg.get("stopbits", 1)),
                         timeout=timeout, write_timeout=1.0)


class SerialScale:
    name = "SCALE"

    def __init__(self, cfg, raw=False):
        self.cfg, self.raw = cfg, raw
        self._ser = None
        self._stop = threading.Event()
        self._thread = None
        self._weight = None
        self._last_rx = 0.0
        self._opened_at = 0.0
        self._error = "chưa kết nối"

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="scale", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._close()

    def _close(self):
        ser, self._ser = self._ser, None
        if ser is not None:
            try:
                ser.close()
                log.info("Đã đóng cổng cân %s", self.cfg["port"])
            except Exception as e:
                log.warning("Lỗi đóng cổng cân: %s", e)

    def _run(self):
        backoff = 3
        buf = b""
        while not self._stop.is_set():
            if self._ser is None:
                try:
                    self._ser = open_serial(self.cfg, timeout=0.2)
                    self._opened_at = time.time()
                    self._error = "đã mở cổng, chờ dữ liệu"
                    buf, backoff = b"", 3
                    log.info("Mở cổng cân %s @%s OK", self.cfg["port"], self.cfg["baudrate"])
                except Exception as e:
                    self._error = f"không mở được {self.cfg['port']}: {e}"
                    log.warning("Cân: %s - thử lại sau %d s", self._error, backoff)
                    self._stop.wait(backoff)
                    backoff = min(backoff * 2, 30)
                    continue
            try:
                chunk = self._ser.read(256)
            except Exception as e:
                self._error = f"lỗi đọc: {e}"
                log.warning("Cân: %s - mở lại cổng", self._error)
                self._close()
                self._stop.wait(1)
                continue
            if chunk:
                if self.raw:
                    raw_log.info("RX %s", chunk.hex(" "))
                buf += chunk
                parts = re.split(rb"[\r\n]+", buf)
                buf = parts.pop()[-64:]
                for p in parts:
                    w = parse_weight(p.decode("ascii", "ignore"))
                    if w is not None:
                        self._weight, self._last_rx, self._error = w, time.time(), ""
            else:
                idle = time.time() - max(self._last_rx, self._opened_at)
                if idle > float(self.cfg.get("reopen_s", 10)):
                    self._error = f"không có dữ liệu {idle:.0f} s"
                    log.warning("Cân im lặng %.0f s - đóng/mở lại cổng %s", idle, self.cfg["port"])
                    self._close()

    @property
    def connected(self):
        return time.time() - self._last_rx <= float(self.cfg.get("stale_s", 2.0))

    def read(self):
        """Khối lượng mới nhất (g); None nếu đang mất tín hiệu cân."""
        return self._weight if self.connected else None

    def status(self):
        return {"ok": self.connected, "detail": self._error or f"{self.cfg['port']}"}
