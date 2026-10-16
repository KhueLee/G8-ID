"""Thiết bị giả cho chế độ MANUAL: nói chuyện với công cụ mô phỏng (run_simulator.bat) qua HTTP."""
import json
import logging
import threading
import time
import urllib.request

log = logging.getLogger("device.sim")


def _call(base, path, body=None, timeout=2.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, method="GET" if data is None else "POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class _Base:
    name = "SIM"

    def __init__(self, base):
        self.base = base
        self._ok = False
        self._error = "công cụ mô phỏng chưa chạy"

    def start(self):
        pass

    def stop(self):
        pass

    @property
    def connected(self):
        return self._ok

    def status(self):
        return {"ok": self._ok, "detail": self._error or "mô phỏng"}

    def _fail(self, e):
        if self._ok:
            log.warning("%s mô phỏng mất kết nối: %s", self.name, e)
        self._ok, self._error = False, "công cụ mô phỏng chưa chạy"


class SimScale(_Base):
    name = "SCALE"

    def __init__(self, base):
        super().__init__(base)
        self._weight = None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sim-scale", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self):
        while not self._stop.is_set():
            try:
                r = _call(self.base, "/dev/scale", timeout=1.0)
                self._ok = bool(r.get("online"))
                self._error = "" if self._ok else "cân mô phỏng đang tắt"
                self._weight = r.get("weight")
                self._stop.wait(0.1)
            except Exception as e:
                self._fail(e)
                self._weight = None
                self._stop.wait(1.0)

    def read(self):
        return self._weight if self._ok else None


class _Polled(_Base):
    """Thiết bị chỉ được gọi khi cần: thêm luồng nhỏ dò kết nối để chỉ báo trên màn hình đúng."""
    probe = "/dev/ping"

    def __init__(self, base):
        super().__init__(base)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sim-" + self.name.lower(),
                                        daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self):
        while not self._stop.is_set():
            try:
                r = _call(self.base, self.probe, timeout=1.0)
                self._ok = bool(r.get(self.name.lower(), True))
                self._error = "" if self._ok else "thiết bị mô phỏng đang tắt"
            except Exception as e:
                self._fail(e)
            self._stop.wait(1.0)


class SimBarcode(_Polled):
    name = "BARCODE"

    def read(self, timeout_ms=5000, abort=None):
        # Hỏi từng lát 400 ms để bấm Dừng là thoát ngay, giống đầu đọc thật.
        deadline = time.time() + timeout_ms / 1000.0
        try:
            while not (abort and abort.is_set()):
                left = deadline - time.time()
                r = _call(self.base, "/dev/barcode/read",
                          {"timeout_ms": 400, "final": left <= 0.4}, timeout=5)
                code = str(r.get("code") or "").strip()
                if code or left <= 0.4:
                    return code
        except Exception as e:
            self._fail(e)
        return ""


class SimPrinter(_Polled):
    name = "PRINTER"

    def print_carton(self, parcel_code, item_name, pallet_code, wh_code, weight_g, mfg_date="",
                     seq=None):
        return self._print({"type": "carton", "code": parcel_code, "item_name": item_name,
                            "pallet": pallet_code, "wh_code": wh_code, "weight": weight_g,
                            "mfg_date": mfg_date, "seq": seq})

    def _print(self, body):
        try:
            body["time"] = time.strftime("%H:%M:%S")
            return bool(_call(self.base, "/dev/printer/print", body).get("ok"))
        except Exception as e:
            self._fail(e)
            return False


class SimPlc(_Polled):
    name = "PLC"

    def __init__(self, base):
        super().__init__(base)
        self._want = "off"

    def set_light(self, color):
        if color == self._want and self._ok:
            return
        self._want = color
        try:
            _call(self.base, "/dev/plc/light", {"color": color}, timeout=1.0)
        except Exception as e:
            self._fail(e)

    def stop(self):
        try:
            _call(self.base, "/dev/plc/light", {"color": "off"}, timeout=0.5)
        except Exception:
            pass
        super().stop()
