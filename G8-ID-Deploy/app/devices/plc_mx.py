"""PLC Mitsubishi + đèn tháp qua MX Component Version 5 (ActUtlType64) - driver của bản cũ.

Viết theo "MX Component Version 5 Reference Manual" (SH-082395ENG):
  - Mục 9.1: ActUtlType64 chỉ có 2 thuộc tính ActLogicalStationNumber và ActPassword; mọi thông
    số truyền thông (CPU, cổng, IP...) nằm trong Logical Station tạo bằng Communication Settings
    Utility - đúng cách bản cũ làm (CPLC.cs: ActLogicalStationNumber -> Open).
  - Mục 11.3: Open(), Close(), SetDevice(szDevice, lData), GetDevice(szDevice, lData) trả 0 khi
    thành công, khác 0 là mã lỗi (chương 13). Thiết bị bit chỉ dùng bit thấp nhất của lData.
  - Mục 11.1: control thuộc mô hình STA -> đối tượng COM chỉ được dùng trong đúng một luồng.
    Luồng nghiệp vụ chỉ đặt màu mong muốn rồi đi tiếp, nên PLC chậm/treo/mất kết nối không bao
    giờ làm treo việc cân - in.
  - Mục 11.1: kill tiến trình khi đang truyền thông có thể làm kẹt tiến trình khác -> luôn
    tắt đèn + Close() khi thoát.

ActUtlType64 là máy chủ COM ngoài tiến trình (ActUtlType64.exe) nên tạo theo CLSID; Python
32-bit trên máy chỉ có MX Component 4 thì rơi về ActUtlType.ActUtlType (DLL 32-bit).

Đèn tháp (CPLC.SetTrafficLightByM): M0 = đỏ, M1 = xanh, M2 = vàng, M10 = tắt.
"""
import logging
import threading
import time

log = logging.getLogger("device.plc")

COLORS = {"red": 0, "green": 1, "yellow": 2}

# CLSID của coclass ActUtlType64 (ActUtlType64Lib) - trùng với GUID trong MitsubishiPLC.dll bản cũ.
CLSID_ACTUTLTYPE64 = "{F0B1A112-BFCB-4DA3-9535-C296D69A17E0}"
PROGID_ACTUTLTYPE32 = "ActUtlType.ActUtlType"

ALREADY_OPEN = (0xF0000003, 0x01808001)
# Trích chương 13 (ERROR CODES) - các mã hay gặp ở trạm.
ERRORS = {
    0xF0000001: "MX Component chưa có license",
    0xF0000002: "không đọc được Logical Station - kiểm tra số Logical Station trong "
                "Communication Settings Utility",
    0xF0000003: "đã Open rồi",
    0xF0000004: "chưa Open",
    0xF0000005: "MX Component khởi tạo lỗi - khởi động lại máy / cài lại MX Component",
    0x01801006: "cấu hình module không khớp thực tế",
    0x01801007: "sai loại CPU trong Logical Station",
    0x01802001: "tên thiết bị PLC không hợp lệ",
    0x01808001: "Open hai lần",
    0x01808007: "không tạo được socket - cổng đang bị chương trình khác dùng",
    0x01808008: "không kết nối được cổng tới PLC",
    0x01808009: "lỗi cổng COM tới PLC",
    0x01808404: "chưa Open",
    0x0180840B: "hết thời gian chờ PLC trả lời - kiểm tra cáp / nguồn PLC",
    0x01808502: "không kết nối được driver USB của PLC",
    0x01808505: "USB tới PLC hết thời gian chờ",
}
# Lỗi do cách gọi (không phải do đường truyền): không coi là mất kết nối.
_CALL_SHAPE_HRESULTS = (0x80020005, 0x8002000E, 0x80020004, 0x80020003, 0x80020006)


def describe(rc):
    rc &= 0xFFFFFFFF
    text = ERRORS.get(rc)
    return "0x%08X%s" % (rc, " (%s)" % text if text else "")


class MxError(RuntimeError):
    def __init__(self, what, rc):
        super().__init__("%s lỗi %s" % (what, describe(rc)))
        self.rc = rc & 0xFFFFFFFF


def _rc(result):
    """Giá trị trả về của hàm MX. pywin32 trả (mã, dữ liệu) với hàm có tham số ra."""
    if isinstance(result, tuple):
        return int(result[0]), (result[1] if len(result) > 1 else None)
    return int(result), None


class MxPlc:
    name = "PLC"

    def __init__(self, cfg):
        self.cfg = cfg
        self._want = "off"
        self._sent = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._ok = False
        self._via = ""
        self._error = "chưa kết nối" if cfg.get("enabled", True) else "không dùng"
        self._keepalive = float(cfg.get("keepalive_s", 5) or 0)

    def start(self):
        if not self.cfg.get("enabled", True):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="plc", daemon=True)
        self._thread.start()

    def stop(self):
        self._want = "off"
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def connected(self):
        return self._ok

    def set_light(self, color):
        """color: red | green | yellow | off. Không chặn."""
        if color != self._want:
            self._want = color
            self._wake.set()

    # ---- các bước gọi MX Component (chỉ chạy trong luồng "plc") ----------------
    def _create(self):
        """Tạo control. Trả (đối tượng, tên) hoặc ném lỗi nếu máy chưa cài MX Component."""
        import pythoncom
        import win32com.client
        if self.cfg.get("progid"):
            return win32com.client.Dispatch(self.cfg["progid"]), self.cfg["progid"]
        errors = []
        try:
            return (win32com.client.Dispatch(CLSID_ACTUTLTYPE64,
                                             clsctx=pythoncom.CLSCTX_LOCAL_SERVER),
                    "ActUtlType64 (MX Component 5)")
        except Exception as e:
            errors.append("ActUtlType64: %s" % e)
        try:
            return win32com.client.Dispatch(PROGID_ACTUTLTYPE32), "ActUtlType (32-bit)"
        except Exception as e:
            errors.append("ActUtlType: %s" % e)
        raise RuntimeError("chưa cài MX Component (%s)" % "; ".join(errors))

    def _open(self):
        plc, via = self._create()
        plc.ActLogicalStationNumber = int(self.cfg.get("station_number", 0))
        if self.cfg.get("password"):
            plc.ActPassword = str(self.cfg["password"])
        rc, _ = _rc(plc.Open())
        if rc & 0xFFFFFFFF in ALREADY_OPEN:
            log.warning("PLC: Open báo %s - Close rồi Open lại", describe(rc))
            plc.Close()
            rc, _ = _rc(plc.Open())
        if rc != 0:
            raise MxError("Open", rc)
        if self._keepalive:
            # Open thành công chưa chắc PLC trả lời: đọc thử ngay để chỉ báo không nhấp nháy.
            try:
                self._probe(plc)
            except Exception:
                try:
                    plc.Close()
                except Exception:
                    pass
                raise
        return plc, via

    def _set(self, plc, dev, on):
        rc, _ = _rc(plc.SetDevice(dev, 1 if on else 0))
        if rc != 0:
            raise MxError("SetDevice " + dev, rc)

    def _write(self, plc, color):
        if color not in COLORS:
            self._set(plc, "M10", True)
            return
        idx = COLORS[color]
        for dev, val in (("M10", False), ("M0", idx == 0), ("M1", idx == 1), ("M2", idx == 2)):
            self._set(plc, dev, val)

    def _probe(self, plc):
        """Đọc thử M10 để biết đường truyền còn sống (rút cáp PLC thì chỉ báo PLC phải đỏ)."""
        try:
            rc, _ = _rc(plc.GetDevice("M10", 0))
        except Exception as e:
            hr = getattr(e, "hresult", None)
            if hr is not None and hr & 0xFFFFFFFF in _CALL_SHAPE_HRESULTS:
                self._keepalive = 0
                log.warning("PLC: không gọi được GetDevice kiểu này (%s) - tắt dò kết nối định kỳ, "
                            "đèn tháp vẫn hoạt động", e)
                return
            raise
        if rc != 0:
            raise MxError("GetDevice M10", rc)

    def _run(self):
        import pythoncom
        pythoncom.CoInitialize()                 # STA, theo mục 11.1 của sổ tay
        plc, backoff, last_probe = None, 3, 0.0
        try:
            while not self._stop.is_set():
                if plc is None:
                    try:
                        plc, self._via = self._open()
                        self._ok, self._error, self._sent, backoff = True, "", None, 3
                        last_probe = time.time()
                        log.info("Kết nối PLC OK: %s, Logical Station %s", self._via,
                                 self.cfg.get("station_number", 0))
                    except Exception as e:
                        plc, self._ok, self._error = None, False, str(e)
                        log.warning("PLC: %s - thử lại sau %d s", e, backoff)
                        self._stop.wait(backoff)
                        backoff = min(backoff * 2, 60)
                        continue
                try:
                    want = self._want
                    if want != self._sent:
                        self._write(plc, want)
                        self._sent = want
                        last_probe = time.time()
                        log.info("Đèn tháp -> %s", want)
                    elif self._keepalive and time.time() - last_probe >= self._keepalive:
                        self._probe(plc)
                        last_probe = time.time()
                except Exception as e:
                    self._ok, self._error = False, str(e)
                    log.warning("PLC: %s - kết nối lại", e)
                    try:
                        plc.Close()
                    except Exception:
                        pass
                    plc = None
                    continue
                self._wake.wait(1.0)
                self._wake.clear()
        finally:
            if plc is not None:
                try:
                    self._write(plc, "off")
                except Exception:
                    pass
                try:
                    plc.Close()
                    log.info("Đã đóng kết nối PLC")
                except Exception as e:
                    log.warning("Lỗi đóng PLC: %s", e)
            self._ok = False
            pythoncom.CoUninitialize()

    def status(self):
        return {"ok": self._ok, "detail": self._error or self._via or "MX Component"}
