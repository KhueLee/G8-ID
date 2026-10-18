"""Máy in tem Godex qua thư viện EZio (EZio64.dll / EZio32.dll) - đúng driver của bản cũ.

Tem thùng 70x40 mm (560x320 điểm, 8 điểm/mm), bố cục từ bản 2.3.0:
  khu 1 (trên mã QR): giờ in tem (không in ngày in - ngày trên tem chỉ là NSX)
  cột trái: logo, số thứ tự thùng, tên sản phẩm (chữ đậm, tối đa 3 dòng), mã pallet, mã lệnh, NSX
  khu 2 (dải dưới cùng): mã định danh
Mọi lệnh gọi DLL đi qua một khoá để không gọi chồng nhau.
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
FW_EXTRALIGHT, FW_SEMIBOLD, FW_BOLD, FW_HEAVY = 200, 600, 700, 900
SEQ_X, SEQ_Y, SEQ_H = 125, 18, 64      # số thứ tự thùng: chữ to, cạnh logo, trái mã QR
QR_X, QR_Y, QR_MUL = 300, 36, 9        # mã QR (bản 25 ô = 225 điểm) chừa chỗ khu 1 và khu 2
STAMP_X, STAMP_Y, STAMP_H = 300, 8, 20  # khu 1: giờ in
LEFT_X, LEFT_W = 10, 282               # cột chữ bên trái mã QR
NAME_Y, NAME_BOX, NAME_LEAD = 86, 96, 3  # tên sản phẩm: khung cao 96 điểm, dòng cách dòng h+3
NAME_SIZES = (32, 30, 28, 26, 24, 22, 20, 18)  # cỡ chữ tên SP: lấy cỡ lớn nhất còn vừa khung
NAME_MAX_LINES = 3
LINE_Y, LINE_GAP, LINE_H = 186, 32, 22  # mã pallet / mã lệnh / NSX
CODE_Y, CODE_H = 286, 28               # khu 2: mã định danh, cả chiều ngang tem
CHAR_W = 0.55                          # bề rộng trung bình 1 ký tự Arial ~ 0,55 x cỡ chữ


def name_lines(h):
    """Số dòng tên SP vừa khung với cỡ chữ h."""
    return max(1, min(NAME_MAX_LINES, (NAME_BOX + NAME_LEAD) // (h + NAME_LEAD)))


def wrap_name(text, width=LEFT_W, sizes=NAME_SIZES):
    """Chia tên sản phẩm thành các dòng vừa `width` điểm, số dòng theo name_lines();
    trả (cỡ chữ, [dòng]) với cỡ chữ lớn nhất còn vừa khung."""
    words = str(text or "").split()
    for h in sizes:
        cap = max(1, int(width / (h * CHAR_W)))
        lines, cur = [], ""
        for w in words:
            while len(w) > cap:                      # từ quá dài (mã liền): cắt cứng
                if cur:
                    lines.append(cur)
                    cur = ""
                lines.append(w[:cap])
                w = w[cap:]
            if not cur:
                cur = w
            elif len(cur) + 1 + len(w) <= cap:
                cur += " " + w
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) <= name_lines(h):
            return h, lines
    n = name_lines(sizes[-1])
    rest = " ".join(lines[n - 1:])
    return sizes[-1], lines[:n - 1] + [rest[:cap - 1] + "…" if len(rest) > cap else rest]


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
            target = self.cfg.get("com_port") or ""
            if not target:
                raise RuntimeError("kiểu kết nối COM nhưng chưa chọn cổng (None)")
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

    def print_carton(self, parcel_code, item_name, pallet_code, wh_code, mfg_date="", seq=None):
        with self._lock:
            if not self._open:
                return False
            try:
                dll = self._dll
                stamp = datetime.datetime.now().strftime("%Hh%Mp%Ss")
                self._begin(dll)
                logo = config.path(self.cfg.get("logo") or "drivers/G8_Label.bmp")
                if os.path.exists(logo):
                    dll.putimage(10, 20, logo.encode("mbcs"), 0)
                if seq:
                    self._text(dll, SEQ_X, SEQ_Y, SEQ_H, str(seq), FW_HEAVY)
                dll.ecTextOutR(STAMP_X, STAMP_Y, STAMP_H, b"Arial", stamp.encode("mbcs"), 0,
                               FW_SEMIBOLD, 0)
                h, name = wrap_name(item_name)
                for i, line in enumerate(name):
                    self._text(dll, LEFT_X, NAME_Y + i * (h + NAME_LEAD), h, line, FW_BOLD)
                for i, line in enumerate(("Ma Pallet : " + str(pallet_code),
                                          "Ma Lenh   : " + str(wh_code),
                                          "NSX       : " + str(mfg_date))):
                    self._text(dll, LEFT_X, LINE_Y + i * LINE_GAP, LINE_H, line, FW_SEMIBOLD)
                self._text(dll, LEFT_X, CODE_Y, CODE_H, str(parcel_code), FW_HEAVY)
                code = str(parcel_code).encode("mbcs")
                dll.Bar_QRcode(QR_X, QR_Y, 3, 2, b"L", 0, QR_MUL, len(code), 0, code)
                dll.sendcommand(b"E")
                return True
            except Exception as e:
                self._error = f"lỗi in: {e}"
                log.exception("In tem thùng lỗi - sẽ kết nối lại máy in")
                self._close()
                return False

    def status(self):
        return {"ok": self._open, "detail": self._error or str(self.cfg.get("connect_type"))}
