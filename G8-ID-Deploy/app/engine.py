"""Nghiệp vụ trạm định danh: nhận lệnh -> cân -> in tem -> đọc lại -> đèn tháp -> chốt pallet.

Quy trình và câu thông báo giữ theo TForm.cs (MainProcessBarcode) của bản WinForms.
Toàn bộ trạng thái nằm trong MongoDB nên tắt/mở máy không mất tiến độ.
Vòng lặp chạy trong một luồng riêng; mọi chỗ chờ đều ngắt được ngay khi bấm Dừng,
không dùng Thread.Abort và không chạm vào giao diện -> không còn treo khi dừng/đóng.
"""
import datetime
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid

from pymongo import ASCENDING

from . import config, db, devices, simguard

log = logging.getLogger("engine")
http_log = logging.getLogger("http.out")

ACTIVE = ("PROCESSING", "FINALIZING", "AWAIT_SEND")
# AUTO = sản xuất thật. MANUAL = mô phỏng toàn bộ. HYBRID = thiết bị thật tại bàn, chỉ mô phỏng
# hệ thống bên ngoài (WMS/WCS gửi lệnh, RCS nhận pallet) bằng công cụ mô phỏng.
MODES = ("AUTO", "MANUAL", "HYBRID")
STATUS_TEXT = {0: "Chờ in", 1: "Đã lên bảng kê", 2: "Đã lên bảng kê", 3: "Chờ in Palet",
               4: "Chờ gửi Palet", 5: "Hoàn tất Palet"}

GRAY, ORANGE, RED, GREEN, LIME, BLUE = "gray", "orange", "red", "green", "lime", "blue"
# Đầu đọc tự tắt tia sau thời gian quét của nó (scanner_timeout.bat) -> kích lại định kỳ để
# nghe liên tục tới khi có mã, như bản cũ (ReadBarcoder chờ tới khi có dữ liệu hoặc bấm Dừng).
BARCODE_RETRIGGER_MS = 60000


class Stopped(Exception):
    """Người vận hành bấm Dừng (hoặc phần mềm đang tắt)."""


class OrderError(Exception):
    pass


def field(d, *names, default=None):
    """Lấy trường không phân biệt hoa/thường, chấp nhận vài tên gọi khác nhau."""
    if not isinstance(d, dict):
        return default
    low = {str(k).lower(): v for k, v in d.items()}
    for n in names:
        v = low.get(n.lower())
        if v is not None:
            return v
    return default


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def fmt_date(v):
    """Ngày sản xuất in trên tem: dd/mm/yyyy. Lệnh gửi yyyy-mm-dd (có thể kèm giờ) thì đổi lại."""
    s = str(v or "").strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return "%s/%s/%s" % (s[8:10], s[5:7], s[:4])
    return s


def spec_text(p):
    """Quy cách in trên tem: "<số> chiec" theo Inner_Carton; lệnh không gửi thì Qty / Ctn."""
    p = p or {}
    n = to_int(p.get("inner_carton"))
    if n <= 0 and to_int(p.get("ctn")) > 0 and to_int(p.get("qty")) % to_int(p.get("ctn")) == 0:
        n = to_int(p.get("qty")) // to_int(p.get("ctn"))
    return "%d chiec" % n if n > 0 else ""


def parse_carton(raw):
    """Carton_List: có hơn 10 phần ngăn bởi '|' thì mã thùng là phần thứ 10, không thì nguyên chuỗi."""
    received = str(raw or "").strip()
    parts = received.split("|")
    code = parts[9].strip() if len(parts) > 10 else received
    return code or received, received


class Engine:
    def __init__(self):
        self.cfg = config.get()
        self.lock = threading.RLock()
        self._send_lock = threading.Lock()
        self.mode = self._load_mode()
        self.settings = self._load_settings()
        self.db = db.data_db(self.manual)
        self.port_notes = {}
        self._build_devices()
        self.running = False
        self._stop_evt = threading.Event()
        self._thread = None
        self.job = None          # việc in lại toàn bộ tem pallet đang chạy / vừa xong
        self._job_stop = threading.Event()
        self._job_thread = None
        self.message, self.msg_color = "", GRAY
        self.big, self.big_color = "STOP", BLUE
        self.light = "off"
        self.weight = 0
        self.current_code = ""
        self.cycle = ""
        self.rcs = None          # kết quả lần gửi server gần nhất
        self.rcs_error = ""
        self.wcs = False         # cổng nhận lệnh đang mở?
        self._need_zero = False
        self._dirty = True
        self._cache = {}
        self._last_send = {}
        self.sim_heartbeat = 0.0
        self._sim_seen = (0.0, False)
        self._testing = ""       # thiết bị đang được kiểm tra ở thẻ Cài đặt (driver tạm đóng)
        self.started_at = time.time()
        self._port_msg()

    # ------------------------------------------------------------------ cấu hình
    @property
    def manual(self):
        """MANUAL và HYBRID: DB mô phỏng, WCS/RCS là công cụ mô phỏng, không dùng cho sản xuất."""
        return self.mode in ("MANUAL", "HYBRID")

    @property
    def sim_devices(self):
        """Chỉ MANUAL dùng thiết bị giả; HYBRID chạy thiết bị thật tại bàn định danh."""
        return self.mode == "MANUAL"

    def _load_mode(self):
        try:
            with open(config.MODE_FILE, "r", encoding="utf-8") as f:
                m = json.load(f).get("mode", "AUTO")
                return m if m in MODES else "AUTO"
        except (OSError, ValueError):
            return "AUTO"

    def _save_mode(self):
        os.makedirs(config.DATA_DIR, exist_ok=True)
        tmp = config.MODE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"mode": self.mode, "at": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
        os.replace(tmp, config.MODE_FILE)

    def _load_settings(self):
        s = dict(config.SETTING_DEFAULTS)
        doc = db.settings_col().find_one({"_id": "operation"}) or {}
        s.update({k: v for k, v in doc.items() if k in s})
        return s

    def save_settings(self, patch):
        """Lưu được cả lúc đang chạy: lượt cân kế tiếp dùng thông số mới."""
        s = dict(self.settings)
        for k, v in patch.items():
            if k not in config.SETTING_DEFAULTS:
                continue
            d = config.SETTING_DEFAULTS[k]
            if isinstance(d, bool):
                s[k] = bool(v)
            elif isinstance(d, int):
                s[k] = to_int(v, d)
            elif isinstance(d, list):
                s[k] = [str(x).strip() for x in v][:6]
            else:
                s[k] = str(v)
        if s["scale_value"] <= 0 or s["scale_error"] < 0 or s["time_scale"] <= 0:
            raise OrderError("Khối lượng chuẩn / sai số / thời gian cân không hợp lệ.")
        if s["pallet_done_trigger"] not in ("button", "auto"):
            raise OrderError("pallet_done_trigger phải là button hoặc auto.")
        db.settings_col().replace_one({"_id": "operation"}, dict(s, _id="operation"), upsert=True)
        self.settings = s
        self._dirty = True
        log.info("Đã lưu cài đặt vận hành: %s", s)
        self.event("settings", **s)

    # ------------------------------------------------------------------ ngày sản xuất
    # Mặc định in ngày sản xuất (NSX) theo lệnh. Thẻ Cài đặt -> Cài đặt vận hành cho sửa tay
    # NSX của lệnh đang làm, chỉ khi lệnh đó chưa có thùng nào đạt; lệnh mới về lại theo lệnh.
    def _mfg_doc(self):
        return db.settings_col().find_one({"_id": "mfg_override"}) or {}

    def _mfg_for(self, p, doc=None):
        doc = self._mfg_doc() if doc is None else doc
        if doc.get("enabled") and p and doc.get("po_key") == p.get("po_key"):
            return doc.get("date", "")
        return fmt_date((p or {}).get("mfg_date"))

    def _order_started(self, po_key):
        """Lệnh đã có thùng đạt (đang làm hoặc pallet đã xong) -> không cho sửa NSX nữa."""
        d = self.db
        ids = [x["pallet_id"] for x in d.pallets.find({"po_key": po_key}, {"pallet_id": 1})]
        if ids and d.parcels.count_documents({"pallet_id": {"$in": ids}, "status": {"$gte": 1}},
                                             limit=1):
            return True
        return d.pallets_his.count_documents({"po_key": po_key, "carton_ok": {"$gt": 0}},
                                             limit=1) > 0

    def mfg_info(self):
        p = self._front_pallet()
        if p is None:
            return {"has_order": False}
        doc = self._mfg_doc()
        manual = bool(doc.get("enabled")) and doc.get("po_key") == p.get("po_key")
        return {"has_order": True, "po": p.get("po_name") or p.get("po_id"),
                "order_date": fmt_date(p.get("mfg_date")), "manual": manual,
                "date": doc.get("date", "") if manual else "",
                "effective": self._mfg_for(p, doc), "locked": self._order_started(p.get("po_key"))}

    def set_mfg(self, enabled, date):
        enabled = bool(enabled)
        date = fmt_date(date)
        with self.lock:
            p = self._front_pallet()
            if p is None:
                raise OrderError("Chưa có lệnh sản xuất. Ngày sản xuất chỉ sửa được cho lệnh đã về bàn.")
            if self.running:
                raise OrderError("Hãy bấm Dừng trước khi sửa ngày sản xuất.")
            if self._order_started(p.get("po_key")):
                raise OrderError("Lệnh %s đã định danh thùng / pallet: không sửa được ngày sản xuất "
                                 "nữa." % (p.get("po_name") or p.get("po_id")))
            if enabled:
                try:
                    time.strptime(date, "%d/%m/%Y")
                except ValueError:
                    raise OrderError("Ngày sản xuất không hợp lệ (dd/mm/yyyy).")
            doc = {"_id": "mfg_override", "enabled": enabled, "po_key": p.get("po_key"),
                   "date": date if enabled else "", "at": db.now()}
            db.settings_col().replace_one({"_id": "mfg_override"}, doc, upsert=True)
            self._dirty = True
        log.info("Ngày sản xuất lệnh %s: %s", p.get("po_key"),
                 "SỬA TAY " + date if enabled else "theo lệnh (%s)" % fmt_date(p.get("mfg_date")))
        self.event("mfg_date", po_key=p.get("po_key"), enabled=enabled, date=doc["date"])
        return self.mfg_info()

    # ------------------------------------------------------------------ tiện ích
    def event(self, kind, **data):
        try:
            self.db.event_log.insert_one({"at": db.now(), "type": kind, "cycle": self.cycle,
                                          "mode": self.mode, **data})
        except Exception:
            log.exception("Không ghi được event_log")

    def _build_devices(self):
        """Thiết bị thật: tự dò lại cổng COM (thiết bị bật Tự dò) trước khi mở cổng."""
        from .devices import portmap
        self.port_notes = {} if self.sim_devices else portmap.apply(self.cfg)
        self.dev = devices.build(self.cfg, self.sim_devices)
        self.dev.notes = self.port_notes

    PORT_MSG = "CHƯA TÌM THẤY CỔNG COM: "

    def _port_msg(self):
        if self.port_notes:
            names = ", ".join(config.DEVICE_NAMES[d].upper() for d in self.port_notes)
            self._msg(self.PORT_MSG + "%s - HÃY CHỌN CỔNG THỦ CÔNG Ở THẺ CÀI ĐẶT" % names, RED)
        elif self.message.startswith(self.PORT_MSG):
            self._msg("", GRAY)

    def _msg(self, text, color=GRAY):
        if text != self.message:
            log.info("[UI] %s", text)
        self.message, self.msg_color = text, color

    def _big(self, text, color):
        self.big, self.big_color = text, color

    def _light(self, color):
        if color != self.light:
            log.info("[LIGHT] %s -> %s", self.light, color)
        self.light = color
        try:
            self.dev.plc.set_light(color)
        except Exception:
            log.exception("Lỗi đặt đèn tháp (bỏ qua, không chặn sản xuất)")

    def _check(self):
        if self._stop_evt.is_set():
            raise Stopped()

    def _sleep(self, seconds):
        if self._stop_evt.wait(seconds):
            raise Stopped()

    # ------------------------------------------------------------------ nhận lệnh
    def receive_order(self, data, source=""):
        """IF-01. Trả về chuỗi mô tả; ném OrderError nếu lệnh không hợp lệ."""
        po_id = to_int(field(data, "PO_ID"), 0)
        if po_id <= 0:
            raise OrderError("order_id invalid")
        log.info("XỬ LÝ LỆNH SẢN XUẤT: PO_ID=%s Task_ID=%s (từ %s)", po_id,
                 field(data, "Task_ID"), source)
        if self.settings["confirm_new_order"]:
            self.db.inbox.replace_one({"_id": "pending"},
                                      {"_id": "pending", "at": db.now(), "data": data}, upsert=True)
            self._dirty = True
            self.event("order_offered", po_id=po_id)
            return "offered"
        return self._load_order(data)

    def answer_order(self, accept):
        with self.lock:
            doc = self.db.inbox.find_one_and_delete({"_id": "pending"})
            self._dirty = True
            if not doc:
                return "Không có lệnh chờ xác nhận."
            if not accept:
                log.info("Công nhân chọn No - bỏ lệnh PO_ID=%s", field(doc["data"], "PO_ID"))
                self.event("order_rejected", po_id=field(doc["data"], "PO_ID"))
                return "Đã bỏ qua lệnh."
            self._load_order(doc["data"])
            return "Đã tiếp nhận lệnh."

    def _load_order(self, data):
        detail = field(data, "info_detail", "InforDetail", "infor_detail") or []
        if not isinstance(detail, list) or not detail:
            raise OrderError("Lệnh sản xuất không có dữ liệu chi tiết.")
        po_id = to_int(field(data, "PO_ID"))
        common = {
            "task_id": str(field(data, "Task_ID", default="") or ""),
            "po_id": po_id,
            "po_name": str(field(data, "PO_Name", default="") or ""),
            "wh_code": str(field(data, "WH_Code", default="") or ""),
            "line_id": str(field(data, "Line_ID", "LineId", "LineProduction", default="LINE_01")
                           or "LINE_01"),
            "from_system": str(field(data, "fromSystem", "From_System", default="") or ""),
        }
        with self.lock:
            batch = uuid.uuid4().hex[:12]
            pallets, parcels, seen = [], [], set()
            for item in detail:
                pallet_id = str(field(item, "Pallet_ID", "PalletId", default="") or "").strip()
                if not pallet_id:
                    raise OrderError("Thiếu Pallet_ID trong info_detail")
                if self.db.pallets.find_one({"pallet_id": pallet_id}, {"_id": 1}):
                    log.warning("Pallet %s đã có trong danh sách - bỏ qua (lệnh gửi lặp)", pallet_id)
                    continue
                cartons = field(item, "Carton_List", "CartonList") or []
                if not cartons:
                    raise OrderError(f"Pallet {pallet_id} không có Carton_List")
                rows = []
                for n, raw in enumerate(cartons, 1):
                    code, received = parse_carton(raw)
                    if not code or code in seen:
                        raise OrderError(f"Mã thùng trống hoặc trùng trong lệnh: {code}")
                    seen.add(code)
                    rows.append({"batch": batch, "pallet_id": pallet_id, "seq": n,
                                 "parcel_code": code, "received_code": received, "status": 0,
                                 "fail": False, "print_count": 0, "weight": None,
                                 "created_at": db.now()})
                po_name = str(field(item, "PO_Name", default=common["po_name"]) or "")
                pallets.append(dict(
                    common, batch=batch, pallet_id=pallet_id, status="WAIT",
                    po_name=po_name, po_key=po_name or str(po_id),
                    location=str(field(item, "Location", default="") or "").strip(),
                    item_code=str(field(item, "Item_Code", "ItemCode", default="") or ""),
                    item_name=str(field(item, "Item_Name", default="") or ""),
                    ctn=to_int(field(item, "Ctn")), qty=to_int(field(item, "Qty")),
                    pcs=to_int(field(item, "Pcs")),
                    inner_carton=to_int(field(item, "Inner_Carton")),
                    inner_pallet=to_int(field(item, "Inner_Pallet")),
                    weight_ref=to_int(field(item, "Weight_ref", "WeightRef",
                                            default=field(data, "Weight_ref"))),
                    mfg_date=str(field(item, "MFG_Date", "MfgDate",
                                       default=field(data, "MFG_Date", default="")) or ""),
                    pallet_current=to_int(field(item, "Pallet_Current")),
                    carton_count=len(rows), created_at=db.now()))
                parcels.extend(rows)
            if not pallets:
                return "duplicate"
            dup = self.db.parcels.find_one({"parcel_code": {"$in": list(seen)}},
                                           {"parcel_code": 1})
            if dup:
                raise OrderError(f"Mã thùng {dup['parcel_code']} đang nằm trong lệnh khác")
            base = self.db.meta.find_one_and_update(
                {"_id": "pallet_seq"}, {"$inc": {"v": len(pallets)}}, upsert=True) or {"v": 0}
            for i, p in enumerate(pallets):
                p["seq"] = base.get("v", 0) + i + 1
            try:
                self.db.pallets.insert_many(pallets)
                self.db.parcels.insert_many(parcels)
            except Exception:
                # Không để lại lệnh nạp dở.
                self.db.parcels.delete_many({"batch": batch})
                self.db.pallets.delete_many({"batch": batch})
                raise
            self._dirty = True
        log.info("Đã nạp lệnh PO_ID=%s: %d pallet, %d thùng", po_id, len(pallets), len(parcels))
        self.event("order_loaded", po_id=po_id, task_id=common["task_id"],
                   pallets=[p["pallet_id"] for p in pallets], cartons=len(parcels))
        self._auto_start()
        return "loaded"

    def _auto_start(self):
        """Lệnh mới về bàn mà trạm đang STOP -> tự Bắt đầu, khỏi chờ công nhân bấm.

        Đèn tháp lỗi thì vẫn chạy (không có ai trả lời câu hỏi; PLC không chặn sản xuất).
        Thiết bị khác lỗi thì không chạy, báo đỏ lý do để công nhân xử lý rồi bấm Bắt đầu.
        """
        if not self.settings.get("auto_start_on_order") or self.running:
            return
        try:
            r = self.start(confirm_no_light=True)
        except Exception:
            log.exception("Tự bắt đầu khi có lệnh mới lỗi")
            return
        if r.get("ok"):
            log.info("Có lệnh mới -> tự Bắt đầu")
            self.event("auto_start")
        else:
            log.warning("Có lệnh mới nhưng không tự Bắt đầu được: %s", r.get("error"))
            self._msg("ĐÃ NHẬN LỆNH MỚI - CHƯA TỰ BẮT ĐẦU ĐƯỢC: %s" % r.get("error"), RED)

    def cancel_task(self, data, reason="CANCEL"):
        """IF /ids/cancelTask/: hủy theo Task_ID / PO_ID / Pallet_ID (nhận trường nào dùng trường đó)."""
        q = []
        pid = field(data, "palletID", "Pallet_ID", "PalletId")
        if pid:
            q.append({"pallet_id": str(pid).strip()})
        tid = field(data, "Task_ID")
        if tid and not pid:
            q.append({"task_id": str(tid)})
        po = to_int(field(data, "PO_ID"))
        if po and not pid and not tid:
            q.append({"po_id": po})
        if not q:
            raise OrderError("Task_ID invalid")            # câu trả lời của bản cũ
        with self.lock:
            ids = [p["pallet_id"] for p in self.db.pallets.find({"$or": q}, {"pallet_id": 1})]
            for pallet_id in ids:
                self._archive(pallet_id, "CANCEL", reason)
        log.warning("XỬ LÝ HỦY LỆNH SẢN XUẤT: %s -> %d pallet bị hủy: %s", data, len(ids), ids)
        if ids and reason == "CANCEL":
            self._msg("HỦY LỆNH SẢN XUẤT-WMS YÊU CẦU", RED)
        self.event("cancel", request=data, pallets=ids)
        return ids

    def confirm_product(self, data):
        """IF /ids/confirm_product/: WMS báo kết quả định danh pallet.

        Dựng theo chuỗi còn lại trong VTP_Induction.exe (không có mã nguồn): kiểm tra PO_ID,
        Line_ID, Pallet_ID; Status = "true" -> "ĐÃ HOÀN THÀNH PALLET: ...", ngược lại báo
        "Lỗi từ WMS: <Message>".
        """
        if to_int(field(data, "PO_ID")) <= 0:
            raise OrderError("PO_ID invalid")
        pid = str(field(data, "Pallet_ID", "palletID", "PalletId", default="") or "").strip()
        if not pid or not str(field(data, "Line_ID", "LineId", default="") or "").strip():
            raise OrderError("Line_ID or Pallet_ID invalid")
        ok = str(field(data, "Status", default="")).strip().lower() == "true"
        text = str(field(data, "Message", default="") or "")
        log.info("confirm_product: Pallet_ID=%s, Location=%s, Status=%s, Message=%s", pid,
                 field(data, "Location"), field(data, "Status"), text)
        matched = False
        if ok:
            with self.lock:
                matched = self.db.pallets.find_one({"pallet_id": pid, "status": "AWAIT_SEND"},
                                                   {"_id": 1}) is not None
                if matched:
                    self._archive(pid, "DONE", "CONFIRM_PRODUCT")
            self._msg("ĐÃ HOÀN THÀNH PALLET: " + pid, GREEN)
        else:
            log.error("LỖI GỬI ĐỊNH DANH VỀ WMS: pallet %s - Lỗi từ WMS: %s", pid, text)
            self._msg("LỖI GỬI ĐỊNH DANH VỀ WMS: Lỗi từ WMS: %s (%s)" % (text, pid), RED)
        self.event("confirm_product", request=data, ok=ok, matched=matched)
        return matched

    # ------------------------------------------------------------------ dữ liệu
    def _front_pallet(self):
        """Pallet đang hiện ở Trang chủ: đang làm, không có thì pallet chờ đầu tiên."""
        d = self.db
        return d.pallets.find_one({"status": {"$in": ACTIVE}}, sort=[("seq", ASCENDING)]) or \
            d.pallets.find_one({"status": "WAIT"}, sort=[("seq", ASCENDING)])

    def _current_pallet(self):
        with self.lock:
            p = self.db.pallets.find_one({"status": {"$in": ACTIVE}}, sort=[("seq", ASCENDING)])
            if p is None:
                p = self.db.pallets.find_one_and_update(
                    {"status": "WAIT"}, {"$set": {"status": "PROCESSING", "started_at": db.now()}},
                    sort=[("seq", ASCENDING)], return_document=True)
                if p is not None:
                    log.info("Bắt đầu pallet %s (vị trí %s, %d thùng)", p["pallet_id"],
                             p.get("location"), p.get("carton_count", 0))
                    self._dirty = True
            return p

    def _archive(self, pallet_id, status, reason):
        """Chuyển pallet + thùng sang lịch sử (thay cho trigger SQL của bản cũ). Gọi lặp vẫn đúng."""
        with self.lock:
            p = self.db.pallets.find_one({"pallet_id": pallet_id})
            if p is None:
                return
            done_at = db.now()
            rows = list(self.db.parcels.find({"pallet_id": pallet_id}))
            ok = sum(1 for r in rows if r["status"] >= 1)
            for r in rows:
                if status == "DONE" and r["status"] >= 1:
                    r["status"] = 5
                r.update(done_at=done_at, done_reason=reason)
                self.db.parcels_his.replace_one({"_id": r["_id"]}, r, upsert=True)
            p.update(status=status, done_at=done_at, done_reason=reason, carton_ok=ok)
            self.db.pallets_his.replace_one({"_id": p["_id"]}, p, upsert=True)
            self.db.parcels.delete_many({"pallet_id": pallet_id})
            self.db.pallets.delete_one({"_id": p["_id"]})
            self._dirty = True
        log.info("Pallet %s -> lịch sử (%s / %s, %d/%d thùng đạt)", pallet_id, status, reason,
                 ok, len(rows))

    def _count(self, ok):
        day = time.strftime("%Y-%m-%d")
        inc = {"total": 1, "pass" if ok else "fail": 1}
        self.db.counters.update_one({"_id": day}, {"$inc": inc}, upsert=True)
        self._dirty = True

    def reset_counter(self):
        self.db.counters.replace_one({"_id": time.strftime("%Y-%m-%d")},
                                     {"total": 0, "pass": 0, "fail": 0}, upsert=True)
        self._dirty = True
        log.info("Đặt lại bộ đếm Đạt/Sai")
        self.event("counter_reset")

    # ------------------------------------------------------------------ điều khiển
    def start(self, confirm_no_light=False):
        """Bấm Bắt đầu. Kiểm tra theo đúng thứ tự của bản cũ."""
        with self.lock:
            log.info("Click START button")
            if self.running:
                return {"ok": True}
            if self._job_active():
                return {"ok": False, "title": "THÔNG BÁO",
                        "error": "ĐANG IN LẠI TEM PALLET. CHỜ IN XONG HOẶC BẤM DỪNG ĐỂ HỦY."}
            if self._testing:
                return {"ok": False, "title": "THÔNG BÁO",
                        "error": "ĐANG KIỂM TRA %s Ở THẺ CÀI ĐẶT. CHỜ KIỂM TRA XONG."
                                 % config.DEVICE_NAMES[self._testing].upper()}
            d = self.dev
            if not self.manual:
                why = simguard.simulator_running(self)
                if why:
                    return {"ok": False, "title": "CHẾ ĐỘ AUTO",
                            "error": "CÔNG CỤ MÔ PHỎNG CHƯA ĐÓNG (%s). HÃY ĐÓNG CỬA SỔ "
                                     "chay_mo_phong.bat RỒI BẮT ĐẦU LẠI!" % why}
            if not d.printer.connected:
                return {"ok": False, "title": "LỖI KẾT NỐI!!!", "error": "KIỂM TRA LẠI KẾT NỐI MÁY IN!!"}
            if not d.barcode.connected:
                return {"ok": False, "title": "LỖI KẾT NỐI!!!", "error": "KIỂM TRA LẠI KẾT NỐI PDA!!"}
            if not d.plc.connected and not confirm_no_light:
                return {"ok": False, "title": "CẢNH BÁO",
                        "confirm": "KẾT NỐI ĐÈN LỖI. TIẾP TỤC HAY KHÔNG?"}
            if not d.scale.connected:
                return {"ok": False, "title": "LỖI KẾT NỐI!!!",
                        "error": "KIỂM TRA LẠI KẾT NỐI TỚI CÂN!!"}
            if self.db.pallets.count_documents({}, limit=1) == 0:
                return {"ok": False, "title": "THÔNG BÁO",
                        "error": "KHÔNG CÓ LỆNH SẢN XUẤT. CHỜ PHẢN HỒI HỆ THỐNG!"}
            if self._thread is not None and self._thread.is_alive():
                return {"ok": False, "title": "THÔNG BÁO", "error": "Hệ thống đang dừng, thử lại sau 1 giây."}
            self._stop_evt.clear()
            self.running = True
            self._big("RUN", ORANGE)
            self._thread = threading.Thread(target=self._run, name="engine", daemon=True)
            self._thread.start()
            log.info("[SYSTEM] System is Working")
            self.event("start")
            return {"ok": True}

    def stop(self, wait=True):
        log.info("Click STOP button")
        self._stop_evt.set()
        self._job_stop.set()
        t = self._thread
        if wait and t is not None and t is not threading.current_thread():
            t.join(timeout=8)
            if t.is_alive():
                log.error("Luồng xử lý chưa dừng sau 8 s (đang kẹt ở thiết bị?)")
        j = self._job_thread
        if wait and j is not None and j is not threading.current_thread():
            j.join(timeout=5)
        return {"ok": True}

    def shutdown(self):
        """Tắt phần mềm: dừng vòng lặp, tắt đèn, đóng sạch mọi cổng (sửa lỗi kẹt CH340 bản cũ)."""
        log.info("Đang tắt: dừng xử lý và đóng thiết bị...")
        self.stop()
        self.dev.stop()
        log.info("Đã đóng toàn bộ thiết bị")

    def set_mode(self, mode):
        mode = str(mode).upper()
        if mode not in MODES:
            raise OrderError("Chế độ không hợp lệ")
        with self.lock:
            if mode == self.mode:
                return
            if self.running:
                raise OrderError("Hãy bấm Dừng trước khi đổi chế độ.")
            self._no_job()
            if mode == "AUTO":
                why = simguard.simulator_running(self)
                if why:
                    raise OrderError("CÔNG CỤ MÔ PHỎNG CHƯA ĐÓNG (%s). Hãy đóng cửa sổ "
                                     "chay_mo_phong.bat rồi chuyển AUTO lại." % why)
            log.warning("ĐỔI CHẾ ĐỘ %s -> %s", self.mode, mode)
            self.dev.stop()
            self.mode = mode
            self._save_mode()
            self.db = db.data_db(self.manual)
            self._build_devices()
            self.dev.start()
            self.light, self.weight, self._need_zero = "off", 0, False
            self.rcs, self.rcs_error = None, ""
            self._msg("ĐÃ CHUYỂN CHẾ ĐỘ " + mode, GRAY)
            self._port_msg()
            self._dirty = True
            self.event("mode", mode=mode)

    def reconnect_devices(self):
        if self.running:
            raise OrderError("Hãy bấm Dừng trước khi kết nối lại thiết bị.")
        if self._testing:
            raise OrderError("Đang kiểm tra thiết bị, chờ xong rồi lưu lại.")
        self._no_job()
        with self.lock:
            log.info("Kết nối lại toàn bộ thiết bị theo cấu hình mới")
            self.dev.stop()
            self.cfg = config.get()
            self._build_devices()
            self._port_msg()
            self.dev.start()

    def test_device(self, name, dcfg):
        """Kiểm tra một thiết bị thật với cấu hình đang chọn ở thẻ Cài đặt (chưa lưu).

        Driver đang giữ cùng cổng (kể cả chính thiết bị đó) được tạm đóng rồi mở lại sau.
        """
        from .devices import probe
        if name not in probe.TESTS:
            raise OrderError("Không có thiết bị " + str(name))
        if self.running:
            raise OrderError("Hãy bấm Dừng trước khi kiểm tra thiết bị.")
        self._no_job()
        # Chỉ giữ khoá lúc đóng/mở driver: thử thiết bị mất vài giây, không chặn lệnh WMS đến.
        with self.lock:
            if self.running or self._testing:
                raise OrderError("Đang chạy hoặc đang kiểm tra thiết bị khác.")
            self._testing = name
            cfg = dict(self.cfg["devices"][name], **(dcfg or {}))
            target = config.com_ports({**self.cfg["devices"], name: cfg}).get(name)
            live = config.com_ports(self.cfg["devices"])
            dev = self.dev
            hold = [d for d in probe.TESTS if d == name or (target and live.get(d) == target)]
            for d in hold:
                getattr(dev, d).stop()
        try:
            ok, text = probe.TESTS[name](cfg)
        finally:
            with self.lock:
                for d in hold:
                    getattr(dev, d).start()
                self._testing = ""
        log.info("Kiểm tra %s %s: %s", name, target or "", text)
        return {"pass": ok, "text": text}

    # ------------------------------------------------------------------ vòng lặp chính
    def _run(self):
        try:
            self._light("yellow")
            while True:
                self._check()
                p = self._current_pallet()
                if p is None:
                    self._msg("ĐÃ HOÀN TẤT LỆNH SẢN XUẤT", GREEN)
                    self._light("green")
                    log.info("Hết pallet - trạm tự STOP")
                    self.event("all_done")
                    break
                if p["status"] in ("FINALIZING", "AWAIT_SEND"):
                    self._close_pallet(p)
                else:
                    self._carton_cycle(p)
        except Stopped:
            self._light("off")
            self.weight = 0
        except Exception as e:
            log.exception("MainProcess lỗi hệ thống")
            self._msg("LỖI HỆ THỐNG: %s" % e, RED)
            self._light("red")
            self.event("system_error", error=str(e))
        finally:
            self.running = False
            self.current_code = ""
            self._big("STOP", BLUE)
            self._dirty = True
            log.info("[SYSTEM] System is STOP")

    def _read_weight(self):
        w = self.dev.scale.read()
        if w is None:
            self.weight = None
            self._msg("MẤT TÍN HIỆU CÂN - KIỂM TRA KẾT NỐI CÂN", RED)
            self._light("red")
            self._sleep(0.3)
            return None
        self.weight = w
        return w

    def _carton_cycle(self, p):
        s = self.settings
        if self._need_zero:
            self._wait_zero()
        w = self._read_weight()
        if w is None:
            return
        if w < s["zero_threshold_g"]:
            self._msg("CHỜ ĐẶT SẢN PHẨM LÊN CÂN", GRAY)
            self._big("RUN", ORANGE)
            self._light("yellow")
            self._sleep(0.1)
            return

        pallet_id = p["pallet_id"]
        parcel = self.db.parcels.find_one({"pallet_id": pallet_id, "status": 0},
                                          sort=[("seq", ASCENDING)])
        if parcel is None:
            if self.db.parcels.count_documents({"pallet_id": pallet_id}, limit=1):
                self._begin_close(pallet_id)       # mọi thùng đã đạt (khôi phục sau mất điện)
            else:
                self._msg("HẾT DANH SÁCH IN / CHƯA CÓ THÙNG CHỜ IN", GRAY)
                self._sleep(0.5)
            return

        code = parcel["parcel_code"]
        self.cycle = uuid.uuid4().hex[:8]
        self.current_code = code
        tag = "[%s po=%s pallet=%s thung=%s]" % (self.cycle, p.get("po_id"), pallet_id, code)
        std = p.get("weight_ref") or s["scale_value"]
        log.info("%s Bắt đầu lượt: chuẩn %s ± %s g", tag, std, s["scale_error"])

        # 1) Cân
        self._msg("CÂN SẢN PHẨM...", ORANGE)
        ok, final = self._stable_weight(std, s["scale_error"], s["time_scale"])
        if final is None:
            log.warning("%s Mất tín hiệu cân giữa lượt - không tính NG", tag)
            return
        log.info("%s [SCALE] %s g -> %s", tag, final, "ĐẠT" if ok else "KHÔNG ĐẠT")
        if not ok:
            self._ng(tag, parcel, "weight", "SẢN PHẨM KHÔNG ĐẠT, VUI LÒNG BỎ RA KHỎI CÂN",
                     weight=final, mark=False)
            return
        self._big("OK", LIME)
        self._sleep(0.5)

        # 2) In tem thùng
        self._msg("ĐANG IN TEM...", ORANGE)
        t0 = time.time()
        mfg = self._mfg_for(p)
        printed = self.dev.printer.print_carton(
            code, p.get("item_name") or p.get("item_code", ""), pallet_id,
            p.get("wh_code", ""), mfg, seq=parcel.get("seq"),
            received_code=parcel.get("received_code", ""), spec=spec_text(p))
        self.db.parcels.update_one({"_id": parcel["_id"]},
                                   {"$inc": {"print_count": 1}, "$set": {"mfg_date": mfg}})
        log.info("%s [PRINTER] in tem thùng: %s (%d ms), lần in thứ %d", tag,
                 "OK" if printed else "LỖI", (time.time() - t0) * 1000,
                 parcel.get("print_count", 0) + 1)
        if not printed:
            self._ng(tag, parcel, "print", "IN TEM THẤT BẠI, VUI LÒNG BỎ RA KHỎI CÂN", weight=final)
            return
        self._sleep(1.5)

        # 3) Đọc lại mã vừa in (như bản cũ): chờ tới khi đầu đọc trả mã; mã sai thì đọc lần 2.
        #    QR chứa nguyên phần tử Carton_List -> tách mã định danh (phần thứ 10) rồi mới so.
        read = got = ""
        for i, text in ((1, "ĐANG ĐỌC MÃ VẠCH..."), (2, "ĐỌC MÃ LỖI - ĐANG THỬ ĐỌC LẠI LẦN 2...")):
            t0 = time.time()
            read = self._read_code(text)
            got = parse_carton(read)[0]
            log.info("%s [BARCODE] lần %d: mong đợi '%s', nhận '%s' (mã định danh '%s') sau %d ms -> %s",
                     tag, i, code, read, got, (time.time() - t0) * 1000,
                     "KHỚP" if got == code else "SAI")
            if got == code:
                break
            self._sleep(0.3)
        if got != code:
            self._ng(tag, parcel, "barcode", "KHÔNG ĐỌC ĐƯỢC MÃ VẠCH - BỎ RA KHỎI CÂN",
                     weight=final, read=read)
            return

        # 4) Đạt
        self.db.parcels.update_one({"_id": parcel["_id"]}, {"$set": {
            "status": 1, "fail": False, "weight": final, "done_at": db.now()}})
        self._count(True)
        self.current_code = ""            # dòng xanh nhảy sang thùng "Chờ in" kế tiếp
        self._big("OK", LIME)
        self._msg("MÃ VẠCH:" + got, LIME)
        self._light("green")
        self._need_zero = True
        log.info("%s [PROCESS] ĐÃ HOÀN THÀNH IN THÙNG %s", tag, code)
        self.event("carton_ok", po_id=p.get("po_id"), pallet_id=pallet_id, parcel=code, weight=final)

        if not self.db.parcels.count_documents({"pallet_id": pallet_id, "status": 0}, limit=1):
            self._begin_close(pallet_id)
            self._close_pallet(self.db.pallets.find_one({"pallet_id": pallet_id}))
        self._sleep(0.3)

    def _read_code(self, text):
        """Nghe đầu đọc tới khi có mã. Không có giới hạn thời gian: công nhân bấm Dừng để thoát."""
        while True:
            if self.dev.barcode.connected:
                self._msg(text, ORANGE)
                read = self.dev.barcode.read(BARCODE_RETRIGGER_MS, self._stop_evt)
                if read:
                    return read
                self._check()
            else:
                self._msg("MẤT KẾT NỐI ĐẦU ĐỌC - KIỂM TRA CÁP PDA", RED)
                self._sleep(1.0)

    def _ng(self, tag, parcel, why, text, weight=None, read=None, mark=True):
        """Thùng không đạt: đèn đỏ, đếm Sai. In/đọc lỗi thì giữ mã để in lại ở lượt sau."""
        if mark:
            self.db.parcels.update_one({"_id": parcel["_id"]}, {"$set": {"fail": True}})
        self._count(False)
        self._big("NG", RED)
        self._msg(text, RED)
        self._light("red")
        self._need_zero = True
        log.warning("%s NG (%s): %s", tag, why, text)
        self.event("carton_ng", reason=why, parcel=parcel["parcel_code"],
                   pallet_id=parcel["pallet_id"], weight=weight, read=read)

    def _stable_weight(self, standard, allowed, duration_s, interval=0.2):
        """Như IsStableWeight: 2 lần đọc liên tiếp lệch <= jitter là ổn định; đủ thời gian thì so chuẩn."""
        required = max(1, int(duration_s * 1000 / (interval * 1000)))
        stable, previous, final, lost = 0, None, 0, 0
        for _ in range(required * 10):
            self._check()
            w = self.dev.scale.read()
            if w is None:
                lost += 1
                if lost * interval > 3:
                    self._read_weight()
                    return False, None
                self._sleep(interval)
                continue
            lost = 0
            self.weight = w
            if previous is not None and abs(previous - w) <= self.settings["stable_jitter_g"]:
                stable += 1
            else:
                stable = 1
            previous = final = w
            if stable >= required:
                return abs(final - standard) <= allowed, final
            self._sleep(interval)
        return False, final

    def _wait_zero(self):
        """Như WaitForZeroWeight: cân < ngưỡng đủ 5 lần liên tiếp mới nhận thùng kế. Giữ lý do NG."""
        count, t0, keep = 0, time.time(), (self.message, self.msg_color)
        while True:
            self._check()
            w = self.dev.scale.read()
            if w is None:
                self.weight = None
                self._msg("MẤT TÍN HIỆU CÂN - KIỂM TRA KẾT NỐI CÂN", RED)
                count = 0
            else:
                self.weight = w
                if w < self.settings["zero_threshold_g"]:
                    count += 1
                    if count >= 5:
                        break
                else:
                    count = 0
                    if self.big != "NG" and time.time() - t0 > 6:
                        self._msg("VUI LÒNG LẤY HÀNG RA KHỎI CÂN", RED)
                    else:
                        self._msg(*keep)
            self._sleep(0.1)
        self._need_zero = False
        self._msg("SẴN SÀNG CHO SẢN PHẨM MỚI", GREEN)

    # ------------------------------------------------------------------ chốt pallet
    def _begin_close(self, pallet_id):
        self.db.pallets.update_one({"pallet_id": pallet_id, "status": "PROCESSING"},
                                   {"$set": {"status": "FINALIZING"}})
        self._dirty = True
        self.current_code = ""
        log.info("Pallet %s đủ thùng -> chốt pallet", pallet_id)

    def _close_pallet(self, p):
        if p is None:
            return
        s, pid = self.settings, p["pallet_id"]
        if p["status"] == "FINALIZING":
            # Như bản cũ: đủ thùng là chốt pallet và chờ ĐỊNH DANH, không in tem pallet.
            with self.lock:
                self.db.parcels.update_many({"pallet_id": pid, "status": {"$gte": 1}},
                                            {"$set": {"status": 4}})
                self.db.pallets.update_one({"pallet_id": pid, "status": "FINALIZING"},
                                           {"$set": {"status": "AWAIT_SEND", "closed_at": db.now()}})
                self._dirty = True
            self.event("pallet_closed", pallet_id=pid)

        # Chờ gửi về server
        while True:
            self._check()
            cur = self.db.pallets.find_one({"pallet_id": pid})
            if cur is None:
                break                                  # đã gửi xong / bị hủy
            auto = s["pallet_done_trigger"] == "auto" or cur.get("identify_requested")
            if not auto:
                self._msg("ĐÃ HOÀN THÀNH PALLET - HÃY BẤM NÚT ĐỊNH DANH", GREEN)
                self._light("green")
            elif time.time() - self._last_send.get(pid, 0) >= self.cfg["servers"]["retry_s"]:
                ok, err = self.send_pallet_done(pid)
                if ok:
                    break
                self._msg("ĐANG CHỜ GỬI PALLET VỀ SERVER: " + pid, RED)
                self._light("red")
            self._sleep(0.2)
        self._msg("PALLET OK – TIẾP TỤC SẢN XUẤT", GREEN)
        self._light("green")
        self._big("RUN", ORANGE)
        self._sleep(1.0)

    def identify(self, pallet_id=""):
        """Nút ĐỊNH DANH: gửi pallet đã chốt về server (dùng được cả khi đang STOP).

        pallet_id: pallet chọn ở thẻ Thông số ("Gửi định danh"); trống = pallet chờ đầu tiên.
        """
        if pallet_id:
            p = self.db.pallets.find_one({"pallet_id": pallet_id})
            if p is None:
                return {"ok": False, "error": "Không tìm thấy pallet %s." % pallet_id}
            if p["status"] != "AWAIT_SEND":
                return {"ok": False, "title": "CHƯA ĐỦ SỐ LƯỢNG HÀNG!",
                        "error": "Chưa quét đủ số thùng, không thể gửi thành công pallet!"}
        else:
            p = self.db.pallets.find_one({"status": "AWAIT_SEND"}, sort=[("seq", ASCENDING)])
        if p is None:
            return {"ok": False, "error": "Chưa có pallet nào chờ định danh."}
        ok, err = self.send_pallet_done(p["pallet_id"])
        if ok:
            if not self.running:
                self._msg("PALLET OK – TIẾP TỤC SẢN XUẤT", GREEN)
            return {"ok": True}
        # Đã bấm rồi thì vòng lặp tự gửi lại mỗi retry_s cho tới khi server nhận.
        self.db.pallets.update_one({"_id": p["_id"]}, {"$set": {"identify_requested": True}})
        return {"ok": False, "error": "GỬI PALLET LỖI: %s\nMáy sẽ tự gửi lại mỗi %s giây." %
                                      (err, self.cfg["servers"]["retry_s"])}

    def send_pallet_done(self, pallet_id):
        with self._send_lock:
            p = self.db.pallets.find_one({"pallet_id": pallet_id, "status": "AWAIT_SEND"})
            if p is None:
                return True, ""
            self._last_send[pallet_id] = time.time()
            body = {"Task_ID": p.get("task_id", ""), "PO_ID": p.get("po_id", 0),
                    "WH_Code": p.get("wh_code", ""), "Line_ID": p.get("line_id", ""),
                    "palletID": pallet_id,
                    "Ctn": self.db.parcels.count_documents({"pallet_id": pallet_id,
                                                            "status": {"$gte": 1}})}
            ok, err = self._post(self._pallet_done_url(), body)
            self.rcs, self.rcs_error = ok, err
            self.db.pallets.update_one({"_id": p["_id"]}, {
                "$inc": {"send_attempts": 1}, "$set": {"send_error": err, "send_at": db.now()}})
            if not ok:
                log.error("GỬI PALLET LỖI: %s (%s)", pallet_id, err)
                self._dirty = True
                return False, err
            self._archive(pallet_id, "DONE", "NORMAL")
            self._last_send.pop(pallet_id, None)
            self.event("pallet_done", pallet_id=pallet_id, body=body)
            return True, ""

    def _pallet_done_url(self):
        if self.manual:
            return "http://127.0.0.1:%s/identify-service/ids/pallet_identify_done" % \
                   self.cfg["simulator"]["port"]
        return self.cfg["servers"]["pallet_done_url"]

    def _post(self, url, body):
        """POST JSON, coi HTTP 2xx là thành công. Mọi bản tin ra đều ghi đủ vào http-*.log."""
        payload = json.dumps(body, ensure_ascii=False)
        t0 = time.time()
        try:
            req = urllib.request.Request(url, data=payload.encode("utf-8"), method="POST",
                                         headers={"Content-Type": "application/json; charset=utf-8"})
            with urllib.request.urlopen(req, timeout=self.cfg["servers"]["timeout_s"]) as r:
                text = r.read(4000).decode("utf-8", "replace")
                http_log.info("OUT POST %s body=%s -> %s %s (%d ms)", url, payload, r.status, text,
                              (time.time() - t0) * 1000)
                return 200 <= r.status < 300, "" if 200 <= r.status < 300 else "HTTP %s" % r.status
        except urllib.error.HTTPError as e:
            text = e.read(2000).decode("utf-8", "replace")
            http_log.error("OUT POST %s body=%s -> %s %s (%d ms)", url, payload, e.code, text,
                           (time.time() - t0) * 1000)
            return False, "%s %s" % (e.code, e.reason)
        except Exception as e:
            http_log.error("OUT POST %s body=%s -> LỖI %s (%d ms)", url, payload, e,
                           (time.time() - t0) * 1000)
            return False, str(getattr(e, "reason", e))

    # ------------------------------------------------------------------ thao tác tay
    def reprint(self):
        """In lại tem của thùng đạt gần nhất trong pallet đang làm (nút In lại tem)."""
        if self.running:
            raise OrderError("Hãy bấm Dừng trước khi in lại tem.")
        self._no_job()
        r = self.db.parcels.find_one({"status": {"$gte": 1}}, sort=[("done_at", -1)])
        if r is None:
            raise OrderError("Chưa có thùng nào đã in.")
        p = self.db.pallets.find_one({"pallet_id": r["pallet_id"]}) or {}
        ok = self.dev.printer.print_carton(r["parcel_code"], p.get("item_name") or p.get("item_code", ""),
                                           r["pallet_id"], p.get("wh_code", ""),
                                           r.get("mfg_date") or self._mfg_for(p), seq=r.get("seq"),
                                           received_code=r.get("received_code", ""), spec=spec_text(p))
        log.info("In lại tem thùng %s: %s", r["parcel_code"], "OK" if ok else "LỖI")
        if not ok:
            raise OrderError("IN LỖI " + r["parcel_code"])
        return r["parcel_code"]

    # ---- in lại toàn bộ tem của một pallet ("In tất cả" của bản cũ) ----
    def _job_active(self):
        return self._job_thread is not None and self._job_thread.is_alive()

    def _no_job(self):
        if self._job_active():
            raise OrderError("Đang in lại tem pallet. Chờ in xong hoặc bấm Dừng để hủy.")

    def reprint_pallet(self, pallet_id="", codes=None):
        """In lại tem mọi thùng đã đạt của pallet (đang làm hoặc trong lịch sử).

        codes: chỉ in lại các mã này (nút "In lại mã định danh" ở thẻ Thông số).
        Chạy nền vì một pallet có thể vài chục tem; bấm Dừng là hủy. Thùng chưa cân/in đạt
        không được in ở đây để không có tem cho thùng chưa qua kiểm tra.
        """
        pallet_id = str(pallet_id or "").strip()
        codes = [str(c).strip() for c in (codes or []) if str(c).strip()]
        with self.lock:
            if self.running:
                raise OrderError("Hãy bấm Dừng trước khi in lại tem.")
            self._no_job()
            if not self.dev.printer.connected:
                raise OrderError("KIỂM TRA LẠI KẾT NỐI MÁY IN!!")
            q = {"pallet_id": pallet_id} if pallet_id else {"status": {"$in": ACTIVE}}
            p = self.db.pallets.find_one(q, sort=[("seq", ASCENDING)])
            if p is not None:
                rows_q, col, source = {"pallet_id": p["pallet_id"]}, self.db.parcels, "đang làm"
            elif not pallet_id:
                raise OrderError("Chưa có lệnh sản xuất đang chạy.")
            else:
                p = self.db.pallets_his.find_one({"pallet_id": pallet_id}, sort=[("done_at", -1)])
                if p is None:
                    raise OrderError("Không tìm thấy pallet %s." % pallet_id)
                rows_q = {"pallet_id": pallet_id, "done_at": p["done_at"]}
                col, source = self.db.parcels_his, "lịch sử"
            if codes:
                rows_q["parcel_code"] = {"$in": codes}
            rows = list(col.find(dict(rows_q, status={"$gte": 1})).sort("seq", ASCENDING)
                        .limit(2000))
            if not rows and codes:
                raise OrderError("Thùng đã chọn chưa cân / in đạt nên không in lại tem được.")
            if not rows:
                raise OrderError("Pallet %s chưa có thùng nào đã in tem." % p["pallet_id"])
            total = len(rows)
            self.job = {"id": uuid.uuid4().hex[:8], "pallet_id": p["pallet_id"], "done": 0,
                        "total": total, "active": True, "error": "", "cancelled": False}
            self._job_stop.clear()
            self._job_thread = threading.Thread(
                target=self._reprint_job, args=(p, rows, col is self.db.parcels),
                name="reprint", daemon=True)
            self._job_thread.start()
        log.warning("IN LẠI TOÀN BỘ TEM pallet %s (%s): %d tem thùng", p["pallet_id"], source,
                    len(rows))
        self.event("reprint_pallet", pallet_id=p["pallet_id"], cartons=len(rows), source=source)
        return {"pallet_id": p["pallet_id"], "total": total, "job": self.job["id"]}

    def _reprint_job(self, p, rows, live):
        job, pid, printer = self.job, p["pallet_id"], self.dev.printer
        try:
            for r in rows:
                if self._job_stop.is_set():
                    job["cancelled"] = True
                    break
                self._msg("ĐANG IN LẠI TEM PALLET %s: %d/%d" % (pid, job["done"] + 1,
                                                                 job["total"]), ORANGE)
                code = r["parcel_code"]
                ok = printer.print_carton(code, p.get("item_name") or p.get("item_code", ""), pid,
                                          p.get("wh_code", ""), r.get("mfg_date") or self._mfg_for(p),
                                          seq=r.get("seq"), received_code=r.get("received_code", ""),
                                          spec=spec_text(p))
                log.info("[REPRINT] pallet %s thùng %s (STT %s): %s", pid, code, r.get("seq"),
                         "OK" if ok else "LỖI")
                if not ok:
                    job["error"] = "IN LỖI " + code
                    break
                if live:
                    self.db.parcels.update_one({"_id": r["_id"]}, {"$inc": {"print_count": 1}})
                job["done"] += 1
                self._job_stop.wait(0.3)             # không dồn lệnh vào bộ đệm máy in
        except Exception as e:
            log.exception("In lại tem pallet %s lỗi", pid)
            job["error"] = "LỖI: %s" % e
        finally:
            job["active"] = False
            if job["error"]:
                self._msg("IN LẠI TEM PALLET %s LỖI (%d/%d): %s" % (
                    pid, job["done"], job["total"], job["error"]), RED)
            elif job["cancelled"]:
                self._msg("ĐÃ HỦY IN LẠI TEM PALLET %s (%d/%d)" % (pid, job["done"],
                                                                   job["total"]), GRAY)
            else:
                self._msg("ĐÃ IN LẠI %d TEM CỦA PALLET %s" % (job["done"], pid), GREEN)
            self.event("reprint_pallet_end", pallet_id=pid, done=job["done"], total=job["total"],
                       error=job["error"], cancelled=job["cancelled"])

    # ---- các nút của thẻ Thông số (giữ như bản cũ, cho vận hành thủ công) ----
    def _pick_pallet(self, pallet_id):
        """Pallet được chọn ở bảng LỆNH ĐANG CHỜ; không chọn thì pallet đang làm."""
        pallet_id = str(pallet_id or "").strip()
        p = self.db.pallets.find_one({"pallet_id": pallet_id}) if pallet_id else self._front_pallet()
        if p is None:
            raise OrderError("Không tìm thấy pallet %s." % pallet_id if pallet_id else
                             "Chưa có lệnh sản xuất đang chạy.")
        return p

    def fake_complete(self, pallet_id=""):
        """"Thành công ảo": coi pallet là đã định danh xong, KHÔNG gửi gì lên server."""
        with self.lock:
            if self.running:
                raise OrderError("Hãy bấm Dừng trước.")
            self._no_job()
            p = self._pick_pallet(pallet_id)
            self._archive(p["pallet_id"], "DONE", "FAKE_COMPLETE")
        log.warning("THÀNH CÔNG ẢO pallet %s (không gửi server)", p["pallet_id"])
        self.event("fake_complete", pallet_id=p["pallet_id"])
        return p["pallet_id"]

    def pull_next(self):
        """"Tải lệnh mới": đưa pallet chờ đầu tiên vào làm (như btnPullNewTask bản cũ)."""
        with self.lock:
            if self.running:
                raise OrderError("Hãy bấm Dừng trước.")
            if self.db.pallets.count_documents({"status": {"$in": ACTIVE}}, limit=1):
                raise OrderError("Đang có lệnh sản xuất đang chạy, không thể tải lệnh mới.")
            p = self._current_pallet()
            if p is None:
                raise OrderError("Không có pallet nào đang chờ xử lý.")
        self.event("pull_next", pallet_id=p["pallet_id"])
        return p["pallet_id"]

    def delete_pallet(self, pallet_id=""):
        """"Xóa lệnh đang làm": chuyển pallet sang lịch sử (CANCEL), làm lại được bằng Thực hiện lại."""
        if self.running:
            raise OrderError("Hãy bấm Dừng trước khi xóa lệnh.")
        self._no_job()
        p = self._pick_pallet(pallet_id)
        return self.cancel_task({"Pallet_ID": p["pallet_id"]}, "MANUAL_DELETE")

    def orders(self, date_from, date_to, pallet="", po=""):
        """Hai bảng của thẻ Thông số + 3 con số thống kê."""
        def like(q):
            for k, v in (("pallet_id", pallet), ("po_key", po)):
                if v:
                    q[k] = {"$regex": re.escape(v), "$options": "i"}
            return q

        doc = self._mfg_doc()
        pend, done_active = [], 0
        for p in self.db.pallets.find(like({})).sort("seq", ASCENDING).limit(500):
            ok = self.db.parcels.count_documents({"pallet_id": p["pallet_id"], "status": {"$gte": 1}})
            done_active += ok
            pend.append(dict(self._order_row(p), mfg_date=self._mfg_for(p, doc),
                             cartons="%s/%s" % (ok, p.get("carton_count", 0))))
        comp, done_his = [], 0
        q = like({"done_at": {"$gte": date_from, "$lt": date_to}})
        for p in self.db.pallets_his.find(q).sort("done_at", -1).limit(500):
            done_his += p.get("carton_ok", 0)
            comp.append(dict(self._order_row(p), mfg_date=fmt_date(p.get("mfg_date")),
                             cartons="%s/%s" % (p.get("carton_ok", 0), p.get("carton_count", 0)),
                             done_at=p["done_at"].strftime("%d/%m/%Y %H:%M:%S"),
                             done_reason=p.get("done_reason", ""),
                             key=p["done_at"].strftime("%Y%m%d%H%M%S%f")))
        return {"pending": pend, "completed": comp,
                "stats": {"active": len(pend), "passed": len(comp),
                          "cartons": done_active + done_his}}

    @staticmethod
    def _order_row(p):
        return {"pallet_id": p["pallet_id"], "inner_pallet": p.get("inner_pallet", 0),
                "item_code": p.get("item_code", ""), "item_name": p.get("item_name", ""),
                "po": p.get("po_name") or p.get("po_id"), "location": p.get("location", ""),
                "status": p.get("status"), "wh_code": p.get("wh_code", ""),
                "line_id": p.get("line_id", ""), "po_id": p.get("po_id"),
                "task_id": p.get("task_id", ""), "ctn": p.get("ctn", 0), "qty": p.get("qty", 0),
                "pcs": p.get("pcs", 0),
                "created_at": p["created_at"].strftime("%d/%m/%Y %H:%M:%S")
                if p.get("created_at") else ""}

    def order_parcels(self, pallet_id, key=""):
        """"Tải mã định danh": danh sách thùng của pallet (đang làm, hoặc lịch sử theo key)."""
        pallet_id = str(pallet_id or "").strip()
        if not pallet_id:
            raise OrderError("Vui lòng chọn một lệnh (pallet) trước khi tải mã định danh.")
        p = None if key else self.db.pallets.find_one({"pallet_id": pallet_id})
        if p is not None:
            rows = self.db.parcels.find({"pallet_id": pallet_id})
            mfg = self._mfg_for(p)
        else:
            q = {"pallet_id": pallet_id}
            if key:
                q["done_at"] = datetime.datetime.strptime(key, "%Y%m%d%H%M%S%f")
            p = self.db.pallets_his.find_one(q, sort=[("done_at", -1)])
            if p is None:
                raise OrderError("Không tìm thấy pallet %s." % pallet_id)
            rows = self.db.parcels_his.find({"pallet_id": pallet_id, "done_at": p["done_at"]})
            mfg = fmt_date(p.get("mfg_date"))
        out = [{"stt": r["seq"], "code": r["parcel_code"], "st": r["status"],
                "text": "In lỗi" if r["status"] == 0 and r.get("fail") else
                STATUS_TEXT.get(r["status"], "Không xác định"),
                "mfg_date": r.get("mfg_date") or mfg, "weight": r.get("weight"),
                "prints": r.get("print_count", 0),
                "done_at": r["done_at"].strftime("%d/%m/%Y %H:%M:%S") if r.get("done_at") else ""}
               for r in rows.sort("seq", ASCENDING).limit(2000)]
        return {"pallet_id": pallet_id, "item": p.get("item_name") or p.get("item_code", ""),
                "rows": out, "done": sum(1 for r in out if r["st"] >= 1), "total": len(out)}

    def label_sheet(self, pallet_id=""):
        """"In PDF mã hiện tại": dữ liệu tem của mọi thùng trong pallet đang làm."""
        p = self._pick_pallet(pallet_id)
        rows = list(self.db.parcels.find({"pallet_id": p["pallet_id"]}).sort("seq", ASCENDING)
                    .limit(2000))
        if not rows:
            raise OrderError("Không có ParcelCode nào thuộc pallet hiện tại.")
        mfg = self._mfg_for(p)
        return {"pallet_id": p["pallet_id"], "item": p.get("item_name") or p.get("item_code", ""),
                "wh_code": p.get("wh_code", ""), "spec": spec_text(p),
                "rows": [{"seq": r["seq"], "code": r["parcel_code"],
                          "full": r.get("received_code") or r["parcel_code"],
                          "mfg_date": r.get("mfg_date") or mfg} for r in rows]}

    def print_manual(self, text):
        if self.running:
            raise OrderError("Hãy bấm Dừng trước khi in thử.")
        self._no_job()
        ok = self.dev.printer.print_carton(text, "", "", "", "")      # tem thử: chỉ có mã
        log.info("In thử '%s': %s", text, "OK" if ok else "LỖI")
        if not ok:
            raise OrderError("IN LỖI " + text)

    def reload_pallet(self, pallet_id):
        """Nạp lại một pallet từ lịch sử để làm lại (ReloadPalletFromHis của bản cũ)."""
        with self.lock:
            if self.db.pallets.count_documents({}, limit=1):
                raise OrderError("Đang có lệnh sản xuất đang chạy, không thể reload.")
            p = self.db.pallets_his.find_one({"pallet_id": pallet_id}, sort=[("done_at", -1)])
            if p is None:
                raise OrderError("Không tìm thấy pallet trong lịch sử.")
            rows = list(self.db.parcels_his.find({"pallet_id": pallet_id, "done_at": p["done_at"]})
                        .sort("seq", ASCENDING))
            if not rows:
                raise OrderError("Pallet này không còn danh sách thùng trong lịch sử.")
            for k in ("_id", "done_at", "done_reason", "carton_ok", "send_error", "send_attempts",
                      "send_at", "identify_requested", "closed_at"):
                p.pop(k, None)
            seq = self.db.meta.find_one_and_update({"_id": "pallet_seq"}, {"$inc": {"v": 1}},
                                                   upsert=True) or {"v": 0}
            p.update(status="WAIT", seq=seq.get("v", 0) + 1, created_at=db.now(), reloaded=True)
            self.db.pallets.insert_one(p)
            self.db.parcels.insert_many([{
                "batch": p.get("batch"), "pallet_id": pallet_id, "seq": r["seq"],
                "parcel_code": r["parcel_code"], "received_code": r.get("received_code", ""),
                "status": 0, "fail": False, "print_count": 0, "weight": None,
                "created_at": db.now()} for r in rows])
            self._dirty = True
        log.warning("Nạp lại pallet %s từ lịch sử (%d thùng)", pallet_id, len(rows))
        self.event("reload", pallet_id=pallet_id)

    # ------------------------------------------------------------------ dữ liệu cho màn hình
    def _refresh(self):
        d = self.db
        p = self._front_pallet()
        c = {"pallet": None, "rows": [], "carton": [0, 0], "order": [0, 0], "pallets": [0, 0],
             "pos": -1, "queue": d.pallets.count_documents({"status": "WAIT"}),
             "has_order": d.pallets.count_documents({}, limit=1) > 0,
             "can_identify": d.pallets.count_documents({"status": "AWAIT_SEND"}, limit=1) > 0}
        if p:
            rows = list(d.parcels.find({"pallet_id": p["pallet_id"]}).sort("seq", ASCENDING).limit(2000))
            c["rows"] = [{"stt": r["seq"], "code": r["parcel_code"], "pallet": r["pallet_id"],
                          "st": r["status"],
                          "text": "In lỗi" if r["status"] == 0 and r.get("fail") else
                          STATUS_TEXT.get(r["status"], "Không xác định")} for r in rows]
            done = sum(1 for r in rows if r["status"] >= 1)
            c["carton"] = [done, len(rows) or p.get("ctn", 0)]
            key = p.get("po_key")
            # Số thùng hoàn thành tính theo LỆNH: thùng đã làm / tổng thùng cần làm của mọi
            # pallet thuộc lệnh (đang chờ / đang làm + đã xong). Pallet nạp lại từ lịch sử chỉ
            # tính một lần (theo bản đang chạy); lịch sử chỉ lấy lần xong mới nhất mỗi pallet.
            act = list(d.pallets.find({"po_key": key}, {"pallet_id": 1, "carton_count": 1}))
            act_ids = {a["pallet_id"] for a in act}
            his = {}
            for h in d.pallets_his.find({"po_key": key, "status": "DONE"},
                                        {"pallet_id": 1, "carton_ok": 1, "carton_count": 1})                    .sort("done_at", -1).limit(5000):
                if h["pallet_id"] not in act_ids:
                    his.setdefault(h["pallet_id"], h)
            his = list(his.values())
            others = [i for i in act_ids if i != p["pallet_id"]]
            other_ok = d.parcels.count_documents({"pallet_id": {"$in": others},
                                                  "status": {"$gte": 1}}) if others else 0
            c["order"] = [done + other_ok + sum(h.get("carton_ok", 0) for h in his),
                          sum(a.get("carton_count", 0) for a in act) +
                          sum(h.get("carton_count") or h.get("carton_ok", 0) for h in his)]
            c["pallets"] = [len(his), len(his) + len(act)]
            pos = self.settings["positions"]
            c["pos"] = pos.index(p.get("location")) if p.get("location") in pos[:3] else -1
            std = p.get("weight_ref") or self.settings["scale_value"]
            c["pallet"] = {
                "po": p.get("po_name") or p.get("po_id"), "task_id": p.get("task_id"),
                "pallet_id": p["pallet_id"], "location": p.get("location"),
                "item": p.get("item_name") or p.get("item_code"),
                "spec": ("%s Hộp / Thùng" % p["inner_carton"]) if p.get("inner_carton") else "N/A",
                "weight": "%s ± %s GAM" % (std, self.settings["scale_error"]),
                "mfg_date": self._mfg_for(p) or time.strftime("%d/%m/%Y"),
                "status": p["status"], "wh_code": p.get("wh_code"), "line_id": p.get("line_id")}
        cnt = d.counters.find_one({"_id": time.strftime("%Y-%m-%d")}) or {}
        c["counter"] = {"total": cnt.get("total", 0), "pass": cnt.get("pass", 0),
                        "fail": cnt.get("fail", 0)}
        pend = d.inbox.find_one({"_id": "pending"})
        c["pending"] = {"po": field(pend["data"], "PO_Name", "PO_ID"),
                        "task": field(pend["data"], "Task_ID")} if pend else None
        self._cache = c

    def snapshot(self):
        if self._dirty or not self._cache:
            self._dirty = False
            try:
                self._refresh()
            except Exception:
                self._dirty = True
                raise
        c = self._cache
        w = self.weight if self.running else 0       # STOP: cân hiển thị 0 g như bản cũ
        if time.time() - self._sim_seen[0] > 2:      # dò cổng tốn ~0,3 s nên chỉ dò mỗi 2 s
            self._sim_seen = (time.time(), bool(simguard.simulator_running(self)))
        return {
            "time": time.strftime("%H:%M:%S"), "date": time.strftime("%d/%m/%Y"),
            "station": self.cfg["station_id"], "desk_no": self.cfg.get("desk_no", 1),
            "software": self.cfg["software_name"],
            "version": config.VERSION, "mode": self.mode, "running": self.running,
            "big": self.big, "big_color": self.big_color,
            "message": self.message, "msg_color": self.msg_color, "light": self.light,
            "weight": w, "current": self.current_code,
            "dev": self.dev.status(), "wcs": self.wcs, "rcs": self.rcs, "rcs_error": self.rcs_error,
            "positions": self.settings["positions"][:3], "sim": self._sim_seen[1],
            "job": self.job,
            **c,
        }

    def history(self, date_from, date_to, text="", limit=300):
        q = {"done_at": {"$gte": date_from, "$lt": date_to}}
        if text:
            q["$or"] = [{"pallet_id": {"$regex": text, "$options": "i"}},
                        {"po_key": {"$regex": text, "$options": "i"}}]
        out = []
        for p in self.db.pallets_his.find(q).sort("done_at", -1).limit(limit):
            out.append({"pallet_id": p["pallet_id"], "po": p.get("po_name") or p.get("po_id"),
                        "item": p.get("item_name") or p.get("item_code"),
                        "location": p.get("location"), "status": p.get("status"),
                        "reason": p.get("done_reason"),
                        "cartons": "%s/%s" % (p.get("carton_ok", 0), p.get("carton_count", 0)),
                        "done_at": p["done_at"].strftime("%d/%m/%Y %H:%M:%S")})
        return out

    def history_parcels(self, pallet_id):
        return [{"stt": r["seq"], "code": r["parcel_code"], "st": r["status"],
                 "weight": r.get("weight"), "prints": r.get("print_count", 0),
                 "done_at": r["done_at"].strftime("%d/%m/%Y %H:%M:%S") if r.get("done_at") else ""}
                for r in self.db.parcels_his.find({"pallet_id": pallet_id}).sort("seq", ASCENDING)
                .limit(2000)]

    def queue(self):
        return [{"pallet_id": p["pallet_id"], "po": p.get("po_name") or p.get("po_id"),
                 "task_id": p.get("task_id"), "location": p.get("location"),
                 "status": p["status"], "cartons": p.get("carton_count", 0)}
                for p in self.db.pallets.find({}).sort("seq", ASCENDING).limit(500)]
