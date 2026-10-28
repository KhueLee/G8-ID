"""Bộ kiểm tra tự động (run_tests.bat). Không đụng tới dữ liệu / cổng của trạm đang chạy:
dùng thư mục tạm, cổng riêng (186xx, 277xx) và mongod riêng.

  1. Kiểm tra đơn vị: phân tích bản tin cân, tách mã thùng.
  2. Kiểm tra đầu-cuối: bật phần mềm ở MANUAL + công cụ mô phỏng, chạy lệnh thật qua HTTP,
     thử các tình huống lỗi, khoá liên động AUTO/mô phỏng, mất điện giữa lệnh, thoát sạch.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

UI, ORD, SIM, MONGO = 18600, 18500, 18700, 27718
APP = "http://127.0.0.1:%d" % UI
ORDER = "http://127.0.0.1:%d" % ORD
SIMU = "http://127.0.0.1:%d" % SIM
PASS = "1234"
results = []


def http(url, body=None, method=None, timeout=20, raw=None):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(url, data=data, method=method or ("GET" if data is None else "POST"),
                                 headers={"Content-Type": "application/json", "X-Pass": PASS})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def state():
    return http(APP + "/api/state")[1]


def wait(cond, timeout=30, what=""):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            v = cond()
            if v:
                return v
        except (OSError, ValueError):
            pass
        time.sleep(0.15)
    raise AssertionError("Hết %ss chờ: %s | message=%r" % (timeout, what, _msg()))


def _msg():
    try:
        return state().get("message")
    except Exception:
        return None


def check(name, fn):
    t0 = time.time()
    try:
        fn()
        results.append((name, True, ""))
        print("  [ĐẠT]  %-62s %5.1fs" % (name, time.time() - t0))
    except Exception as e:
        results.append((name, False, str(e)))
        print("  [LỖI]  %-62s %5.1fs\n         %s" % (name, time.time() - t0, e))
        if not isinstance(e, AssertionError):
            traceback.print_exc()


# ---------------------------------------------------------------- kiểm tra đơn vị
def unit_tests():
    from app.devices.scale import parse_weight
    from app.devices.printer_godex import (CHAR_W, CODE_H, CODE_W, LEFT_W, NAME_BOX, QR_BOX,
                                          code_size, name_lines, qr_mul, text_em, wrap_name)
    from app.engine import field, fmt_date, order_code, parse_carton, spec_text, std_weight_g

    def t_scale():
        cases = {"ST,GS,+  1.234kg": 1234, "  300 g": 300, "US,NT,+0000.50 kg": 500, "0": 0,
                 "abc": None, "": None, "ST,GS,    305g": 305, "1000.4": 1000}
        for line, want in cases.items():
            assert parse_weight(line) == want, "%r -> %r (mong %r)" % (line, parse_weight(line), want)

    def t_carton():
        assert parse_carton("a|b|c|d|e|f|g|h|i|TP0231|k") == ("TP0231", "a|b|c|d|e|f|g|h|i|TP0231|k")
        assert parse_carton("  TP0001 ") == ("TP0001", "TP0001")
        assert parse_carton("a|b|c") == ("a|b|c", "a|b|c")

    def t_field():
        assert field({"PO_ID": 5}, "po_id") == 5
        assert field({"palletID": "P1"}, "Pallet_ID", "palletID") == "P1"
        assert field({}, "x", default=7) == 7

    def t_wcs_fields():
        assert std_weight_g({"GW": 1.637, "NW": 0.0}, {}) == 1637            # GW kg/thùng -> gam
        assert std_weight_g({"GW": "0.5"}, {}) == 500
        assert std_weight_g({"Weight_ref": 300, "GW": 1.637}, {}) == 300     # Weight_ref (gam) trước
        assert std_weight_g({}, {"Weight_ref": 250}) == 250                  # mặc định cấp lệnh
        assert std_weight_g({"GW": 0}, {}) == 0 and std_weight_g({"GW": "x"}, {}) == 0
        assert order_code({"po_name": "VAS-091026-3", "po_id": 190146369}) == "VAS-091026-3"
        assert order_code({"po_id": 190146369}) == "190146369" and order_code(None) == ""
        assert spec_text({"inner_carton": 6}) == "6 chiếc"
        assert spec_text({"ctn": 32, "qty": 192}) == "6 chiếc" and spec_text({}) == ""

    def t_mfg_fmt():
        assert fmt_date("2026-09-18") == "18/09/2026"
        assert fmt_date("2026-09-18T00:00:00") == "18/09/2026"
        assert fmt_date("18/09/2026") == "18/09/2026" and fmt_date(None) == ""

    def t_label_name():
        name = "Bóng Led trụ nhôm T60,model T60-140/G01 (6c/T hoặc 24c/T)"
        h, lines = wrap_name(name)
        assert h >= 24 and len(lines) == 3 and " ".join(lines) == name, (h, lines)
        assert all(len(x) * h * CHAR_W <= LEFT_W for x in lines), (h, lines)
        assert len(lines) * (h + 3) <= NAME_BOX + 3, (h, lines)
        assert name_lines(32) == 2 and name_lines(24) == 3
        assert wrap_name("SP ngắn") == (32, ["SP ngắn"])
        h, lines = wrap_name("X" * 200)
        assert len(lines) == 3 and lines[2].endswith("…"), lines
        assert wrap_name("") == (32, [])

    def t_label_code():
        full = "TRU_V01_10W_AT|||||||48|0|G8HOME14842246343127001||001||||||||01"
        h = code_size(full)
        assert 14 <= h < CODE_H and text_em(full) * h <= CODE_W, h   # vừa 1 dòng, ~2 mm
        assert text_em(full) >= 32.57                                 # không hẹp hơn Arial đậm thật
        assert code_size("G8HOME14842246343127001") == CODE_H         # mã ngắn: chữ to như cũ
        assert qr_mul("G8HOME14842246343127001") == 9                 # mã ngắn: QR như cũ
        assert qr_mul(full) == 7 and 33 * 7 <= QR_BOX                 # QR nguyên phần tử: 33 ô
        assert parse_carton(full)[0] == "G8HOME14842246343127001"     # đọc QR -> tách mã định danh

    check("Phân tích bản tin cân (g / kg / rác)", t_scale)
    check("Ngày sản xuất từ lệnh đổi về dd/mm/yyyy", t_mfg_fmt)
    check("Lệnh WCS: GW (kg) -> khối lượng chuẩn (g), mã lệnh PO_Name, quy cách", t_wcs_fields)
    check("Tem: tên sản phẩm chữ to, chia tối đa 3 dòng", t_label_name)
    check("Tem: QR + dòng cuối là nguyên phần tử Carton_List, vừa khung", t_label_code)
    check("Tách mã thùng từ Carton_List", t_carton)
    check("Đọc trường không phân biệt hoa thường", t_field)
    check("Driver cân RS232: đọc luồng, mất tín hiệu giữ cổng, đọc lỗi mở lại, đóng sạch", t_serial_scale)
    check("Driver đầu đọc RS232: kích 16 54 0D / tắt 16 55 0D, hết giờ, Dừng", t_serial_barcode)
    check("Driver máy in: nạp được EZio DLL của bản cũ", t_printer_dll)
    check("Driver PLC MX Component (control giả): Open, đèn, nút M20/M22/M21, mất nối, Close", t_plc_mx)
    check("Cổng COM: None không mở cổng, chặn hai thiết bị trùng cổng", t_com_none_conflict)
    check("Kiểm tra thiết bị ở thẻ Cài đặt: nhận ra cân / đầu đọc / sai cổng", t_probe)
    check("Tự dò cổng COM theo tên Windows (trạm ST02), thiếu / trùng -> None", t_portmap)
    check("Chẩn đoán PLC (kiem_tra_plc): phân loại lỗi cổng, chạy bền MX, kết luận CH340 kẹt", t_plc_diag)
    check("PLC tự tắt / bật lại CH340: khi khởi động, khi Open 0x0180800C / rớt 0x01808201", t_plc_ch340)


class FakeSerial:
    """Cổng COM giả để thử driver RS232 thật mà không cần thiết bị."""
    opened = 0

    def __init__(self, feed=None):
        FakeSerial.opened += 1
        self.feed = list(feed or [])
        self.written = []
        self.closed = False
        self.reply = b""

    def read(self, n):
        time.sleep(0.02)
        if self.closed:
            raise OSError("port closed")
        return self.feed.pop(0) if self.feed else b""

    def write(self, data):
        self.written.append(bytes(data))
        if data == b"\x16T\r" and self.reply:
            self.feed.append(self.reply)

    def reset_input_buffer(self):
        self.feed.clear()

    def close(self):
        self.closed = True


def t_serial_scale():
    from app.devices import scale
    real = scale.open_serial
    ports = []

    def fake_open(cfg, timeout):
        # Bản tin bị cắt ngang giữa hai lần đọc, lẫn dòng không có số.
        p = FakeSerial([b"ST,GS,+  0.3", b"00kg\r\nUS,GS,\r\n", b"ST,GS,+  0.305kg\r\n"])
        ports.append(p)
        return p

    scale.open_serial = fake_open
    try:
        s = scale.SerialScale({"port": "COMX", "baudrate": 9600, "stale_s": 0.4})
        s.start()
        wait(lambda: s.read() == 305, 3, "đọc được 305 g")
        wait(lambda: s.read() is None, 3, "hết dữ liệu -> báo mất cân, không dùng số cũ")
        time.sleep(1.5)
        assert len(ports) == 1 and not ports[0].closed, "cân im lặng: giữ cổng, không đóng/mở lại"
        ports[0].feed.append(b"ST,GS,+  0.310kg\r\n")
        wait(lambda: s.read() == 310, 3, "có lại dữ liệu trên cổng cũ")
        ports[0].closed = True                          # đọc lỗi (rút cáp) -> vẫn phải mở lại
        wait(lambda: len(ports) == 2, 5, "đọc cổng lỗi thì đóng rồi mở lại")
        wait(lambda: s.read() == 305, 3, "có lại dữ liệu sau khi mở lại")
        t0 = time.time()
        s.stop()
        assert time.time() - t0 < 2 and ports[-1].closed, "đóng cổng phải nhanh và sạch"
    finally:
        scale.open_serial = real


def t_serial_barcode():
    import threading
    from app.devices import barcode
    real = barcode.open_serial
    port = FakeSerial()
    barcode.open_serial = lambda cfg, timeout: port
    try:
        b = barcode.SerialBarcode({"port": "COMX", "baudrate": 9600})
        b.start()
        wait(lambda: b.connected, 3, "mở cổng đầu đọc")
        port.reply = b"TP0231\r\n"
        assert b.read(1000) == "TP0231"
        assert port.written[-2:] == [b"\x16T\r", b"\x16U\r"], port.written
        port.reply = b""
        t0 = time.time()
        assert b.read(400) == "" and 0.3 < time.time() - t0 < 1.5, "hết giờ phải trả rỗng"
        abort = threading.Event()
        threading.Timer(0.2, abort.set).start()
        t0 = time.time()
        assert b.read(10000, abort) == "" and time.time() - t0 < 1.0, "Dừng phải ngắt việc đọc ngay"
        b.stop()
        assert port.closed and port.written[-1] == b"\x16U\r"
    finally:
        barcode.open_serial = real


def t_com_none_conflict():
    from app import config
    from app.devices import barcode, scale
    opened = []
    real = scale.open_serial, barcode.open_serial
    scale.open_serial = barcode.open_serial = lambda cfg, timeout: opened.append(cfg) or FakeSerial()
    try:
        devs = [scale.SerialScale({"port": "", "baudrate": 9600}), barcode.SerialBarcode({"port": "", "baudrate": 9600})]
        for d in devs:
            d.start()
        time.sleep(0.3)
        for d in devs:
            assert not d.connected and "None" in d.status()["detail"], d.status()
            d.stop()
        assert not opened, "cổng None không được mở"
    finally:
        scale.open_serial, barcode.open_serial = real
    devices = {"scale": {"port": "COM4"}, "barcode": {"port": "com4"},
               "printer": {"connect_type": "USB", "com_port": "COM4"},
               "plc": {"enabled": False, "com_port": "COM4"}}
    assert "Cân và Đầu đọc" in config.com_conflict(devices), config.com_conflict(devices)
    devices["barcode"]["port"] = "COM3"
    assert config.com_conflict(devices) == "", "máy in USB / PLC tắt không chiếm cổng"
    devices["printer"]["connect_type"] = "COM"
    assert "Máy in" in config.com_conflict(devices)
    devices["printer"]["com_port"] = ""
    devices["scale"]["port"] = devices["barcode"]["port"] = ""
    assert config.com_conflict(devices) == "", "nhiều thiết bị None không tính là trùng"


def t_portmap():
    import copy
    from app import config
    from app.devices import portmap
    st02 = [{"port": "COM1", "desc": "Communications Port (COM1)"},
            {"port": "COM3", "desc": "USB Serial Device (COM3)"},
            {"port": "COM4", "desc": "USB-SERIAL CH340 (COM4)"},
            {"port": "COM5", "desc": "USB Serial Port (COM5)"}]
    dev = copy.deepcopy(config.DEFAULTS["devices"])
    got = portmap.detect(dev, st02)
    assert got == {"scale": ("COM5", ""), "barcode": ("COM3", ""), "plc": ("COM4", "")}, got
    dev["scale"].update(auto=False, port="COM1")           # máy đặc biệt: cân chọn tay COM1
    got = portmap.detect(dev, st02)
    assert "scale" not in got and got["barcode"] == ("COM3", ""), got
    dev["barcode"].update(auto=False, port="COM5")         # chọn tay chiếm cổng của mẫu khác
    dev["scale"].update(auto=True)
    got = portmap.detect(dev, st02)
    assert got["scale"][0] == "" and "không thấy" in got["scale"][1], got
    two = st02 + [{"port": "COM7", "desc": "USB Serial Port (COM7)"}]
    dev["barcode"].update(auto=True)
    got = portmap.detect(dev, two)
    assert got["scale"][0] == "" and "COM5, COM7" in got["scale"][1], got
    dev["plc"]["enabled"] = False
    assert "plc" not in portmap.detect(dev, st02), "PLC tắt thì không dò"


def t_plc_diag():
    """tools/plc_diag.py với control MX giả và cổng thô giả: không cần cáp / MX Component."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import argparse
    import plc_diag as d
    from app.devices import plc_mx
    c = d.classify_serial_error
    assert c(Exception("could not open port 'COM9': PermissionError(13, 'Access is denied.', None, 5)"))[0] == "busy"
    assert c(Exception("could not open port 'COM9': FileNotFoundError(2, 'The system cannot find "
                       "the file specified.', None, 2)"))[0] == "missing"
    assert c(Exception("Cannot configure port, something went wrong. Original message: OSError(22, "
                       "'A device attached to the system is not functioning.', None, 31)"))[0] == "dcb"
    assert d.summarize_raw({9600: ("ok", ""), 115200: ("dcb", "")}) == "dcb"

    class FakeMx:
        reads = 0
        fail_after = 10**9

        def Open(self):
            return 0

        def Close(self):
            return 0

        def GetDevice(self, dev):
            FakeMx.reads += 1
            return (0, 0x01808201) if FakeMx.reads > FakeMx.fail_after else (0, 0)

    def create(self):
        self._ct = True
        return FakeMx(), "control giả"

    real_create, real_raw = plc_mx.MxPlc._create, d.raw_test
    plc_mx.MxPlc._create = create
    try:
        cfg = {"enabled": True, "station_number": 0}
        btn = {"start": "M20", "stop": "M22"}
        box = d.MxSession(cfg).run(1, 0.05, btn)
        assert "error" not in box and box["soak_ok_s"] == 1 and box["reads"] > 4, box
        FakeMx.reads, FakeMx.fail_after = 0, 7                 # chạy được một lúc rồi lỗi gửi
        box = d.MxSession(cfg).run(5, 0.05, btn)
        assert box["stage"] == "soak" and box["rc"] == 0x01808201 and "after_s" in box, box
        d.raw_test = lambda port, bauds=d.BAUDS: {9600: ("dcb", "kẹt")}
        d.findings.clear()
        args = argparse.Namespace(khong_reset=True)
        d.diagnose_mx_failure(box, "COM12", "", None, False, args, cfg)
        assert len(d.findings) == 1 and "CH340 KẸT" in d.findings[0][1], d.findings
        d.raw_test = lambda port, bauds=d.BAUDS: {9600: ("ok", "")}   # cổng tốt, MX báo không mở được
        d.findings.clear()
        d.diagnose_mx_failure({"stage": "open", "rc": 0x01808009, "describe": ""}, "COM12", "", None,
                              False, args, cfg)
        assert "trỏ sai cổng" in d.findings[0][1] and "COM12" in d.findings[0][2], d.findings
        # Access denied mà handle64 không thấy ai giữ (trạm ST01, 28/10): driver CH340 kẹt, không phải bị giành.
        real_owner = d.find_owner
        d.find_owner = lambda kernel: ("handle", [], "No matching handles found.")
        d.raw_test = lambda port, bauds=d.BAUDS: {9600: ("busy", "")}
        d.findings.clear()
        d.diagnose_mx_failure(box, "COM12", "\\Device\\Serial2", None, False, args, cfg)
        d.find_owner = real_owner
        assert len(d.findings) == 1 and "CH340 KẸT" in d.findings[0][1] and "không tiến trình" in d.findings[0][1], \
            d.findings
    finally:
        plc_mx.MxPlc._create, d.raw_test = real_create, real_raw

    # Cổng của Logical Station: Communication Settings Utility ghi ...\LogicalStNo_NNNN\<kiểu nối>\PortNumber.
    import winreg
    base = r"Software\MITSUBISHI\SWnD5-ACT\COMMUTL\LogicalStNo_0099"
    made = []                                       # khoá cha tự tạo -> xoá lại khi xong
    for part in (r"Software\MITSUBISHI", r"Software\MITSUBISHI\SWnD5-ACT",
                 r"Software\MITSUBISHI\SWnD5-ACT\COMMUTL"):
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, part))
        except OSError:
            made.append(part)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\STECMOPEN") as k:
        winreg.SetValueEx(k, "PortNumber", 0, winreg.REG_DWORD, 12)
    try:
        num, key = d.mx_station_port(99)
        assert num == 12 and key.endswith(r"LogicalStNo_0099\STECMOPEN"), (num, key)
        assert d.mx_station_port(98) == (None, "")
    finally:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base + r"\STECMOPEN")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base)
        for part in reversed(made):
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, part)


def t_plc_ch340():
    """Driver PLC với control giả + ch340.restart giả: không đụng cáp thật."""
    from app.devices import ch340, plc_mx
    resets, state = [], {"open": [0x0180800C, 0], "get_fail": False}

    class FakeAct:
        def Open(self):
            return state["open"].pop(0) if state["open"] else 0

        def Close(self):
            return 0

        def SetDevice(self, dev, value):
            return 0

        def GetDevice(self, dev):
            return (0, 0x01808201) if state["get_fail"] else (0, 0)

    def create(self):
        self._ct = True
        return FakeAct(), "control giả"

    real = (plc_mx.MxPlc._create, ch340.restart, ch340.is_admin)
    plc_mx.MxPlc._create = create
    ch340.restart = lambda port: (resets.append(port) or True, "USB-SERIAL CH340 (%s)" % port)
    ch340.is_admin = lambda: True
    p = plc_mx.MxPlc({"enabled": True, "station_number": 0, "com_port": "COM12",
                      "buttons": {"start": "M20"}, "button_poll_ms": 50,
                      "ch340_restart_on_start": True, "ch340_restart_on_error": True})
    p._stop.wait = lambda s=None: time.sleep(min(s or 0, 0.05))     # bỏ chờ 3 s sau khi bật lại
    try:
        p.start()
        # Khởi động: bật lại 1 lần; Open 0x0180800C -> bật lại ngay rồi Open OK.
        wait(lambda: p.connected, 5, "PLC nối sau khi bật lại CH340")
        assert resets == ["COM12", "COM12"], resets
        # Chạy được rồi rớt 0x01808201: lần nối trước đã OK nên bật lại ngay, không chờ khoảng cách.
        state["get_fail"], state["open"] = True, []
        wait(lambda: len(resets) == 3, 5, "rớt 0x01808201 -> bật lại CH340")
        state["get_fail"] = False
        wait(lambda: p.connected, 5, "nối lại sau khi bật lại")
        # Bật lại xong vẫn lỗi -> lần sau phải cách CH340_GAP_S (30 s), không bật liên tục.
        state["open"] = [0x0180800C] * 50
        state["get_fail"] = True
        wait(lambda: len(resets) == 4, 5, "rớt lần nữa -> bật lại")
        time.sleep(0.5)
        assert len(resets) == 4, "bật lại xong vẫn lỗi thì phải giãn ra: %s" % resets
        # 0x0180840B (PLC không trả lời) không phải lỗi CH340.
        assert 0x0180840B not in plc_mx.CH340_STUCK
    finally:
        p.stop()
        plc_mx.MxPlc._create, ch340.restart, ch340.is_admin = real
    assert ch340.pick([{"com": "COM12"}, {"com": "COM4"}], "") is None, "nhiều cáp mà không biết cổng: không đoán"
    assert ch340.pick([{"com": "COM12"}], "")["com"] == "COM12"
    assert ch340.pick([{"com": "COM12"}, {"com": "COM4"}], "com4")["com"] == "COM4"


def t_probe():
    from app.devices import barcode, probe
    real = probe.open_serial
    try:
        probe.open_serial = lambda cfg, timeout: FakeSerial([b"ST,GS,+  0.3", b"05kg\r\n"])
        ok, text = probe.scale({"port": "COM4", "baudrate": 9600})
        assert ok and "305 g" in text, text
        stream = FakeSerial([b"ST,GS,+  0.305kg" + bytes([13, 10])] * 100)
        stream.reset_input_buffer = lambda: None      # cân phát liên tục, xoá đệm vẫn có số mới
        probe.open_serial = lambda cfg, timeout: stream
        ok, text = probe.barcode({"port": "COM4", "baudrate": 9600})
        assert not ok and "giống cân" in text and not stream.written, (text, stream.written)
        port = FakeSerial()
        port.reply = b"TP0231\r\n"
        probe.open_serial = lambda cfg, timeout: port
        ok, text = probe.barcode({"port": "COM3", "baudrate": 9600})
        assert ok and "TP0231" in text and port.written == [barcode.TRIGGER_ON, barcode.TRIGGER_OFF], (text, port.written)
        probe.SCALE_LISTEN_S = 0.3
        probe.open_serial = lambda cfg, timeout: FakeSerial()
        ok, text = probe.scale({"port": "COM3", "baudrate": 9600})
        assert not ok and "không có dữ liệu" in text, text

        def boom(cfg, timeout):
            raise OSError("could not open port")
        probe.open_serial = boom
        ok, text = probe.scale({"port": "COM9", "baudrate": 9600})
        assert not ok and "COM9" in text, text
        ok, text = probe.barcode({"port": "", "baudrate": 9600})
        assert not ok and "None" in text, text
    finally:
        probe.open_serial, probe.SCALE_LISTEN_S = real, 3.0


def t_printer_dll():
    from app import config
    from app.devices.printer_godex import GodexPrinter
    config.load()
    p = GodexPrinter({"connect_type": "USB", "usb_name": ""})
    dll = p._load()
    for fn in ("OpenUSB", "FindFirstUSB", "sendcommand", "ecTextOutRW", "Bar_QRcode", "putimage",
               "closeport"):
        assert hasattr(dll, fn), "DLL thiếu hàm " + fn
    assert p.print_carton("X", "", "", "", "") is False, "chưa nối máy in thì in phải trả lỗi"


def t_plc_mx():
    """Chạy driver thật với một control giả có cùng giao diện ActUtlType64 (máy thử không có
    MX Component): kiểm tra trình tự gọi theo sổ tay, không kiểm tra được truyền thông thật."""
    from app.devices import plc_mx
    calls, made = [], []

    class FakeAct:
        opens = 0
        dead = False

        def __init__(self):
            self.ActLogicalStationNumber = None
            made.append(self)

        def Open(self):
            FakeAct.opens += 1
            calls.append("Open")
            return -268435453 if FakeAct.opens == 1 else 0     # 0xF0000003: đã Open

        def Close(self):
            calls.append("Close")
            return 0

        def SetDevice(self, dev, value):
            calls.append((dev, value))
            return 0

        def GetDevice(self, dev, value):
            return (0x0180840B, 0) if FakeAct.dead else (0, 1)

    real = plc_mx.MxPlc._create
    plc_mx.MxPlc._create = lambda self: (FakeAct(), "control giả")
    p = plc_mx.MxPlc({"enabled": True, "station_number": 3, "keepalive_s": 0.2})
    try:
        p.start()
        wait(lambda: p.connected, 3, "PLC nối")
        assert made[0].ActLogicalStationNumber == 3
        assert calls[:3] == ["Open", "Close", "Open"], "đã Open thì phải Close rồi Open lại: %s" % calls
        p.set_light("green")
        wait(lambda: ("M2", 0) in calls, 3, "ghi đèn xanh")
        assert calls[-4:] == [("M10", 0), ("M0", 0), ("M1", 1), ("M2", 0)], calls[-4:]
        FakeAct.dead = True
        wait(lambda: not p.connected, 3, "đọc thử lỗi -> báo mất kết nối")
        assert "0x0180840B" in p.status()["detail"] and "hết thời gian" in p.status()["detail"]
        FakeAct.dead = False
        wait(lambda: p.connected and calls[-1] == ("M2", 0) and calls.count(("M1", 1)) == 2, 8,
             "tự nối lại và bật lại đúng màu đèn")
        p.stop()
        assert calls[-2:] == [("M10", 1), "Close"], "thoát phải tắt đèn rồi Close: %s" % calls[-2:]
    finally:
        p.stop()
        plc_mx.MxPlc._create = real

    # Kiểu comtypes (ActUtlType64 thật): GetDevice(dev) trả (lData, mã lỗi).
    class FakeCt(FakeAct):
        def GetDevice(self, dev):
            return (0, 0x0180840B) if FakeAct.dead else (1, 0)

    def create_ct(self):
        self._ct = True
        return FakeCt(), "control giả comtypes"

    # Nút vật lý: M20 START / M22 STOP / M21 ĐỊNH DANH, kích ở sườn lên; bit đang 1 lúc nối không kích.
    class FakeBtn(FakeCt):
        bits = {"M20": 1, "M21": 0, "M22": 0}

        def GetDevice(self, dev):
            return (FakeBtn.bits.get(dev, 0), 0)

    def create_btn(self):
        self._ct = True
        return FakeBtn(), "control giả nút"

    pressed = []
    FakeAct.opens = 1
    plc_mx.MxPlc._create = create_btn
    p = plc_mx.MxPlc({"enabled": True, "station_number": 0, "keepalive_s": 5,
                      "buttons": {"start": "M20", "stop": "M22", "identify": "M21"},
                      "button_poll_ms": 50})
    p.on_button = pressed.append
    try:
        p.start()
        wait(lambda: p.connected, 3, "PLC nối (nút)")
        time.sleep(0.3)
        assert pressed == [], "M20 đang 1 lúc nối không được tự Bắt đầu: %s" % pressed
        FakeBtn.bits["M20"] = 0
        time.sleep(0.2)
        FakeBtn.bits["M20"] = 1
        wait(lambda: pressed == ["start"], 2, "nhấn START (M20)")
        time.sleep(0.3)
        assert pressed == ["start"], "giữ nút không được kích lặp: %s" % pressed
        FakeBtn.bits.update(M20=0, M22=1)
        wait(lambda: pressed == ["start", "stop"], 2, "nhấn STOP (M22)")
        FakeBtn.bits.update(M22=0, M21=1)
        wait(lambda: pressed == ["start", "stop", "identify"], 2, "nhấn ĐỊNH DANH (M21)")
    finally:
        p.stop()
        plc_mx.MxPlc._create = real
    p = plc_mx.MxPlc({"enabled": True, "buttons": {"start": "", "stop": "", "identify": ""}})
    assert p._buttons == {}, "bit để trống = không dùng nút"

    FakeAct.opens, FakeAct.dead = 1, False
    plc_mx.MxPlc._create = create_ct
    p = plc_mx.MxPlc({"enabled": True, "station_number": 0, "keepalive_s": 0.2})
    try:
        p.start()
        wait(lambda: p.connected, 3, "PLC nối (comtypes)")
        FakeAct.dead = True
        wait(lambda: not p.connected, 3, "comtypes: GetDevice lỗi -> báo mất kết nối")
        assert "0x0180840B" in p.status()["detail"], p.status()
    finally:
        p.stop()
        plc_mx.MxPlc._create = real


# ---------------------------------------------------------------- môi trường thử
class Env:
    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="g8id_test_")
        self.cfg = os.path.join(self.dir, "config.json")
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({
                "station_id": "TEST",
                "ui": {"host": "127.0.0.1", "port": UI, "password": PASS, "open_browser": False},
                "order_server": {"host": "127.0.0.1", "port": ORD},
                "mongo": {"uri": "mongodb://127.0.0.1:%d" % MONGO},
                "log": {"dir": os.path.join(self.dir, "logs")},
                "servers": {"timeout_s": 3, "retry_s": 2},
                # HYBRID mở thiết bị thật: không được tắt / bật cáp PLC của trạm đang chạy test.
                "devices": {"plc": {"ch340_restart_on_start": False, "ch340_restart_on_error": False}},
                "simulator": {"host": "127.0.0.1", "port": SIM}}, f)
        self.env = dict(os.environ, G8ID_CONFIG=self.cfg, G8ID_DATA=os.path.join(self.dir, "data"),
                        G8ID_NO_BROWSER="1", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
        self.app = self.sim = None

    def set_mode_file(self, mode):
        os.makedirs(self.env["G8ID_DATA"], exist_ok=True)
        with open(os.path.join(self.env["G8ID_DATA"], "mode.json"), "w") as f:
            json.dump({"mode": mode}, f)

    def _popen(self, args, name):
        out = open(os.path.join(self.dir, name + ".out"), "a", encoding="utf-8")
        return subprocess.Popen([sys.executable] + args, cwd=ROOT, env=self.env, stdout=out,
                                stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)

    def start_app(self):
        t0 = time.time()
        self.app = self._popen(["-m", "app.main"], "app")
        wait(lambda: http(APP + "/api/mode", timeout=2)[0] == 200, 60, "phần mềm chính sẵn sàng")
        return time.time() - t0

    def start_sim(self):
        self.sim = self._popen(["simulator/sim_main.py"], "sim")
        wait(lambda: http(SIMU + "/sim/state", timeout=2)[0] == 200, 30, "công cụ mô phỏng sẵn sàng")

    def stop_sim(self):
        if self.sim and self.sim.poll() is None:
            self.sim.kill()
            self.sim.wait(10)
        self.sim = None

    def kill_all(self):
        for p in (self.sim, self.app):
            if p and p.poll() is None:
                p.kill()
        # mongod riêng của bộ thử (nếu còn sống sau khi kill cứng)
        try:
            import pymongo
            c = pymongo.MongoClient("mongodb://127.0.0.1:%d" % MONGO, serverSelectionTimeoutMS=1500)
            try:
                c.admin.command("shutdown")
            except Exception:
                pass
            c.close()
        except Exception:
            pass
        time.sleep(1.5)
        shutil.rmtree(self.dir, ignore_errors=True)


def sim_set(**kw):
    http(SIMU + "/sim/set", kw)


def place(weight=300):
    http(SIMU + "/sim/place", {"weight": weight})


def remove():
    http(SIMU + "/sim/remove", {})


def order(pallets, cartons, **kw):
    s, r = http(SIMU + "/sim/order", dict(pallets=pallets, cartons=cartons, **kw))
    assert r["ok"], "gửi lệnh lỗi: %s" % r
    return r["order"]


def start():
    s, r = http(APP + "/api/start", {})
    assert r.get("ok"), "Bắt đầu bị từ chối: %s" % r
    wait(lambda: state()["running"], 5, "RUN")


def stop():
    t0 = time.time()
    http(APP + "/api/stop", {})
    wait(lambda: not state()["running"], 10, "STOP")
    return time.time() - t0


def carton_ok(expect_done):
    """Một lượt thùng đạt: đặt -> chờ kết quả -> nhấc."""
    wait(lambda: state()["message"].startswith(("CHỜ ĐẶT", "SẴN SÀNG")), 20, "trạm chờ thùng")
    place(300)
    wait(lambda: state()["carton"][0] >= expect_done or state()["message"].startswith(
        ("ĐÃ HOÀN THÀNH PALLET", "PALLET OK")), 30,
         "thùng thứ %d đạt" % expect_done)
    remove()


def e2e_tests(env):
    def t_boot():
        env.set_mode_file("MANUAL")
        secs = env.start_app()
        assert secs < 30, "khởi động mất %.1f s" % secs
        s = state()
        assert s["mode"] == "MANUAL" and not s["running"] and s["wcs"] is True
        print("         (khởi động + MongoDB sẵn sàng sau %.1f s)" % secs)

    def t_sim_start():
        env.start_sim()
        wait(lambda: all(state()["dev"][k]["ok"] for k in ("plc", "printer", "scale", "barcode")),
             15, "4 thiết bị mô phỏng xanh")
        r = http(APP + "/api/settings", {"time_scale": 1, "scale_value": 300,
                                         "scale_error": 50})[1]
        assert r["ok"], r
        for url in (APP + "/guide", SIMU + "/guide"):
            with urllib.request.urlopen(url, timeout=5) as g:
                assert g.status == 200 and g.read(5) == b"%PDF-", url

    def t_order_api():
        assert http(ORDER + "/ids/orderTask/", method="GET")[0] == 405
        s, r = http(ORDER + "/ids/orderTask/", raw=b"", method="POST")
        assert (s, r["desc"]) == (400, "Empty body"), (s, r)
        s, r = http(ORDER + "/ids/orderTask/", raw=b"{oops", method="POST")
        assert (s, r["desc"]) == (400, "Invalid JSON"), (s, r)
        s, r = http(ORDER + "/ids/orderTask/", {"PO_ID": 0, "info_detail": []})
        assert (s, r["code"], r["desc"]) == (400, 1001, "order_id invalid"), (s, r)
        s, r = http(APP + "/api/start", {})
        assert not r["ok"] and "KHÔNG CÓ LỆNH SẢN XUẤT" in r["error"], r

    def t_wcs_real_order():
        # Đúng dạng lệnh WCS thật (log 19/10/2026), rút gọn còn 2 thùng: GW kg/thùng, không có
        # Weight_ref, Pallet_Current ở cấp lệnh, mã lệnh in trên tem lấy PO_Name.
        cl = ["TRU_G01_50W_AT|||||||6|0|G8HOME2347843845538600%d||001||||||||01" % i for i in (1, 2)]
        o = {"Task_ID": "1-190146369__14:38:41.059898", "PO_ID": 190146369,
             "PO_Name": "VAS-091026-3", "WH_Code": "WH_TB", "Line_ID": "MCSX001",
             "info_detail": [{"Item_Code": "TRU_G01_50W_AT",
                              "Item_Name": "Bóng Led trụ nhôm T50,model T50-125/G01 (6c/T hoặc 24c/T)",
                              "MFG_Date": "09/10/2026", "Pallet_ID": "LPN03020",
                              "Location": "S02.257.1", "Carton_List": cl, "Ctn": 2, "Qty": 12,
                              "Pcs": 0, "Inner_Carton": 6, "Inner_Pallet": 2, "NW": 0.0,
                              "GW": 1.637}],
             "fromSystem": "IdentifyService", "Pallet_Current": 1}
        s, r = http(ORDER + "/ids/orderTask/", o)
        assert (s, r["code"]) == (200, 1000), (s, r)
        wait(lambda: state()["has_order"], 10, "nạp lệnh WCS")
        assert state()["pallet"]["weight"].startswith("1637 ±"), state()["pallet"]
        t = time.strftime("%Y-%m-%d")
        row = http(APP + "/api/orders?from=%s&to=%s" % (t, t))[1]["pending"][0]
        assert (row["pallet_current"], row["weight_ref"], row["po"]) == (1, 1637, "VAS-091026-3"), row
        if not state()["running"]:
            start()
        wait(lambda: state()["message"].startswith(("CHỜ ĐẶT", "SẴN SÀNG")), 20, "trạm chờ thùng")
        place(1637)
        wait(lambda: state()["carton"][0] >= 1, 30, "thùng 1637 g đạt")
        remove()
        stop()
        last = http(SIMU + "/sim/state")[1]["labels"][-1]
        want = ("VAS-091026-3", "6 chiếc", "09/10/2026")
        assert (last["order"], last["spec"], last["mfg_date"]) == want, last
        assert last["received_code"] == cl[0] and last["item_name"].startswith("Bóng Led trụ"), last
        with urllib.request.urlopen(APP + "/labels?pallet=LPN03020", timeout=5) as g:
            page = g.read().decode("utf-8")
        assert "Mã lệnh" in page and "VAS-091026-3" in page and "6 chiếc" in page, page[-800:]
        # WMS dừng lệnh khi pallet đang dở 1/2 thùng: giữ pallet, ĐỊNH DANH gửi 1 thùng.
        sent = len(http(SIMU + "/sim/state")[1]["received"])
        s, r = http(ORDER + "/ids/cancelTask/", {"Task_ID": o["Task_ID"]})
        assert s == 200 and state()["has_order"] and state()["can_identify"], (s, r)
        assert "WMS DỪNG LỆNH" in state()["message"], state()["message"]
        assert http(APP + "/api/identify", {})[1]["ok"]
        wait(lambda: not state()["has_order"], 10, "gửi pallet dở của lệnh đã dừng")
        got = http(SIMU + "/sim/state")[1]["received"]
        assert len(got) == sent + 1 and got[-1]["body"]["palletID"] == "LPN03020" and \
            got[-1]["body"]["Ctn"] == 1, got[-1]
        http(APP + "/api/counter/reset", {})              # bộ đếm ngày về 0 cho các bài sau

    def t_full_order():
        db0 = http(APP + "/api/info")[1]["db"]                # lịch sử có sẵn từ các bài trước
        sent = len(http(SIMU + "/sim/state")[1]["received"])
        o = order(2, 3)
        s = state()
        assert s["carton"] == [0, 3] and s["pallets"] == [0, 2] and s["order"] == [0, 6], s["carton"]
        assert s["rows"][0]["code"].startswith("TP") and "|" not in s["rows"][0]["code"]
        start()
        for pallet in range(2):
            for n in range(1, 4):
                carton_ok(n)
            wait(lambda: state()["message"].startswith("ĐÃ HOÀN THÀNH PALLET"), 30, "chờ ĐỊNH DANH")
            assert state()["can_identify"]
            assert http(APP + "/api/identify", {})[1]["ok"]
            wait(lambda: state()["pallets"][0] == pallet + 1 or not state()["has_order"], 15,
                 "pallet %d xong" % (pallet + 1))
            if pallet == 0:     # số thùng hoàn thành tính theo lệnh: 3 thùng xong / 6 thùng của lệnh
                assert state()["order"] == [3, 6], state()["order"]
        wait(lambda: not state()["running"], 15, "tự STOP khi hết lệnh")
        assert state()["message"] == "ĐÃ HOÀN TẤT LỆNH SẢN XUẤT", state()["message"]
        got = http(SIMU + "/sim/state")[1]["received"][sent:]
        ids = [g["body"]["palletID"] for g in got]
        want = [d["Pallet_ID"] for d in o["info_detail"]]
        assert ids == want, "server nhận %s, mong %s" % (ids, want)
        assert all(g["body"]["Ctn"] == 3 and g["body"]["Task_ID"] == o["Task_ID"] for g in got)
        c = state()["counter"]
        assert (c["pass"], c["fail"]) == (6, 0), c
        info = http(APP + "/api/info")[1]["db"]
        assert info["pallets"] == 0 and info["parcels"] == 0, "bảng đang làm phải rỗng: %s" % info
        grew = (info["pallets_his"] - db0["pallets_his"], info["parcels_his"] - db0["parcels_his"])
        assert grew == (2, 6), info

    def t_shared_lpn():
        # WCS dùng chung Pallet_ID giữ chỗ "LPN0-0-0" cho nhiều pallet cùng PO, mỗi pallet một
        # Task_ID (log 24/10/2026): phải nhận đủ, không coi là gửi lặp; gửi lặp nhận theo Task_ID.
        def o(n):
            return {"Task_ID": "%d-190918952__16:08:02" % n, "PO_ID": 190918952,
                    "PO_Name": "VAS-231026-2", "WH_Code": "WH_TB", "Line_ID": "MCSX005",
                    "info_detail": [{"Item_Code": "TRU_G01_30W_AT", "Item_Name": "Bóng Led trụ nhôm T30",
                                     "MFG_Date": "05/11/2026", "Pallet_ID": "LPN0-0-0",
                                     "Location": "S02.223.1", "Ctn": 1, "Qty": 12, "Pcs": 0,
                                     "Carton_List": ["TRU_G01_30W_AT|||||||12|0|G8HOMELPN%03d||001||||||||01" % n],
                                     "Inner_Carton": 12, "Inner_Pallet": 1, "NW": 0.0, "GW": 1.637}],
                    "fromSystem": "IdentifyService", "Pallet_Current": n}
        sent = len(http(SIMU + "/sim/state")[1]["received"])
        for x in (o(1), o(2), o(1)):                       # lần 3 = WCS gửi lặp lệnh 1
            s, r = http(ORDER + "/ids/orderTask/", x)
            assert (s, r["code"]) == (200, 1000), (s, r)
        t = time.strftime("%Y-%m-%d")
        pend = http(APP + "/api/orders?from=%s&to=%s" % (t, t))[1]["pending"]
        assert [(x["pallet_id"], x["lpn"]) for x in pend] == \
            [(o(1)["Task_ID"], "LPN0-0-0"), (o(2)["Task_ID"], "LPN0-0-0")], pend
        # Tìm "Mã pallet" theo LPN ra cả hai; theo Task_ID ra đúng một.
        assert len(http(APP + "/api/orders?pallet=LPN0-0-0")[1]["pending"]) == 2
        assert len(http(APP + "/api/orders?pallet=2-190918952")[1]["pending"]) == 1
        if not state()["running"]:
            start()
        for k in range(2):
            wait(lambda: state()["message"].startswith(("CHỜ ĐẶT", "SẴN SÀNG")), 20, "trạm chờ thùng")
            place(1637)
            wait(lambda: state()["message"].startswith("ĐÃ HOÀN THÀNH PALLET"), 30, "chờ ĐỊNH DANH")
            remove()
            assert http(APP + "/api/identify", {})[1]["ok"]
            wait(lambda: len(http(SIMU + "/sim/state")[1]["received"]) >= sent + k + 1, 15,
                 "gửi pallet %d" % (k + 1))
        wait(lambda: not state()["running"], 15, "tự STOP khi hết lệnh")
        got = http(SIMU + "/sim/state")[1]["received"][sent:]
        assert [(g["body"]["palletID"], g["body"]["Task_ID"]) for g in got] == \
            [("LPN0-0-0", o(1)["Task_ID"]), ("LPN0-0-0", o(2)["Task_ID"])], got
        # WMS xác nhận theo LPN dùng chung: không nhầm sang pallet khác (đã xong cả hai).
        s, r = http(ORDER + "/ids/confirm_product/", {"PO_ID": 190918952, "Line_ID": "MCSX005",
                                                      "Pallet_ID": "LPN0-0-0", "Status": "true"})
        assert s == 200, (s, r)
        http(APP + "/api/counter/reset", {})

    def job_done():
        j = state()["job"]
        return j if j and not j["active"] else None

    def t_reprint_history():
        his = http(APP + "/api/history")[1]["rows"]
        pid = his[0]["pallet_id"]
        rows = http(APP + "/api/history/parcels?pallet=" + urllib.parse.quote(pid))[1]["rows"]
        codes = [x["code"] for x in rows]
        assert len(codes) == 3, codes
        r = http(APP + "/api/reprint_pallet", {"pallet_id": pid})[1]
        assert r["ok"] and r["total"] == 3, r
        j = wait(job_done, 20, "in lại xong")
        assert (j["done"], j["error"], j["cancelled"]) == (3, "", False), j
        assert state()["message"] == "ĐÃ IN LẠI 3 TEM CỦA PALLET " + his[0]["lpn"], state()["message"]
        labels = http(SIMU + "/sim/state")[1]["labels"][-3:]
        assert [x["type"] for x in labels] == ["carton"] * 3, labels
        assert [x["code"] for x in labels] == codes, labels
        assert all(x["pallet"] == pid for x in labels), labels
        assert all("weight" not in x and x["mfg_date"] == time.strftime("%d/%m/%Y") for x in labels), \
            "tem in lại: bỏ khối lượng, in NSX theo lệnh: %s" % labels
        # Máy in lỗi giữa chừng: dừng lại và báo đúng thùng
        sim_set(printer_fail=True)
        assert http(APP + "/api/reprint_pallet", {"pallet_id": pid})[1]["ok"]
        j = wait(job_done, 20, "in lại dừng vì lỗi")
        assert j["done"] == 0 and j["error"] == "IN LỖI " + codes[0], j
        sim_set(printer_fail=False)
        r = http(APP + "/api/reprint_pallet", {"pallet_id": "KHONG_CO"})[1]
        assert not r["ok"] and "Không tìm thấy pallet" in r["error"], r
        r = http(APP + "/api/reprint_pallet", {})[1]
        assert not r["ok"] and "Chưa có lệnh sản xuất" in r["error"], r

    def t_mfg_and_orders_tab():
        o = order(2, 2)
        p1, p2 = [d["Pallet_ID"] for d in o["info_detail"]]
        stop()                                              # lệnh mới tự Bắt đầu
        today = time.strftime("%d/%m/%Y")
        m = http(APP + "/api/mfg")[1]["mfg"]
        assert m["has_order"] and not m["manual"] and m["lpn"] == p1 and m["next_seq"] == 1, m
        assert m["order_date"] == m["effective"] == today, m
        r = http(APP + "/api/mfg", {"enabled": True, "date": "31/02/2026"})[1]
        assert not r["ok"] and "không hợp lệ" in r["error"], r
        r = http(APP + "/api/mfg", {"enabled": True, "date": "01/02/2026"})[1]
        assert r["ok"] and r["mfg"]["effective"] == "01/02/2026" and r["mfg"]["manual"], r
        assert state()["pallet"]["mfg_date"] == "01/02/2026"
        req = urllib.request.Request(APP + "/api/mfg", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json", "X-Pass": "sai"})
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "sai mật khẩu vẫn sửa được NSX"
        except urllib.error.HTTPError as e:
            assert e.code == 403, e.code
        t = time.strftime("%Y-%m-%d")
        ords = http(APP + "/api/orders?from=%s&to=%s" % (t, t))[1]
        assert [x["lpn"] for x in ords["pending"]] == [p1, p2], ords["pending"]
        assert all(x["mfg_date"] == "01/02/2026" for x in ords["pending"])
        assert ords["stats"]["active"] == 2, ords["stats"]
        r = http(APP + "/api/identify", {"pallet_id": p1})[1]
        assert not r["ok"] and r["title"] == "CHƯA ĐỦ SỐ LƯỢNG HÀNG!", r
        # Tự Bắt đầu rồi Dừng ngay: pallet 1 có thể còn WAIT -> Tải lệnh mới đưa nó vào làm
        r = http(APP + "/api/orders/pull_next", {})[1]
        assert r.get("pallet_id") == p1 or "Đang có lệnh sản xuất đang chạy" in r.get("error", ""), r
        assert http(APP + "/api/orders?from=%s&to=%s" % (t, t))[1]["pending"][0]["status"] == "PROCESSING"
        r = http(APP + "/api/orders/pull_next", {})[1]
        assert not r["ok"] and "Đang có lệnh sản xuất đang chạy" in r["error"], r
        # Tem in ra mang NSX sửa tay; đã có thùng đạt thì khóa sửa NSX
        start()
        carton_ok(1)
        wait(lambda: state()["carton"][0] == 1, 10, "1 thùng đạt")
        stop()
        last = http(SIMU + "/sim/state")[1]["labels"][-1]
        assert last["mfg_date"] == "01/02/2026" and "weight" not in last, last
        # Đã có thùng đạt vẫn sửa được NSX: áp dụng từ thùng in tiếp theo, thùng đã in giữ ngày cũ
        r = http(APP + "/api/mfg", {"enabled": True, "date": "02/02/2026"})[1]
        assert r["ok"] and r["mfg"]["effective"] == "02/02/2026" and r["mfg"]["next_seq"] == 2, r
        rows = http(APP + "/api/orders/parcels?pallet=" + p1)[1]["rows"]
        assert [x["mfg_date"] for x in rows] == ["01/02/2026", "02/02/2026"], rows
        assert state()["pallet"]["mfg_date"] == "02/02/2026"
        r = http(APP + "/api/mfg", {"enabled": False})[1]
        assert r["ok"] and not r["mfg"]["manual"] and r["mfg"]["effective"] == today, r
        # Tải mã định danh + In lại mã định danh (chỉ thùng đã đạt)
        ps = http(APP + "/api/orders/parcels?pallet=" + p1)[1]
        assert (ps["done"], ps["total"]) == (1, 2), ps
        c0, c1 = ps["rows"][0]["code"], ps["rows"][1]["code"]
        assert ps["rows"][0]["mfg_date"] == "01/02/2026", ps["rows"][0]
        r = http(APP + "/api/reprint_pallet", {"pallet_id": p1, "codes": [c0]})[1]
        assert r["ok"] and r["total"] == 1, r
        wait(job_done, 20, "in lại 1 tem")
        assert http(SIMU + "/sim/state")[1]["labels"][-1]["code"] == c0
        r = http(APP + "/api/reprint_pallet", {"pallet_id": p1, "codes": [c1]})[1]
        assert not r["ok"] and "chưa cân / in đạt" in r["error"], r
        # In PDF mã hiện tại: trang tem có QR của mọi thùng
        with urllib.request.urlopen(APP + "/labels?pallet=" + p1, timeout=5) as g:
            page = g.read().decode("utf-8")
        assert c0 in page and c1 in page and page.count("<svg") == 2 and "01/02/2026" in page
        # Thành công ảo: lưu lịch sử DONE, không gửi server
        sent = len(http(SIMU + "/sim/state")[1]["received"])
        r = http(APP + "/api/orders/fake_complete", {"pallet_id": p1})[1]
        assert r["ok"], r
        assert len(http(SIMU + "/sim/state")[1]["received"]) == sent, "thành công ảo không được gửi"
        ords = http(APP + "/api/orders?from=%s&to=%s&pallet=%s" % (t, t, p1))[1]
        assert ords["pending"] == [] and ords["completed"][0]["done_reason"] == "FAKE_COMPLETE", ords
        hist = http(APP + "/api/orders/parcels?pallet=%s&key=%s" % (p1, ords["completed"][0]["key"]))[1]
        assert (hist["done"], hist["total"]) == (1, 2), hist
        # Tải lệnh mới -> Xóa lệnh đang làm -> Thực hiện lại
        r = http(APP + "/api/orders/pull_next", {})[1]
        assert r["ok"] and r["pallet_id"] == p2, r
        r = http(APP + "/api/orders/delete", {"pallet_id": p2})[1]
        assert r["ok"] and len(r["cancelled"]) == 1, r
        assert not state()["has_order"]
        ords = http(APP + "/api/orders?from=%s&to=%s&pallet=%s" % (t, t, p2))[1]
        assert ords["completed"][0]["status"] == "CANCEL", ords["completed"]
        assert http(APP + "/api/reload", {"pallet_id": p2})[1]["ok"]
        ords = http(APP + "/api/orders?from=%s&to=%s" % (t, t))[1]
        assert [x["lpn"] for x in ords["pending"]] == [p2], ords["pending"]
        assert http(APP + "/api/orders/delete", {"pallet_id": p2})[1]["ok"]
        assert not state()["has_order"]

    def t_ng_cases():
        order(1, 2)
        start()
        # Lưu thông số ngay lúc đang chạy
        r = http(APP + "/api/settings", {"scale_error": 50})[1]
        assert r["ok"] and state()["running"], r
        # Sai khối lượng: NG, không tiêu mã
        wait(lambda: state()["message"].startswith(("CHỜ ĐẶT", "SẴN SÀNG")), 20, "chờ thùng")
        place(900)
        wait(lambda: state()["big"] == "NG", 20, "NG khối lượng")
        assert "KHÔNG ĐẠT" in state()["message"] and state()["light"] == "red"
        assert state()["carton"][0] == 0
        remove()
        # In lỗi: giữ mã, hiện "In lỗi"
        wait(lambda: state()["message"].startswith(("CHỜ ĐẶT", "SẴN SÀNG")), 20, "chờ thùng")
        sim_set(printer_fail=True)
        place(300)
        wait(lambda: "IN TEM THẤT BẠI" in state()["message"], 20, "báo in lỗi")
        assert state()["rows"][0]["text"] == "In lỗi", state()["rows"][0]
        sim_set(printer_fail=False)
        remove()
        # Đọc sai 1 lần rồi đúng: vẫn đạt nhờ đọc lại lần 2
        sim_set(barcode_mode="wrong_once")
        carton_ok(1)
        assert state()["rows"][0]["st"] == 1
        # Đọc sai cả 2 lần: NG, giữ mã để in lại
        sim_set(barcode_mode="wrong")
        wait(lambda: state()["message"].startswith(("CHỜ ĐẶT", "SẴN SÀNG")), 20, "chờ thùng")
        place(300)
        wait(lambda: "KHÔNG ĐỌC ĐƯỢC MÃ VẠCH" in state()["message"], 30, "báo đọc mã lỗi")
        assert state()["carton"][0] == 1 and state()["rows"][1]["text"] == "In lỗi"
        sim_set(barcode_mode="ok")
        remove()
        c = state()["counter"]
        assert c["fail"] == 3, "bộ đếm Sai phải là 3: %s" % c

    def t_scale_lost_and_stop():
        wait(lambda: state()["message"].startswith(("CHỜ ĐẶT", "SẴN SÀNG")), 20, "chờ thùng")
        sim_set(scale_online=False)
        wait(lambda: "MẤT TÍN HIỆU CÂN" in state()["message"], 10, "báo mất cân")
        assert state()["weight"] is None
        sim_set(scale_online=True)
        wait(lambda: state()["message"].startswith("CHỜ ĐẶT"), 10, "tự chạy lại sau khi có cân")
        # Dừng ngay giữa lúc đang chờ đọc mã vạch (bản cũ treo ở bước này)
        sim_set(barcode_mode="none")
        place(300)
        wait(lambda: state()["message"].startswith("ĐANG ĐỌC MÃ VẠCH"), 20, "đang đọc mã")
        # Như bản cũ: không có mã thì nghe tiếp, không tự báo NG
        time.sleep(6)
        assert state()["message"].startswith("ĐANG ĐỌC MÃ VẠCH") and state()["big"] != "NG", \
            (state()["message"], state()["big"])
        secs = stop()
        assert secs < 7, "Dừng mất %.1f s" % secs
        assert state()["big"] == "STOP" and state()["light"] == "off"
        sim_set(barcode_mode="ok")
        remove()
        print("         (Dừng giữa lúc đọc mã mất %.1f s)" % secs)
        # Pallet đang làm dở (1/2 thùng đạt): chỉ in lại thùng đã đạt
        done = [x["code"] for x in state()["rows"] if x["st"] >= 1]
        r = http(APP + "/api/reprint_pallet", {})[1]
        assert r["ok"] and r["total"] == 1 and len(done) == 1, (r, done)
        j = wait(job_done, 20, "in lại pallet đang làm")
        assert j["done"] == 1 and not j["error"], j
        last = http(SIMU + "/sim/state")[1]["labels"][-1]
        assert (last["type"], last["code"]) == ("carton", done[0]), last
        assert state()["carton"][0] == 1, "in lại không được đổi tiến độ"

    def t_plc_buttons():
        def press(name):
            assert http(SIMU + "/sim/plc_button", {"name": name, "hold_ms": 400})[1]["ok"]
            time.sleep(0.6)                                  # nút nhả rồi mới nhấn nút khác

        order(1, 1)
        wait(lambda: state()["running"], 10, "lệnh mới tự Bắt đầu")
        press("stop")
        wait(lambda: not state()["running"], 10, "nút STOP (M22) dừng trạm")
        press("identify")
        wait(lambda: state()["message"] == "CHƯA ĐỦ SỐ LƯỢNG HÀNG!", 5, "ĐỊNH DANH khi chưa đủ thùng")
        press("start")
        wait(lambda: state()["running"], 10, "nút START (M20) chạy trạm")
        sent = len(http(SIMU + "/sim/state")[1]["received"])
        carton_ok(1)
        wait(lambda: state()["message"].startswith("ĐÃ HOÀN THÀNH PALLET"), 30, "chờ ĐỊNH DANH")
        press("identify")
        wait(lambda: not state()["has_order"], 15, "nút ĐỊNH DANH (M21) gửi pallet")
        assert len(http(SIMU + "/sim/state")[1]["received"]) == sent + 1
        wait(lambda: not state()["running"], 15, "tự STOP khi hết lệnh")
        press("start")
        wait(lambda: "KHÔNG CÓ LỆNH SẢN XUẤT" in state()["message"], 5, "START khi không có lệnh")
        assert not state()["running"]
        http(APP + "/api/counter/reset", {})

    def t_server_retry():
        start()
        sim_set(server_mode="error")
        carton_ok(2)
        wait(lambda: state()["message"].startswith("ĐÃ HOÀN THÀNH PALLET"), 30, "chờ ĐỊNH DANH")
        r = http(APP + "/api/identify", {})[1]
        assert not r["ok"] and "GỬI PALLET LỖI" in r["error"], r
        wait(lambda: state()["message"].startswith("ĐANG CHỜ GỬI PALLET"), 10, "báo chờ gửi")
        assert state()["rcs"] is False and state()["has_order"]
        sim_set(server_mode="ok")
        wait(lambda: not state()["has_order"], 15, "tự gửi lại thành công")
        wait(lambda: not state()["running"], 10, "STOP")
        assert state()["rcs"] is True

    def t_stop_order_running():
        # Như WCS thật: PO 2 pallet x 3 thùng, mỗi pallet một bản tin / một Task_ID. Đang chạy
        # pallet 1 được 1 thùng thì WMS dừng PO (gửi Task_ID của pallet 1): pallet 2 bị hủy,
        # pallet đang làm giữ lại; bấm ĐỊNH DANH khi đang chạy gửi số thùng thực tế.
        p1, p2 = "STOPPO1", "STOPPO2"
        for n, pid in ((1, p1), (2, p2)):
            cl = ["IT|||||||6|0|%s%03d||001||||||||01" % (pid, i) for i in (1, 2, 3)]
            s, r = http(ORDER + "/ids/orderTask/", {
                "Task_ID": "%d-555001__10:00:0%d" % (n, n), "PO_ID": 555001, "PO_Name": "VAS-STOP",
                "WH_Code": "WH_TB", "Line_ID": "MCSX001", "Pallet_Current": n,
                "info_detail": [{"Item_Code": "IT", "Item_Name": "Hàng thử dừng PO",
                                 "Pallet_ID": pid, "Location": "S02.257.1", "Carton_List": cl,
                                 "Ctn": 3, "Inner_Carton": 6, "GW": 0.3}]})
            assert (s, r["code"]) == (200, 1000), (s, r)
        if not state()["running"]:
            start()
        carton_ok(1)
        assert not state()["can_identify"]
        sent = len(http(SIMU + "/sim/state")[1]["received"])
        s, r = http(ORDER + "/ids/cancelTask/", {"Task_ID": "1-555001__10:00:01"})
        assert s == 200 and state()["running"], (s, r)
        assert state()["pallet"]["lpn"] == p1 and state()["pallets"] == [0, 1], state()["pallets"]
        assert state()["can_identify"]
        wait(lambda: "LỆNH ĐÃ DỪNG" in state()["message"], 10, "báo lệnh đã dừng khi chờ thùng")
        carton_ok(2)                                       # vẫn làm nốt được
        assert http(APP + "/api/identify", {})[1]["ok"]
        wait(lambda: not state()["has_order"], 15, "gửi pallet dở")
        wait(lambda: not state()["running"], 15, "tự STOP khi hết lệnh")
        got = http(SIMU + "/sim/state")[1]["received"]
        assert [(g["body"]["palletID"], g["body"]["Ctn"]) for g in got[sent:]] == [(p1, 2)], got[sent:]
        rows = http(APP + "/api/history?q=" + p2)[1]["rows"]
        assert rows and rows[0]["status"] == "CANCEL", rows
        http(APP + "/api/counter/reset", {})

    def t_cancel_and_duplicate():
        o = order(2, 2)
        s, r = http(ORDER + "/ids/orderTask/", o)          # WMS gửi lặp cùng lệnh
        assert s == 200 and r["code"] == 1000
        assert len(http(APP + "/api/info")[1]["queue"]) == 2, "lệnh lặp không được nhân đôi"
        p1, p2 = [d["Pallet_ID"] for d in o["info_detail"]]
        wait(lambda: state()["running"] and state()["pallet"]["lpn"] == p1, 10,
             "lệnh mới tự Bắt đầu pallet 1")
        sent = len(http(SIMU + "/sim/state")[1]["received"])
        # Dừng PO khi pallet đang làm chưa có thùng đạt: vẫn giữ pallet đang làm, hủy pallet chờ.
        s, r = http(ORDER + "/ids/cancelTask/", {"Task_ID": o["Task_ID"]})
        assert s == 200 and state()["has_order"] and state()["can_identify"], (s, r)
        rows = http(APP + "/api/history?q=" + p2)[1]["rows"]
        assert rows and rows[0]["status"] == "CANCEL", rows
        # ĐỊNH DANH khi 0 thùng đạt: đóng pallet, không gửi gì về server.
        assert http(APP + "/api/identify", {})[1]["ok"]
        wait(lambda: not state()["has_order"], 10, "đóng pallet 0 thùng")
        assert len(http(SIMU + "/sim/state")[1]["received"]) == sent
        rows = http(APP + "/api/history?q=" + p1)[1]["rows"]
        assert rows and rows[0]["status"] == "CANCEL", rows
        wait(lambda: not state()["running"], 10, "tự STOP khi hết lệnh")
        s, r = http(ORDER + "/ids/cancelTask/", {"foo": 1})
        assert (s, r["desc"]) == (400, "Task_ID invalid"), (s, r)
        s, r = http(ORDER + "/ids/confirm_product/", {"PO_ID": 0})
        assert (s, r["desc"]) == (400, "PO_ID invalid"), (s, r)
        s, r = http(ORDER + "/ids/confirm_product/", {"PO_ID": 7, "Pallet_ID": "P1"})
        assert (s, r["desc"]) == (400, "Line_ID or Pallet_ID invalid"), (s, r)
        s, r = http(ORDER + "/ids/confirm_product/", {"PO_ID": 7, "Line_ID": "LINE_01",
                                                      "Pallet_ID": "P1", "Status": "false",
                                                      "Message": "sai vi tri"})
        assert s == 200 and "Lỗi từ WMS: sai vi tri" in state()["message"], (s, state()["message"])
        s, r = http(ORDER + "/ids/confirm_product/", {"PO_ID": 7, "Line_ID": "LINE_01",
                                                      "Pallet_ID": "P1", "Status": "true"})
        assert s == 200 and state()["message"] == "ĐÃ HOÀN THÀNH PALLET: P1", state()["message"]

    def t_power_loss():
        order(1, 3)
        start()
        carton_ok(1)
        wait(lambda: state()["carton"][0] == 1, 10, "1 thùng đạt")
        env.app.kill()                                     # mất điện: không có cơ hội dọn dẹp
        env.app.wait(10)
        secs = env.start_app()
        s = state()
        assert s["carton"] == [1, 3] and not s["running"], "tiến độ sau mất điện: %s" % s["carton"]
        assert s["mode"] == "MANUAL"
        wait(lambda: all(state()["dev"][k]["ok"] for k in ("printer", "scale", "barcode")), 15,
             "thiết bị nối lại")
        start()
        carton_ok(2)
        carton_ok(3)
        wait(lambda: state()["message"].startswith("ĐÃ HOÀN THÀNH PALLET"), 30, "chờ ĐỊNH DANH")
        assert http(APP + "/api/identify", {})[1]["ok"]
        wait(lambda: not state()["running"], 15, "STOP")
        print("         (khởi động lại sau mất điện: %.1f s, tiến độ còn nguyên)" % secs)

    def t_hybrid():
        # HYBRID: thiết bị thật, WCS/RCS vẫn là công cụ mô phỏng (không bị đuổi về như AUTO)
        r = http(APP + "/api/mode", {"mode": "HYBRID"})[1]
        assert r["ok"], r
        time.sleep(2.5)
        assert env.sim.poll() is None, "công cụ mô phỏng phải chạy tiếp ở HYBRID"
        assert http(SIMU + "/sim/state")[1]["app"] == "HYBRID"
        info = http(APP + "/api/info")[1]
        assert ":%d/" % SIM in info["pallet_done_url"], info["pallet_done_url"]
        assert info["db_name"].endswith("manual"), info["db_name"]
        o = order(1, 2)
        assert any(q["task_id"] == o["Task_ID"] for q in http(APP + "/api/info")[1]["queue"])
        # Thiết bị thật không có trên máy thử -> Bắt đầu bị chặn đúng thông báo
        r = http(APP + "/api/start", {})[1]
        assert not r["ok"] and "MÁY IN" in r["error"], r
        assert http(SIMU + "/sim/cancel", {"Task_ID": o["Task_ID"]})[1]["ok"]
        r = http(APP + "/api/mode", {"mode": "MANUAL"})[1]
        assert r["ok"], r
        wait(lambda: all(state()["dev"][k]["ok"] for k in ("printer", "scale", "barcode")), 15,
             "thiết bị mô phỏng nối lại")

    def t_interlock():
        # Mô phỏng còn chạy -> không cho về AUTO
        r = http(APP + "/api/mode", {"mode": "AUTO"})[1]
        assert not r["ok"] and "MÔ PHỎNG CHƯA ĐÓNG" in r["error"], r
        assert state()["mode"] == "MANUAL"
        # Cửa sổ .bat còn giữ file lock -> vẫn không cho, dù tiến trình mô phỏng đã chết
        env.stop_sim()
        lock = os.path.join(env.env["G8ID_DATA"], "simulator_bat.lock")
        holder = subprocess.Popen('(ping -n 30 127.0.0.1 >nul) 9>"%s"' % lock, shell=True)
        time.sleep(4)
        r = http(APP + "/api/mode", {"mode": "AUTO"})[1]
        assert not r["ok"] and "chay_mo_phong.bat còn mở" in r["error"], r
        subprocess.run("taskkill /F /T /PID %d" % holder.pid, shell=True, capture_output=True)
        time.sleep(4)
        # Đã đóng hẳn -> cho về AUTO
        r = http(APP + "/api/mode", {"mode": "AUTO"})[1]
        assert r["ok"], r
        assert state()["mode"] == "AUTO"
        # Ở AUTO: công cụ mô phỏng từ chối chạy
        p = env._popen(["simulator/sim_main.py"], "sim_refused")
        assert p.wait(20) == 2, "mô phỏng phải thoát mã 2 khi phần mềm ở AUTO"
        # Ở AUTO: thiết bị thật không có trên máy thử -> Bắt đầu bị chặn đúng thông báo
        r = http(APP + "/api/start", {})[1]
        assert not r["ok"] and "MÁY IN" in r["error"], r
        # AUTO dùng DB riêng: không thấy dữ liệu mô phỏng
        assert http(APP + "/api/info")[1]["db"]["pallets_his"] == 0

    def t_clean_exit():
        assert http(APP + "/api/quit", {})[1]["ok"]
        assert env.app.wait(40) == 0, "mã thoát phải là 0"
        import socket
        for port in (UI, ORD, MONGO):
            s = socket.socket()
            s.settimeout(0.5)
            busy = s.connect_ex(("127.0.0.1", port)) == 0
            s.close()
            assert not busy, "cổng %d còn mở sau khi thoát" % port
        log_dir = os.path.join(env.dir, "logs")
        names = os.listdir(log_dir)
        assert any(n.startswith("app-") for n in names) and any(n.startswith("http-") for n in names)
        text = open(os.path.join(log_dir, [n for n in names if n.startswith("app-")][0]),
                    encoding="utf-8").read()
        assert "Đã thoát sạch" in text

    check("Khởi động ở MANUAL (bật mongod kèm theo)", t_boot)
    check("Công cụ mô phỏng nối 4 thiết bị", t_sim_start)
    check("Cổng nhận lệnh: 405 / Empty body / Invalid JSON / order_id invalid", t_order_api)
    check("Lệnh WCS thật: GW -> chuẩn 1637 g, Pallet_Current, tem mã lệnh PO_Name", t_wcs_real_order)
    check("Lệnh 2 pallet x 3 thùng: cân-in-đọc-định danh-lưu lịch sử", t_full_order)
    check("In lại toàn bộ tem pallet từ lịch sử; máy in lỗi giữa chừng", t_reprint_history)
    check("LPN dùng chung (LPN0-0-0) cùng PO: nhận đủ, gửi lặp theo Task_ID, gửi WMS theo LPN",
          t_shared_lpn)
    check("Ngày sản xuất sửa tay + các nút thẻ Thông số như bản cũ", t_mfg_and_orders_tab)
    check("NG: sai khối lượng / in lỗi / đọc lại lần 2 / đọc sai 2 lần", t_ng_cases)
    check("Mất tín hiệu cân tự hồi phục; đầu đọc chờ tới khi có mã; Dừng không treo",
          t_scale_lost_and_stop)
    check("Server lỗi: giữ pallet, tự gửi lại tới khi nhận", t_server_retry)
    check("Nút vật lý trên tủ (PLC): START / STOP / ĐỊNH DANH", t_plc_buttons)
    check("WMS dừng lệnh khi đang chạy: hủy pallet sau, làm nốt + ĐỊNH DANH pallet dở",
          t_stop_order_running)
    check("Lệnh gửi lặp không nhân đôi; cancelTask hủy lệnh; confirm_product", t_cancel_and_duplicate)
    check("Mất điện giữa lệnh: khởi động lại còn nguyên tiến độ", t_power_loss)
    check("HYBRID: thiết bị thật + WCS/RCS mô phỏng", t_hybrid)
    check("Khoá liên động AUTO <-> công cụ mô phỏng", t_interlock)
    check("Thoát sạch: mã 0, đóng cổng, tắt mongod, có log", t_clean_exit)


def main():
    print("\n=== KIỂM TRA ĐƠN VỊ ===")
    unit_tests()
    print("\n=== KIỂM TRA ĐẦU-CUỐI (MANUAL + công cụ mô phỏng) ===")
    env = Env()
    try:
        e2e_tests(env)
    finally:
        keep = os.environ.get("G8ID_KEEP_TEST_DIR")
        if keep:
            shutil.copytree(env.dir, keep, dirs_exist_ok=True)
        env.kill_all()
    bad = [r for r in results if not r[1]]
    print("\n=== KẾT QUẢ: %d/%d đạt ===" % (len(results) - len(bad), len(results)))
    for name, _, err in bad:
        print("  LỖI: %s -> %s" % (name, err))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
