"""Hai máy chủ HTTP:
  - Màn hình vận hành (mặc định 0.0.0.0:8600) cho Chrome.
  - Cổng nhận lệnh (mặc định 0.0.0.0:8500): /ids/orderTask/, /ids/cancelTask/, /ids/confirm_product/
    - giữ nguyên đường dẫn và mã phản hồi của WcsHttpServer bản cũ.
"""
import base64
import datetime
import html
import json
import logging
import os
import threading
import time

from flask import Flask, jsonify, request, send_from_directory
from waitress import create_server

from . import config, db, logsetup
from .engine import OrderError

log = logging.getLogger("web")
http_log = logging.getLogger("http.in")

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def build_ui(engine, on_quit):
    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False

    def authed():
        return request.headers.get("X-Pass", "") == str(config.get()["ui"]["password"])

    def guard(fn):
        def wrapper(*a, **kw):
            if not authed():
                return jsonify(ok=False, error="Sai mật khẩu"), 403
            try:
                return jsonify(ok=True, **(fn(*a, **kw) or {}))
            except OrderError as e:
                return jsonify(ok=False, error=str(e))
            except Exception as e:
                log.exception("Lỗi API %s", request.path)
                return jsonify(ok=False, error="Lỗi: %s" % e), 500
        wrapper.__name__ = fn.__name__
        return wrapper

    def body():
        return request.get_json(silent=True) or {}

    @app.after_request
    def no_cache(resp):
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(Exception)
    def on_error(e):
        code = getattr(e, "code", 500)
        if code == 500:
            log.exception("Lỗi web %s", request.path)
        return jsonify(ok=False, error=str(e)), code

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/guide")
    def guide():
        return send_from_directory(config.BASE_DIR, config.GUIDE_PDF)

    @app.get("/static/<path:name>")
    def static_file(name):
        return send_from_directory(STATIC, name)

    # ---- vận hành (không cần mật khẩu) ----
    @app.get("/api/state")
    def state():
        return jsonify(engine.snapshot())

    @app.post("/api/start")
    def start():
        return jsonify(engine.start(bool(body().get("confirm_no_light"))))

    @app.post("/api/stop")
    def stop():
        return jsonify(engine.stop())

    @app.post("/api/identify")
    def identify():
        return jsonify(engine.identify(str(body().get("pallet_id", "") or "").strip()))

    @app.post("/api/counter/reset")
    def counter_reset():
        engine.reset_counter()
        return jsonify(ok=True)

    @app.post("/api/order/answer")
    def order_answer():
        try:
            return jsonify(ok=True, message=engine.answer_order(bool(body().get("accept"))))
        except OrderError as e:
            return jsonify(ok=False, error=str(e))

    @app.post("/api/login")
    def login():
        return jsonify(ok=authed())

    @app.get("/api/info")
    def info():
        cfg = config.get()
        return jsonify(
            station=cfg["station_id"], desk_no=cfg.get("desk_no", 1), version=config.VERSION, mode=engine.mode,
            uptime_min=int((time.time() - engine.started_at) / 60),
            settings=engine.settings, devices=engine.dev.status(),
            device_cfg=cfg["devices"], order_port=cfg["order_server"]["port"],
            pallet_done_url=engine._pallet_done_url(), db=db.stats(engine.db),
            db_name=engine.db.name, queue=engine.queue(), rcs=engine.rcs,
            rcs_error=engine.rcs_error, log_dir=config.path(cfg["log"]["dir"]))

    @app.get("/api/logs/files")
    def log_files():
        return jsonify(files=logsetup.list_files())

    @app.get("/api/logs")
    def logs():
        name = request.args.get("file", "")
        if not name:
            return jsonify(lines=["%s [%s] [%s] %s" % (x["t"], x["lv"], x["tag"], x["msg"])
                                  for x in logsetup.recent])
        return jsonify(lines=logsetup.tail(name, 800, request.args.get("grep", "")))

    @app.get("/api/history")
    def history():
        fmt = "%Y-%m-%d"
        today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            d1 = datetime.datetime.strptime(request.args.get("from", ""), fmt)
        except ValueError:
            d1 = today
        try:
            d2 = datetime.datetime.strptime(request.args.get("to", ""), fmt)
        except ValueError:
            d2 = today
        return jsonify(rows=engine.history(d1, d2 + datetime.timedelta(days=1),
                                           request.args.get("q", "").strip()))

    @app.get("/api/history/parcels")
    def history_parcels():
        return jsonify(rows=engine.history_parcels(request.args.get("pallet", "")))

    # ---- thẻ Thông số (bố cục và nút như bản cũ) ----
    def day_range():
        fmt = "%Y-%m-%d"
        today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        out = []
        for k in ("from", "to"):
            try:
                out.append(datetime.datetime.strptime(request.args.get(k, ""), fmt))
            except ValueError:
                out.append(today)
        return out[0], out[1] + datetime.timedelta(days=1)

    @app.get("/api/orders")
    def orders():
        d1, d2 = day_range()
        return jsonify(ok=True, **engine.orders(d1, d2, request.args.get("pallet", "").strip(),
                                                request.args.get("po", "").strip()))

    @app.get("/api/orders/parcels")
    def order_parcels():
        try:
            return jsonify(ok=True, **engine.order_parcels(request.args.get("pallet", ""),
                                                           request.args.get("key", "")))
        except OrderError as e:
            return jsonify(ok=False, error=str(e))

    @app.post("/api/orders/pull_next")
    def pull_next():
        try:
            return jsonify(ok=True, pallet_id=engine.pull_next())
        except OrderError as e:
            return jsonify(ok=False, error=str(e))

    @app.post("/api/orders/fake_complete")
    @guard
    def fake_complete():
        return {"pallet_id": engine.fake_complete(body().get("pallet_id", ""))}

    @app.post("/api/orders/delete")
    @guard
    def delete_order():
        return {"cancelled": engine.delete_pallet(body().get("pallet_id", ""))}

    @app.get("/labels")
    def labels():
        """"In PDF mã hiện tại": trang tem 70x40 mm của pallet đang làm -> Chrome in / lưu PDF."""
        try:
            data = engine.label_sheet(request.args.get("pallet", ""))
        except OrderError as e:
            return "<meta charset=utf-8><h2>%s</h2>" % html.escape(str(e)), 404
        return label_page(data)

    # ---- công cụ mô phỏng ----
    @app.get("/api/mode")
    def mode():
        return jsonify(mode=engine.mode, running=engine.running)

    @app.post("/api/sim/heartbeat")
    def sim_heartbeat():
        if engine.manual:
            engine.sim_heartbeat = time.time()
        return jsonify(mode=engine.mode, running=engine.running)

    # ---- cài đặt (cần mật khẩu) ----
    @app.get("/api/settings")
    @guard
    def get_settings():
        cfg = config.get()
        return {"settings": engine.settings, "devices": cfg["devices"], "servers": cfg["servers"],
                "desk_no": cfg.get("desk_no", 1), "mode": engine.mode, "ports": _ports(),
                "port_notes": engine.port_notes}

    @app.get("/api/ports")
    @guard
    def get_ports():
        return {"ports": _ports()}

    @app.post("/api/settings")
    @guard
    def post_settings():
        engine.save_settings(body())

    @app.get("/api/mfg")
    @guard
    def get_mfg():
        return {"mfg": engine.mfg_info()}

    @app.post("/api/mfg")
    @guard
    def post_mfg():
        b = body()
        return {"mfg": engine.set_mfg(b.get("enabled"), b.get("date", ""))}

    @app.post("/api/mode")
    @guard
    def post_mode():
        engine.set_mode(body().get("mode"))
        return {"mode": engine.mode}

    @app.post("/api/devices")
    @guard
    def post_devices():
        b = body()
        patch = {}
        if isinstance(b.get("devices"), dict):
            patch["devices"] = b["devices"]
        if isinstance(b.get("servers"), dict):
            patch["servers"] = b["servers"]
        if "desk_no" in b:
            try:
                desk = int(b["desk_no"])
            except (TypeError, ValueError):
                desk = 0
            if not 1 <= desk <= 999:
                raise OrderError("Số thứ tự bàn định danh phải là số từ 1 đến 999.")
            patch["desk_no"] = desk
        if engine.running:
            raise OrderError("Hãy bấm Dừng trước khi sửa cấu hình thiết bị.")
        if "devices" in patch:
            merged = {k: dict(v, **patch["devices"].get(k, {}))
                      for k, v in config.get()["devices"].items()}
            why = config.com_conflict(merged)
            if why:
                raise OrderError(why + " Mỗi cổng COM chỉ gán cho một thiết bị.")
        config.save(patch)
        log.info("Đã lưu cấu hình thiết bị/server: %s", patch)
        engine.reconnect_devices()

    @app.post("/api/devices/test")
    @guard
    def test_device():
        b = body()
        return engine.test_device(b.get("device"), b.get("cfg") if isinstance(b.get("cfg"), dict) else {})

    @app.post("/api/print_manual")
    @guard
    def print_manual():
        engine.print_manual(str(body().get("text", "")).strip() or "TEST")

    @app.post("/api/reprint")
    @guard
    def reprint():
        return {"code": engine.reprint()}

    @app.post("/api/reprint_pallet")
    @guard
    def reprint_pallet():
        b = body()
        codes = b.get("codes") if isinstance(b.get("codes"), list) else None
        return engine.reprint_pallet(b.get("pallet_id", ""), codes)

    @app.post("/api/reload")
    @guard
    def reload_pallet():
        engine.reload_pallet(str(body().get("pallet_id", "")), str(body().get("key", "") or ""))

    @app.post("/api/cancel")
    @guard
    def cancel():
        if engine.running:
            raise OrderError("Hãy bấm Dừng trước khi hủy pallet.")
        return {"cancelled": engine.cancel_task({"Pallet_ID": body().get("pallet_id")},
                                                "MANUAL_CANCEL")}

    @app.post("/api/password")
    @guard
    def password():
        new = str(body().get("new", "")).strip()
        if len(new) < 4:
            raise OrderError("Mật khẩu mới phải có ít nhất 4 ký tự.")
        config.save({"ui": {"password": new}})
        log.warning("Đã đổi mật khẩu thẻ Cài đặt")

    @app.post("/api/quit")
    @guard
    def quit_app():
        log.warning("Yêu cầu thoát phần mềm từ giao diện")
        threading.Timer(0.5, on_quit).start()

    return app


def _ports():
    from .devices import portmap
    return portmap.list_ports()


LABEL_CSS = """
@page { size: 70mm 40mm; margin: 0; }
* { box-sizing: border-box; margin: 0; }
body { font-family: Arial, sans-serif; background: #ccc; }
.bar { padding: 8px; font: 14px Arial; background: #333; color: #fff; }
.bar button { font-size: 14px; padding: 6px 14px; margin-right: 8px; }
.tem { width: 70mm; height: 40mm; background: #fff; margin: 6px auto; padding: 1.2mm;
       display: grid; grid-template-columns: 36mm 1fr; grid-template-rows: 1fr 5mm;
       overflow: hidden; page-break-after: always; break-after: page; }
.l { font-size: 2.6mm; font-weight: 600; line-height: 1.25; overflow: hidden; }
.top { display: flex; align-items: center; gap: 2mm; height: 9mm; }
.logo { font-weight: 900; font-size: 4mm; color: #000; }
img.logo { width: 12.5mm; height: 6.9mm; image-rendering: pixelated; }
.seq { font-size: 8mm; font-weight: 900; }
.name { font-size: 3mm; font-weight: 700; line-height: 1.12; height: 10.1mm; overflow: hidden;
        margin: .4mm 0 .6mm; }
.r { text-align: center; }
.stamp { font-size: 2.3mm; font-weight: 600; }
.r svg { width: 28mm; height: 28mm; }
.code { grid-column: 1 / 3; font-size: 3.4mm; font-weight: 900; align-self: center; }
@media print { body { background: #fff; } .bar { display: none; } .tem { margin: 0; } }
"""


def code_style(text):
    """Khu 2 trang PDF: chữ thu nhỏ cho vừa 1 dòng như tem Godex. Chuỗi dài in đậm 700 vì đậm 900
    trên Chrome là Arial Black (rộng hơn ~13%)."""
    from .devices.printer_godex import text_em
    size = min(3.4, 67.4 / max(text_em(text), 1))
    return "font-size:%.2fmm" % size + ("" if size >= 3.4 else ";font-weight:700")


def logo_html():
    """Logo trên trang PDF: đúng ảnh máy in dùng (100x55 điểm = 12,5x6,9 mm); thiếu ảnh thì in chữ."""
    try:
        p = config.path(config.get()["devices"]["printer"].get("logo") or "drivers/G8_Label.bmp")
        with open(p, "rb") as f:
            return '<img class="logo" alt="G8HOME" src="data:image/bmp;base64,%s">' %                 base64.b64encode(f.read()).decode()
    except Exception:
        return '<span class="logo">G8HOME</span>'


def label_page(data):
    """Trang in tem của cả pallet, bố cục giống tem Godex (khu 1 giờ in, khu 2 nguyên phần tử Carton_List)."""
    try:
        import segno
    except ImportError:
        segno = None
    logo = logo_html()
    stamp = datetime.datetime.now().strftime("%Hh%Mp%Ss")
    e = html.escape
    out = []
    for r in data["rows"]:
        qr = segno.make(r["full"], error="l", micro=False).svg_inline(scale=1, border=0, omitsize=True) \
            if segno else "<b>(thiếu thư viện segno - chạy install.bat)</b>"
        out.append(
            '<div class="tem"><div class="l"><div class="top">%s'
            '<span class="seq">%s</span></div><div class="name">%s</div>'
            '<div>Quy cách : %s</div><div>Mã lệnh&nbsp; : %s</div><div>NSX&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; : %s</div></div>'
            '<div class="r"><div class="stamp">%s</div>%s</div>'
            '<div class="code" style="%s">%s</div></div>'
            % (logo, r["seq"], e(data["item"]), e(data.get("spec", "")), e(data["order"]),
               e(r["mfg_date"]), stamp, qr, code_style(r["full"]), e(r["full"])))
    return ('<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>Tem pallet %s</title>'
            '<style>%s</style></head><body><div class="bar">Pallet <b>%s</b> - %d tem. '
            '<button onclick="print()">In / Lưu PDF</button> Chọn máy in "Save as PDF" (Lưu dưới '
            'dạng PDF) để lưu file.</div>%s<script>setTimeout(print, 400)</script></body></html>'
            % (e(data["pallet_id"]), LABEL_CSS, e(data["pallet_id"]), len(out), "".join(out)))


def build_order_server(engine):
    """Cổng nhận lệnh. Mọi bản tin vào (đủ body) và phản hồi đều ghi vào http-*.log."""
    app = Flask("orders", static_folder=None)

    def reply(status, code, desc, raw):
        http_log.info("IN  %s %s từ %s body=%s -> %s {code:%s, desc:%s}", request.method,
                      request.path, request.remote_addr, raw, status, code, desc)
        resp = app.response_class(json.dumps({"code": code, "desc": desc}), status=status,
                                  mimetype="application/json")
        return resp

    def handle(action):
        raw = request.get_data(as_text=True) or ""
        if request.method != "POST":
            return reply(405, 1001, "Only POST is allowed", raw)
        if not raw.strip():
            return reply(400, 1001, "Empty body", raw)
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except ValueError:
            return reply(400, 1001, "Invalid JSON", raw)
        if engine.manual and request.remote_addr not in ("127.0.0.1", "::1"):
            # MANUAL/HYBRID dùng DB mô phỏng: không nuốt lệnh thật của WMS vào đó.
            return reply(503, 1001, "Station is in %s (simulation) mode" % engine.mode, raw)
        try:
            if action == "order":
                engine.receive_order(data, request.remote_addr)
            elif action == "cancel":
                engine.cancel_task(data)
            else:
                engine.confirm_product(data)
            return reply(200, 1000, "SUCCESS", raw)
        except OrderError as e:
            return reply(400, 1001, str(e), raw)
        except Exception:
            log.exception("HandleRequest error")
            return reply(500, 1001, "Server error", raw)

    methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
    for path, action in (("/ids/orderTask", "order"), ("/ids/cancelTask", "cancel"),
                         ("/ids/confirm_product", "confirm")):
        for p in (path, path + "/"):
            app.add_url_rule(p, endpoint=action + p, view_func=lambda a=action: handle(a),
                             methods=methods)
    return app


class Server:
    """waitress chạy trong luồng riêng, đóng được ngay khi thoát."""

    def __init__(self, app, host, port, name, threads=6):
        self.name, self.host, self.port = name, host, port
        self.srv = create_server(app, host=host, port=port, threads=threads, ident="g8id",
                                 clear_untrusted_proxy_headers=True)
        self.thread = threading.Thread(target=self.srv.run, name=name, daemon=True)

    def start(self):
        self.thread.start()
        log.info("HTTP server started: %s http://%s:%s", self.name, self.host, self.port)

    def stop(self):
        try:
            self.srv.close()
        except Exception:
            pass
