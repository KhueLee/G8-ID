"""Công cụ mô phỏng (chạy bằng chay_mo_phong.bat) - giả lập cân, đầu đọc, máy in, đèn tháp,
hệ thống gửi lệnh (WMS/WCS) và server nhận pallet (RCS). Giao diện web: http://127.0.0.1:8700

Chỉ chạy được khi phần mềm chính đang ở MANUAL (mô phỏng toàn bộ) hoặc HYBRID (thiết bị thật tại
bàn, chỉ dùng phần WCS/RCS của công cụ này); thấy phần mềm chính về AUTO là tự thoát.
"""
import json
import logging
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402
from waitress import create_server  # noqa: E402

from app import config, logsetup  # noqa: E402

log = logging.getLogger("sim")
HERE = os.path.dirname(os.path.abspath(__file__))

cfg = config.load()
APP = "http://127.0.0.1:%s" % cfg["ui"]["port"]
ORDER = "http://127.0.0.1:%s" % cfg["order_server"]["port"]

lock = threading.Lock()
S = {
    "scale_online": True, "weight": 0, "noise": 2,
    "barcode_online": True, "barcode_mode": "ok", "barcode_delay_ms": 300, "last_code": "",
    "last_parcel": "",
    "printer_online": True, "printer_fail": False, "labels": [],
    "plc_online": True, "light": "off",
    "plc_buttons": {"start": False, "stop": False, "identify": False},   # mức bit M20 / M22 / M21
    "server_mode": "ok", "received": [],
    "auto": False, "auto_identify": True, "carton_weight": 300,
    "app": "?", "app_running": False, "events": [],
}
_seq = [int(time.time()) % 100000]


def note(text):
    log.info(text)
    with lock:
        S["events"].append(time.strftime("%H:%M:%S ") + text)
        del S["events"][:-60]


def call(url, body=None, timeout=3.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="GET" if data is None else "POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except ValueError:
            return e.code, {}


app = Flask("sim", static_folder=None)
app.json.ensure_ascii = False


@app.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/")
def index():
    return send_from_directory(os.path.join(HERE, "static"), "index.html")


@app.get("/guide")
def guide():
    return send_from_directory(config.BASE_DIR, config.GUIDE_PDF)


# ------------------------------------------------------------------ thiết bị giả
@app.get("/dev/scale")
def dev_scale():
    w = S["weight"]
    if w > 0 and S["noise"]:
        w += random.randint(-S["noise"], S["noise"])
    return jsonify(online=S["scale_online"], weight=max(0, w))


@app.get("/dev/ping")
def dev_ping():
    return jsonify(barcode=S["barcode_online"], printer=S["printer_online"], plc=S["plc_online"])


@app.post("/dev/barcode/read")
def dev_barcode():
    b = request.get_json(silent=True) or {}
    mode, code = S["barcode_mode"], S["last_code"]
    if not S["barcode_online"] or mode == "none" or not code:
        time.sleep(min(float(b.get("timeout_ms", 5000)), 15000) / 1000.0)
        if b.get("final", True):
            note("[SIM PDA] Không đọc được barcode")
        return jsonify(code="")
    time.sleep(S["barcode_delay_ms"] / 1000.0)
    wrong = "WRONG_" + (S["last_parcel"] or code)     # tem của thùng khác: mã định danh khác
    if mode == "wrong":
        note("[SIM PDA] Đọc sai barcode=" + wrong)
        return jsonify(code=wrong)
    if mode == "wrong_once":
        S["barcode_mode"] = "ok"
        note("[SIM PDA] Đọc sai 1 lần barcode=" + wrong)
        return jsonify(code=wrong)
    note("[SIM PDA] Đọc đúng barcode=" + code)
    return jsonify(code=code)


@app.post("/dev/printer/print")
def dev_printer():
    b = request.get_json(silent=True) or {}
    if not S["printer_online"] or S["printer_fail"]:
        note("[SIM PRINT] Giả lập IN LỖI. Code=%s" % b.get("code"))
        return jsonify(ok=False)
    with lock:
        S["last_code"] = str(b.get("received_code") or b.get("code", ""))   # nội dung mã QR
        S["last_parcel"] = str(b.get("code", ""))
        S["labels"].append(b)
        del S["labels"][:-30]
    note("[SIM PRINT] In giả lập OK. %s" % json.dumps(b, ensure_ascii=False))
    return jsonify(ok=True)


@app.get("/dev/plc/buttons")
def dev_plc_buttons():
    return jsonify(plc=S["plc_online"], buttons=S["plc_buttons"])


@app.post("/sim/plc_button")
def sim_plc_button():
    """Nhấn nút vật lý trên tủ: bit lên 1 trong hold_ms (mặc định 600 ms) rồi về 0, như nút nhả."""
    b = request.get_json(silent=True) or {}
    name = str(b.get("name", ""))
    if name not in S["plc_buttons"]:
        return jsonify(ok=False, error="nút không hợp lệ: " + name), 400
    hold = max(0.25, float(b.get("hold_ms", 600)) / 1000.0)
    S["plc_buttons"][name] = True
    note("[SIM PLC] Nhấn nút %s" % name.upper())

    def release():
        S["plc_buttons"][name] = False
    threading.Timer(hold, release).start()
    return jsonify(ok=True)


@app.post("/dev/plc/light")
def dev_plc():
    color = (request.get_json(silent=True) or {}).get("color", "off")
    if S["light"] != color:
        note("[SIM PLC] Traffic light=" + str(color).upper())
    S["light"] = color
    return jsonify(ok=True)


# ------------------------------------------------------------------ server nhận pallet giả
@app.post("/identify-service/ids/pallet_identify_done")
def srv_pallet_done():
    raw = request.get_data(as_text=True)
    mode = S["server_mode"]
    note("[SIM SERVER] pallet_identify_done (%s): %s" % (mode, raw))
    if mode == "timeout":
        time.sleep(cfg["servers"]["timeout_s"] + 3)
        return jsonify(code=1001, desc="timeout"), 504
    if mode == "error":
        return jsonify(code=1001, desc="Simulated error"), 500
    with lock:
        S["received"].append({"t": time.strftime("%H:%M:%S"), "body": json.loads(raw or "{}")})
        del S["received"][:-50]
    return jsonify(code=1000, desc="SUCCESS")


# ------------------------------------------------------------------ điều khiển từ giao diện mô phỏng
@app.get("/sim/state")
def sim_state():
    return jsonify(S)


@app.post("/sim/set")
def sim_set():
    b = request.get_json(silent=True) or {}
    for k, v in b.items():
        if k in S and k not in ("labels", "received", "events", "app", "app_running", "plc_buttons"):
            S[k] = type(S[k])(v) if not isinstance(S[k], bool) else bool(v)
            note("Đặt %s = %s" % (k, S[k]))
    return jsonify(ok=True)


@app.post("/sim/place")
def sim_place():
    w = int((request.get_json(silent=True) or {}).get("weight", S["carton_weight"]))
    S["weight"] = w
    note("[SIM SCALE] Đặt thùng lên cân, weight=%s" % w)
    return jsonify(ok=True)


@app.post("/sim/remove")
def sim_remove():
    S["weight"] = 0
    note("[SIM SCALE] Giả lập đã bỏ hàng khỏi cân")
    return jsonify(ok=True)


def make_order(pallets, cartons, piped=True, weight_ref=0, location=""):
    _seq[0] += 1
    n = _seq[0]
    detail = []
    for p in range(1, pallets + 1):
        codes = ["TP%05d%02d%03d" % (n, p, c) for c in range(1, cartons + 1)]
        detail.append({
            "Item_Code": "SP-A", "Item_Name": "SAN PHAM MO PHONG", "Pallet_ID": "PL%05d%02d" % (n, p),
            "Location": location or "S01.12%d.01" % ((p - 1) % 3), "PO_Name": "PO-SIM-%05d" % n,
            "Carton_List": ["a|b|c|d|e|f|g|h|i|%s|k" % c for c in codes] if piped else codes,
            "Ctn": cartons, "Qty": cartons * 12, "Pcs": 0, "Inner_Carton": 12,
            "Inner_Pallet": cartons, "Weight_ref": weight_ref,
            "MFG_Date": time.strftime("%d/%m/%Y")})
    return {"Task_ID": "T-SIM-%05d" % n, "PO_ID": 100000 + n, "WH_Code": "WH01",
            "Line_ID": "LINE_01", "fromSystem": "SIMULATOR", "info_detail": detail}


@app.post("/sim/order")
def sim_order():
    b = request.get_json(silent=True) or {}
    order = make_order(int(b.get("pallets", 2)), int(b.get("cartons", 3)),
                       bool(b.get("piped", True)), int(b.get("weight_ref", 0)))
    status, resp = call(ORDER + "/ids/orderTask/", order)
    note("[SIM WMS] Gửi lệnh %s -> HTTP %s %s" % (order["Task_ID"], status, resp))
    return jsonify(ok=status == 200, status=status, resp=resp, order=order)


@app.post("/sim/cancel")
def sim_cancel():
    b = request.get_json(silent=True) or {}
    status, resp = call(ORDER + "/ids/cancelTask/", b)
    note("[SIM WMS] Gửi hủy %s -> HTTP %s %s" % (b, status, resp))
    return jsonify(ok=status == 200, status=status, resp=resp)


@app.post("/sim/raw")
def sim_raw():
    """Gửi một bản tin JSON tuỳ ý tới cổng nhận lệnh (thử lệnh thật chép từ http-*.log)."""
    b = request.get_json(silent=True) or {}
    status, resp = call(ORDER + str(b.get("path", "/ids/orderTask/")), b.get("body") or {})
    note("[SIM WMS] Gửi thô %s -> HTTP %s %s" % (b.get("path"), status, resp))
    return jsonify(ok=status == 200, status=status, resp=resp)


# ------------------------------------------------------------------ luồng nền
def heartbeat():
    """Báo cho phần mềm chính biết công cụ mô phỏng còn sống; thấy AUTO thì tự thoát."""
    while True:
        try:
            _, r = call(APP + "/api/sim/heartbeat", {}, timeout=2)
            S["app"], S["app_running"] = r.get("mode", "?"), bool(r.get("running"))
            if r.get("mode") == "AUTO":
                log.error("Phần mềm chính đang ở AUTO - công cụ mô phỏng tự thoát")
                os._exit(2)
        except Exception:
            S["app"] = "MẤT KẾT NỐI"
        time.sleep(1.0)


def auto_worker():
    """Công nhân ảo: đặt thùng khi trạm chờ, nhấc thùng khi có kết quả, bấm ĐỊNH DANH.
    HYBRID: cân là cân thật nên chỉ còn tự bấm ĐỊNH DANH."""
    placed_at = 0.0
    while True:
        time.sleep(0.25)
        if not S["auto"]:
            continue
        try:
            _, st = call(APP + "/api/state", timeout=2)
        except Exception:
            continue
        if not st.get("running"):
            continue
        msg = st.get("message", "")
        fake_scale = st.get("mode") != "HYBRID"      # HYBRID: cân thật, người đặt / nhấc thùng
        if fake_scale and S["weight"] == 0 and (msg.startswith("CHỜ ĐẶT")
                                                or msg.startswith("SẴN SÀNG")):
            if st.get("rows") and any(r["st"] == 0 for r in st["rows"]):
                S["weight"] = S["carton_weight"]
                placed_at = time.time()
                note("[AUTO] Đặt thùng %s g" % S["weight"])
        elif fake_scale and S["weight"] > 0 and time.time() - placed_at > 1.0 and (
                st.get("big") in ("OK", "NG") and not msg.startswith(("CÂN", "ĐANG IN", "ĐANG ĐỌC",
                                                                      "ĐỌC MÃ LỖI"))
                or msg.startswith(("VUI LÒNG", "ĐÃ HOÀN THÀNH", "PALLET"))):
            S["weight"] = 0
            note("[AUTO] Nhấc thùng ra")
        if S["auto_identify"] and st.get("can_identify") and msg.startswith("ĐÃ HOÀN THÀNH PALLET"):
            try:
                _, r = call(APP + "/api/identify", {}, timeout=15)
                note("[AUTO] Bấm ĐỊNH DANH -> %s" % r)
            except Exception as e:
                note("[AUTO] Bấm ĐỊNH DANH lỗi: %s" % e)
            time.sleep(1.0)


def main():
    logsetup.setup(config.path(cfg["log"]["dir"]), cfg["log"]["level"], cfg["log"]["keep_days"],
                   prefix="sim")
    try:
        _, r = call(APP + "/api/mode", timeout=3)
    except Exception as e:
        print("\n[!] KHÔNG KẾT NỐI ĐƯỢC PHẦN MỀM CHÍNH (%s): %s" % (APP, e))
        print("    Hãy chạy chay_dinh_danh.bat trước, chuyển sang MANUAL / HYBRID rồi mới chạy công cụ mô phỏng.")
        return 2
    if r.get("mode") not in ("MANUAL", "HYBRID"):
        print("\n[!] PHẦN MỀM CHÍNH ĐANG Ở CHẾ ĐỘ %s." % r.get("mode"))
        print("    Công cụ mô phỏng chỉ chạy được ở MANUAL / HYBRID: thẻ Cài đặt -> Chuyển chế độ.")
        log.error("Từ chối chạy: phần mềm chính đang ở %s", r.get("mode"))
        return 2
    host, port = cfg["simulator"]["host"], cfg["simulator"]["port"]
    try:
        srv = create_server(app, host=host, port=port, threads=12)
    except OSError as e:
        print("\n[!] Cổng %s đang bị chiếm (công cụ mô phỏng đã chạy sẵn?): %s" % (port, e))
        return 3
    threading.Thread(target=heartbeat, name="heartbeat", daemon=True).start()
    threading.Thread(target=auto_worker, name="auto", daemon=True).start()
    log.info("Công cụ mô phỏng chạy tại http://%s:%s (phần mềm chính: %s)", host, port, APP)
    if not os.environ.get("G8ID_NO_BROWSER"):
        try:
            os.startfile("http://127.0.0.1:%s/" % port)
        except OSError:
            pass
    try:
        srv.run()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
