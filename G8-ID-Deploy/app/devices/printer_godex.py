"""Máy in tem Godex qua thư viện EZio (EZio64.dll / EZio32.dll) - đúng driver của bản cũ.

Bố cục tem thùng 70x40 mm và tem pallet giữ nguyên toạ độ, cỡ chữ, tham số QR của
CPrinterGodex.cs. Mọi lệnh gọi DLL đi qua một khoá để không gọi chồng nhau.
"""
import ctypes
import datetime
import logging
import os
import struct
import threading

from .. import config

log = logging.getLogger("device.printer")

LABEL_W_MM, LABEL_H_MM, GAP_MM = 70, 40, 3
SPEED_IPS, DARKNESS = 4, 10
FW_EXTRALIGHT, FW_SEMIBOLD = 200, 600


class GodexPrinter:
    name = "PRINTER"

    def __init__(self, cfg):
        self.cfg = cfg
        self._dll = None
        self._open = False
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._error = "chưa kết nối"

    # ---- nạp DLL -------------------------------------------------------------
    def _load(self):
        if self._dll is not None:
            return self._dll
        is64 = struct.calcsize("P") == 8
        path = config.path("drivers", "EZio64.dll" if is64 else "EZio32.dll")
        dll = ctypes.CDLL(path) if is64 else ctypes.WinDLL(path)
        c = ctypes
        sig = {
            "openport": ([c.c_char_p], c.c_bool),
            "OpenUSB": ([c.c_char_p], c.c_int),
            "OpenDriver": ([c.c_char_p], c.c_bool),
            "OpenNet": ([c.c_char_p, c.c_char_p], c.c_bool),
            "setbaudrate": ([c.c_int], c.c_int),
            "closeport": ([], None),
            "sendcommand": ([c.c_char_p], c.c_int),
            "FindFirstUSB": ([c.c_char_p], c.c_int),
            "putimage": ([c.c_int, c.c_int, c.c_char_p, c.c_int], c.c_int),
            "ecTextOutR": ([c.c_int, c.c_int, c.c_int, c.c_char_p, c.c_char_p,
                            c.c_int, c.c_int, c.c_int], c.c_int),
            "ecTextOutRW": ([c.c_int, c.c_int, c.c_int, c.c_char_p, c.c_char_p,
                             c.c_int, c.c_int, c.c_int, c.c_int], c.c_int),
            "Bar_QRcode": ([c.c_int, c.c_int, c.c_int, c.c_int, c.c_char_p, c.c_int,
                            c.c_int, c.c_int, c.c_int, c.c_char_p], c.c_int),
        }
        for fn, (argtypes, restype) in sig.items():
            f = getattr(dll, fn)
            f.argtypes, f.restype = argtypes, restype
        self._dll = dll
        log.info("Đã nạp %s", path)
        return dll

    # ---- kết nối -------------------------------------------------------------
    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._keepalive, name="printer", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        with self._lock:
            self._close()

    def _close(self):
        if self._open and self._dll is not None:
            try:
                self._dll.closeport()
                log.info("Đã đóng cổng máy in")
            except Exception as e:
                log.warning("Lỗi đóng cổng máy in: %s", e)
        self._open = False

    def _find_usb(self, dll):
        buf = ctypes.create_string_buffer(256)
        if dll.FindFirstUSB(buf) == 1:
            return buf.value.decode("mbcs", "ignore")
        return ""

    def _connect(self):
        dll = self._load()
        kind = str(self.cfg.get("connect_type", "USB")).upper()
        ok = False
        if kind == "USB":
            name = self.cfg.get("usb_name") or self._find_usb(dll)
            if not name:
                raise RuntimeError("không tìm thấy máy in Godex trên USB")
            ok = dll.OpenUSB(name.encode("mbcs")) == 1
            target = "USB " + name
        elif kind == "COM":
            target = self.cfg["com_port"]
            num = "".join(ch for ch in target if ch.isdigit())
            ok = bool(dll.openport(num.encode()))
            if ok and self.cfg.get("baudrate"):
                dll.setbaudrate(int(self.cfg["baudrate"]))
        elif kind == "LAN":
            target = f"{self.cfg['lan_ip']}:{self.cfg['lan_port']}"
            ok = bool(dll.OpenNet(self.cfg["lan_ip"].encode(), str(self.cfg["lan_port"]).encode()))
        else:  # DRIVER: hàng đợi in của Windows
            target = "driver " + self.cfg["driver_name"]
            ok = bool(dll.OpenDriver(self.cfg["driver_name"].encode("mbcs")))
        if not ok:
            raise RuntimeError(f"không mở được máy in ({target})")
        self._open, self._error = True, ""
        log.info("Kết nối máy in OK (%s)", target)

    def _keepalive(self):
        backoff = 3
        while not self._stop.is_set():
            with self._lock:
                if not self._open:
                    try:
                        self._connect()
                        backoff = 3
                    except Exception as e:
                        self._error = str(e)
                        log.warning("Máy in: %s - thử lại sau %d s", e, backoff)
            wait = 5 if self._open else backoff
            if not self._open:
                backoff = min(backoff * 2, 30)
            self._stop.wait(wait)

    @property
    def connected(self):
        return self._open

    # ---- in ------------------------------------------------------------------
    def _begin(self, dll):
        for cmd in (f"^Q{LABEL_H_MM},{GAP_MM}", f"^W{LABEL_W_MM}", "^P1", "^C1",
                    f"^S{SPEED_IPS}", f"^H{DARKNESS}", "^L"):
            dll.sendcommand(cmd.encode())

    def _text(self, dll, x, y, h, text, weight):
        data = text.encode("utf-16-le")
        dll.ecTextOutRW(x, y, h, b"Arial", data, 0, weight, 0, len(text))

    def print_carton(self, parcel_code, item_name, pallet_code, wh_code, weight_g, mfg_date=""):
        with self._lock:
            if not self._open:
                return False
            try:
                dll = self._dll
                stamp = datetime.datetime.now().strftime("%Hh%Mp%Ss %d/%m/%Y")
                self._begin(dll)
                logo = config.path(self.cfg.get("logo") or "drivers/G8_Label.bmp")
                if os.path.exists(logo):
                    dll.putimage(10, 20, logo.encode("mbcs"), 0)
                dll.ecTextOutR(10, 90, 18, b"Arial", stamp.encode("mbcs"), 0, FW_EXTRALIGHT, 0)
                y = 130
                for line in ("Ten SP    : " + str(item_name), "Ma SP     : " + str(parcel_code),
                             "Ma Pallet : " + str(pallet_code), "Ma Lenh   : " + str(wh_code),
                             "K.Luong   : " + str(weight_g) + " gam"):
                    self._text(dll, 10, y, 18, line, FW_SEMIBOLD)
                    y += 30
                code = str(parcel_code).encode("mbcs")
                dll.Bar_QRcode(280, 40, 3, 2, b"L", 0, 10, len(code), 0, code)
                dll.sendcommand(b"E")
                return True
            except Exception as e:
                self._error = f"lỗi in: {e}"
                log.exception("In tem thùng lỗi - sẽ kết nối lại máy in")
                self._close()
                return False

    def print_pallet(self, pallet_code):
        with self._lock:
            if not self._open:
                return False
            try:
                dll = self._dll
                self._begin(dll)
                code = str(pallet_code).encode("mbcs")
                dll.Bar_QRcode(100, 20, 2, 1, b"L", 0, 10, len(code), 0, code)
                dll.sendcommand(b"E")
                return True
            except Exception as e:
                self._error = f"lỗi in: {e}"
                log.exception("In tem pallet lỗi - sẽ kết nối lại máy in")
                self._close()
                return False

    def status(self):
        return {"ok": self._open, "detail": self._error or str(self.cfg.get("connect_type"))}
