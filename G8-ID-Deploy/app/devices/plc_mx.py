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
ActUtlType64 không có IDispatch (win32com.client.Dispatch báo E_NOINTERFACE - đã gặp ở trạm),
chỉ có interface vtable IActUtlType64 khai báo trong thư viện kiểu nhúng ở ActUtlType64.exe
-> gọi qua comtypes. Với comtypes, tham số [out] thành giá trị trả về: GetDevice(dev) trả
(lData, mã lỗi), các hàm khác trả thẳng mã lỗi.

Đèn tháp (CPLC.SetTrafficLightByM): M0 = đỏ, M1 = xanh, M2 = vàng, M10 = tắt.
Nút vật lý (TForm.timerPLCButtonScan_Tick, bản 2.4.1): M20 = START, M22 = STOP, M21 = ĐỊNH DANH,
đọc mỗi 200 ms trong luồng "plc", kích ở sườn lên rồi gọi on_button(tên nút). PLC tự bật / tắt
bit theo nút; phần mềm chỉ đọc, không ghi trả.
"""
import logging
import threading
import time

from . import PLC_BUTTONS, ButtonEdges

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
# Mã lỗi khi cáp CH340 treo / driver kẹt (ST01 28/10: GetDevice 0x01808201 rồi Open 0x0180800C mãi)
# -> tắt / bật lại cáp (ch340.py). 0x0180840B (PLC không trả lời) không thuộc nhóm này: cổng USB vẫn tốt.
CH340_STUCK = (0x0180800C, 0x01808009, 0x01808201)
CH340_GAP_S, CH340_GAP_MAX_S = 30, 600
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


def _mx5_server_path():
    """Đường dẫn ActUtlType64.exe (chứa thư viện kiểu). Bộ cài MX5 ghi CLSID ở nhánh 32-bit."""
    import winreg
    key = r"CLSID\%s\LocalServer32" % CLSID_ACTUTLTYPE64
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key, 0, winreg.KEY_READ | view) as k:
                cmd = winreg.QueryValueEx(k, "")[0].strip()
        except OSError:
            continue
        return cmd[1:].split('"', 1)[0] if cmd.startswith('"') else cmd.split(" /", 1)[0]
    return None


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
        self._ct = False                        # control tạo bằng comtypes (không phải pywin32)
        self._error = "chưa kết nối" if cfg.get("enabled", True) else "không dùng"
        self._keepalive = float(cfg.get("keepalive_s", 5) or 0)
        self.on_button = None                    # engine gán: on_button("start" | "stop" | "identify")
        self._buttons = {k: str(v).strip() for k, v in (cfg.get("buttons", PLC_BUTTONS) or {}).items()
                         if str(v or "").strip()}
        self._poll = max(0.05, float(cfg.get("button_poll_ms", 200) or 200) / 1000.0)
        self._edges = ButtonEdges()
        # Tắt / bật lại CH340 khi khởi động và khi gặp lỗi CH340_STUCK (cách nhau ít nhất _reset_gap,
        # tăng gấp đôi khi bật lại xong vẫn lỗi, về CH340_GAP_S khi nối được).
        self._reset_on_start = bool(cfg.get("ch340_restart_on_start", False))
        self._reset_on_error = bool(cfg.get("ch340_restart_on_error", False))
        self._reset_gap, self._last_reset = CH340_GAP_S, 0.0

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
        """Tạo control. Trả (đối tượng, tên) hoặc ném lỗi kèm lý do từng cách đã thử."""
        import win32com.client
        self._ct = False
        if self.cfg.get("progid"):
            return win32com.client.Dispatch(self.cfg["progid"]), self.cfg["progid"]
        errors = []
        try:
            import comtypes
            import comtypes.client
            exe = _mx5_server_path()
            if not exe:
                raise RuntimeError("không thấy trong registry")
            mod = comtypes.client.GetModule(exe)
            plc = comtypes.client.CreateObject(comtypes.GUID(CLSID_ACTUTLTYPE64),
                                               clsctx=comtypes.CLSCTX_LOCAL_SERVER,
                                               interface=mod.IActUtlType64)
            self._ct = True
            return plc, "ActUtlType64 (MX Component 5)"
        except Exception as e:
            errors.append("ActUtlType64: %s" % e)
        try:
            return win32com.client.Dispatch(PROGID_ACTUTLTYPE32), "ActUtlType (32-bit)"
        except Exception as e:
            errors.append("ActUtlType: %s" % e)
        raise RuntimeError("không tạo được control MX Component (%s)" % "; ".join(errors))

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

    def _get(self, plc, dev):
        """GetDevice một bit, trả 0/1. comtypes trả (lData, mã lỗi); pywin32 trả (mã lỗi, lData)."""
        if self._ct:
            res = plc.GetDevice(dev)
            val, rc = (res[0], res[-1]) if isinstance(res, (tuple, list)) else (0, res)
        else:
            rc, val = _rc(plc.GetDevice(dev, 0))
        if int(rc) != 0:
            raise MxError("GetDevice " + dev, int(rc))
        return int(val or 0) & 1

    @staticmethod
    def _call_shape(e):
        hr = getattr(e, "hresult", None)
        return isinstance(e, TypeError) or (hr is not None and hr & 0xFFFFFFFF in _CALL_SHAPE_HRESULTS)

    def _probe(self, plc):
        """Đọc thử M10 để biết đường truyền còn sống (rút cáp PLC thì chỉ báo PLC phải đỏ)."""
        try:
            self._get(plc, "M10")
        except MxError:
            raise
        except Exception as e:
            if self._call_shape(e):
                self._keepalive = 0
                log.warning("PLC: không gọi được GetDevice kiểu này (%s) - tắt dò kết nối định kỳ, "
                            "đèn tháp vẫn hoạt động", e)
                return
            raise

    def _scan(self, plc):
        """Đọc các bit nút, nút vừa nhấn (sườn lên) -> on_button. Đọc được cũng là dò kết nối."""
        try:
            levels = {name: self._get(plc, dev) == 1 for name, dev in self._buttons.items()}
        except MxError:
            raise
        except Exception as e:
            if self._call_shape(e):
                self._buttons = {}
                log.warning("PLC: không gọi được GetDevice kiểu này (%s) - tắt đọc nút vật lý, "
                            "đèn tháp vẫn hoạt động", e)
                return
            raise
        for name in self._edges.feed(levels):
            log.info("Nhấn nút %s từ PLC (%s)", name.upper(), self._buttons[name])
            cb = self.on_button
            if cb is not None:
                try:
                    cb(name)
                except Exception:
                    log.exception("Lỗi xử lý nút %s từ PLC", name)

    def _want_reset(self, e):
        rc = getattr(e, "rc", None)
        return (self._reset_on_error and rc in CH340_STUCK and not self._stop.is_set()
                and time.time() - self._last_reset >= self._reset_gap)

    def _restart_ch340(self, why):
        """Tắt / bật lại cáp CH340 của PLC. Chạy trong luồng "plc" khi chưa Open (hoặc đã Close)."""
        from . import ch340
        if self._last_reset:                     # lần trước bật lại xong vẫn lỗi -> giãn ra
            self._reset_gap = min(self._reset_gap * 2, CH340_GAP_MAX_S)
        self._last_reset = time.time()
        port = self.cfg.get("com_port") or ""
        self._ok, self._error = False, "đang tắt / bật lại cáp CH340 %s (%s)" % (port, why)
        log.warning("PLC: tắt / bật lại cáp CH340 %s - %s", port, why)
        ok, msg = ch340.restart(port)
        if ok:
            log.info("PLC: đã tắt / bật lại %s", msg)
            self._stop.wait(3)                   # chờ Windows mở lại cổng
        else:
            log.warning("PLC: không tắt / bật lại được CH340: %s", msg)
            if not ch340.is_admin():             # không có quyền thì lần sau cũng vậy: thôi thử
                self._reset_on_start = self._reset_on_error = False
        return ok

    def _run(self):
        import pythoncom
        pythoncom.CoInitialize()                 # STA, theo mục 11.1 của sổ tay
        plc, backoff, last_probe, last_scan = None, 3, 0.0, 0.0
        if self._reset_on_start:
            self._restart_ch340("khởi động phần mềm")
            self._last_reset = 0.0               # lỗi đầu tiên sau khởi động vẫn được bật lại ngay
        try:
            while not self._stop.is_set():
                if plc is None:
                    try:
                        plc, self._via = self._open()
                        self._ok, self._error, self._sent, backoff = True, "", None, 3
                        self._reset_gap, self._last_reset = CH340_GAP_S, 0.0
                        last_probe = time.time()
                        self._edges.reset()          # nối lại: lần đọc đầu chỉ ghi nhận mức nút
                        log.info("Kết nối PLC OK: %s, Logical Station %s%s", self._via,
                                 self.cfg.get("station_number", 0),
                                 ", nút " + ", ".join("%s=%s" % (k.upper(), v)
                                                      for k, v in self._buttons.items())
                                 if self._buttons else "")
                    except Exception as e:
                        plc, self._ok, self._error = None, False, str(e)
                        if self._want_reset(e):
                            log.warning("PLC: %s", e)
                            self._restart_ch340(describe(e.rc))
                            continue
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
                    elif (self._keepalive and not self._buttons
                          and time.time() - last_probe >= self._keepalive):
                        self._probe(plc)
                        last_probe = time.time()
                    if self._buttons and time.time() - last_scan >= self._poll:
                        self._scan(plc)
                        last_scan = time.time()
                except Exception as e:
                    self._ok, self._error = False, str(e)
                    log.warning("PLC: %s - kết nối lại", e)
                    try:
                        plc.Close()
                    except Exception:
                        pass
                    plc = None
                    if self._want_reset(e):
                        self._restart_ch340(describe(e.rc))
                    continue
                self._wake.wait(self._poll if self._buttons else 1.0)
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
            plc = None                           # nhả con trỏ COM trước khi CoUninitialize
            self._ok = False
            pythoncom.CoUninitialize()

    def status(self):
        return {"ok": self._ok, "detail": self._error or self._via or "MX Component"}
