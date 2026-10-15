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
    from app.engine import field, parse_carton

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

    check("Phân tích bản tin cân (g / kg / rác)", t_scale)
    check("Tách mã thùng từ Carton_List", t_carton)
    check("Đọc trường không phân biệt hoa thường", t_field)
    check("Driver cân RS232: đọc luồng, mất tín hiệu, tự mở lại cổng, đóng sạch", t_serial_scale)
    check("Driver đầu đọc RS232: kích 16 54 0D / tắt 16 55 0D, hết giờ, Dừng", t_serial_barcode)
    check("Driver máy in: nạp được EZio DLL của bản cũ", t_printer_dll)
    check("Driver PLC MX Component (control giả): Open, đèn M0/M1/M2/M10, mất nối, Close", t_plc_mx)


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
        s = scale.SerialScale({"port": "COMX", "baudrate": 9600, "stale_s": 0.4, "reopen_s": 0.8})
        s.start()
        wait(lambda: s.read() == 305, 3, "đọc được 305 g")
        wait(lambda: s.read() is None, 3, "hết dữ liệu -> báo mất cân, không dùng số cũ")
        wait(lambda: len(ports) >= 2, 5, "tự đóng/mở lại cổng khi cân im lặng")
        assert ports[0].closed, "cổng cũ phải được đóng trước khi mở lại"
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


def t_printer_dll():
    from app import config
    from app.devices.printer_godex import GodexPrinter
    config.load()
    p = GodexPrinter({"connect_type": "USB", "usb_name": ""})
    dll = p._load()
    for fn in ("OpenUSB", "FindFirstUSB", "sendcommand", "ecTextOutRW", "Bar_QRcode", "putimage",
               "closeport"):
        assert hasattr(dll, fn), "DLL thiếu hàm " + fn
    assert p.print_carton("X", "", "", "", 0) is False, "chưa nối máy in thì in phải trả lỗi"


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
        ("ĐÃ HOÀN THÀNH PALLET", "PALLET OK", "IN MÃ PALLET", "ĐANG ĐỌC MÃ PALLET")), 30,
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
        r = http(APP + "/api/settings", {"time_scale": 1, "pallet_print_delay_s": 0,
                                         "scale_value": 300, "scale_error": 50})[1]
        assert r["ok"], r

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

    def t_full_order():
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
        wait(lambda: not state()["running"], 15, "tự STOP khi hết lệnh")
        assert state()["message"] == "ĐÃ HOÀN TẤT LỆNH SẢN XUẤT", state()["message"]
        got = http(SIMU + "/sim/state")[1]["received"]
        ids = [g["body"]["palletID"] for g in got]
        want = [d["Pallet_ID"] for d in o["info_detail"]]
        assert ids == want, "server nhận %s, mong %s" % (ids, want)
        assert all(g["body"]["Ctn"] == 3 and g["body"]["Task_ID"] == o["Task_ID"] for g in got)
        c = state()["counter"]
        assert (c["pass"], c["fail"]) == (6, 0), c
        info = http(APP + "/api/info")[1]["db"]
        assert info["pallets"] == 0 and info["parcels"] == 0, "bảng đang làm phải rỗng: %s" % info
        assert info["pallets_his"] == 2 and info["parcels_his"] == 6, info

    def job_done():
        j = state()["job"]
        return j if j and not j["active"] else None

    def t_reprint_history():
        his = http(APP + "/api/history")[1]["rows"]
        pid = his[0]["pallet_id"]
        rows = http(APP + "/api/history/parcels?pallet=" + pid)[1]["rows"]
        codes = [x["code"] for x in rows]
        assert len(codes) == 3, codes
        r = http(APP + "/api/reprint_pallet", {"pallet_id": pid})[1]
        assert r["ok"] and r["total"] == 4, r
        j = wait(job_done, 20, "in lại xong")
        assert (j["done"], j["error"], j["cancelled"]) == (4, "", False), j
        assert state()["message"] == "ĐÃ IN LẠI 4 TEM CỦA PALLET " + pid, state()["message"]
        labels = http(SIMU + "/sim/state")[1]["labels"][-4:]
        assert [x["type"] for x in labels] == ["carton"] * 3 + ["pallet"], labels
        assert [x["code"] for x in labels] == codes + [pid], labels
        assert all(x["pallet"] == pid for x in labels[:3]), labels
        assert [x["weight"] for x in labels[:3]] == [x["weight"] for x in rows], \
            "tem in lại phải ghi đúng khối lượng đã cân: %s" % labels
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

    def t_ng_cases():
        order(1, 2)
        start()
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
        # Không đọc được: NG, giữ mã để in lại
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
        secs = stop()
        assert secs < 7, "Dừng mất %.1f s" % secs
        assert state()["big"] == "STOP" and state()["light"] == "off"
        sim_set(barcode_mode="ok")
        remove()
        print("         (Dừng giữa lúc đọc mã mất %.1f s)" % secs)
        # Pallet đang làm dở (1/2 thùng đạt): chỉ in lại thùng đã đạt, chưa in tem pallet
        done = [x["code"] for x in state()["rows"] if x["st"] >= 1]
        r = http(APP + "/api/reprint_pallet", {})[1]
        assert r["ok"] and r["total"] == 1 and len(done) == 1, (r, done)
        j = wait(job_done, 20, "in lại pallet đang làm")
        assert j["done"] == 1 and not j["error"], j
        last = http(SIMU + "/sim/state")[1]["labels"][-1]
        assert (last["type"], last["code"]) == ("carton", done[0]), last
        assert state()["carton"][0] == 1, "in lại không được đổi tiến độ"

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

    def t_cancel_and_duplicate():
        o = order(2, 2)
        s, r = http(ORDER + "/ids/orderTask/", o)          # WMS gửi lặp cùng lệnh
        assert s == 200 and r["code"] == 1000
        assert len(http(APP + "/api/info")[1]["queue"]) == 2, "lệnh lặp không được nhân đôi"
        s, r = http(ORDER + "/ids/cancelTask/", {"Task_ID": o["Task_ID"]})
        assert s == 200, (s, r)
        assert not state()["has_order"]
        rows = http(APP + "/api/history?q=" + o["info_detail"][0]["Pallet_ID"])[1]["rows"]
        assert rows and rows[0]["status"] == "CANCEL", rows
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
        assert not r["ok"] and "run_simulator.bat còn mở" in r["error"], r
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
    check("Lệnh 2 pallet x 3 thùng: cân-in-đọc-định danh-lưu lịch sử", t_full_order)
    check("In lại toàn bộ tem pallet từ lịch sử; máy in lỗi giữa chừng", t_reprint_history)
    check("NG: sai khối lượng / in lỗi / đọc lại lần 2 / không đọc được", t_ng_cases)
    check("Mất tín hiệu cân tự hồi phục; Dừng không treo", t_scale_lost_and_stop)
    check("Server lỗi: giữ pallet, tự gửi lại tới khi nhận", t_server_retry)
    check("Lệnh gửi lặp không nhân đôi; cancelTask hủy lệnh; confirm_product", t_cancel_and_duplicate)
    check("Mất điện giữa lệnh: khởi động lại còn nguyên tiến độ", t_power_loss)
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
