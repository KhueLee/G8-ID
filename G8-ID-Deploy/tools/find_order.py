"""Tra một lệnh trong DB (tim_lenh.bat). Chỉ ĐỌC, không sửa gì.

Tìm theo mã pallet / tên PO / PO_ID ở cả DB AUTO và DB mô phỏng (MANUAL/HYBRID): lệnh đang chờ,
lịch sử, lệnh chờ xác nhận và nhật ký sự kiện. Kết quả in ra màn hình và ghi logs\\find_order.txt.
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pymongo import MongoClient  # noqa: E402

from app import config  # noqa: E402

lines = []


def out(text=""):
    lines.append(text)
    print(text)


def fmt(v):
    return v.strftime("%d/%m/%Y %H:%M:%S") if hasattr(v, "strftime") else v


def main():
    q = " ".join(sys.argv[1:]).strip() or input("Mã pallet / tên PO / PO_ID cần tìm: ").strip()
    if not q:
        return
    cfg = config.get()
    m = cfg["mongo"]
    try:
        with open(config.MODE_FILE, encoding="utf-8") as f:
            mode = json.load(f)
    except (OSError, ValueError):
        mode = {"mode": "AUTO (mặc định, chưa có mode.json)"}
    out("Tra lệnh '%s' lúc %s" % (q, time.strftime("%d/%m/%Y %H:%M:%S")))
    out("Chế độ đang lưu: %s (đổi lúc %s)" % (mode.get("mode"), mode.get("at", "?")))
    rx = {"$regex": re.escape(q), "$options": "i"}
    cond = [{"pallet_id": rx}, {"lpn": rx}, {"po_key": rx}, {"po_name": rx}, {"task_id": rx}]
    if q.isdigit():
        cond.append({"po_id": int(q)})
    cli = MongoClient(m["uri"], serverSelectionTimeoutMS=3000)
    for name, label in ((m["db"], "AUTO"), (m["db_manual"], "MANUAL/HYBRID")):
        d = cli[name]
        out("")
        out("===== DB %s (%s) =====" % (name, label))
        out("Tổng: %d lệnh đang chờ, %d lệnh lịch sử" % (d.pallets.count_documents({}),
                                                         d.pallets_his.count_documents({})))
        for p in d.pallets.find({"$or": cond}).sort("seq", 1):
            out("  [ĐANG CHỜ] pallet=%s LPN=%s PO=%s status=%s nhận lúc %s%s" % (
                p.get("pallet_id"), p.get("lpn", "-"), p.get("po_key"), p.get("status"), fmt(p.get("created_at")),
                " (WMS đã dừng)" if p.get("order_stopped") else ""))
        for p in d.pallets_his.find({"$or": cond}).sort("done_at", -1).limit(50):
            out("  [LỊCH SỬ ] pallet=%s LPN=%s PO=%s status=%s lý do=%s nhận lúc %s, chuyển lúc %s, %s/%s thùng" % (
                p.get("pallet_id"), p.get("lpn", "-"), p.get("po_key"), p.get("status"), p.get("done_reason"),
                fmt(p.get("created_at")), fmt(p.get("done_at")), p.get("carton_ok", 0),
                p.get("carton_count", 0)))
        inbox = d.inbox.find_one({"_id": "pending"})
        if inbox and q.lower() in json.dumps(inbox.get("data", {}), ensure_ascii=False).lower():
            out("  [CHỜ XÁC NHẬN Yes/No] nhận lúc %s" % fmt(inbox.get("at")))
        for e in d.event_log.find().sort("at", -1).limit(5000):
            s = json.dumps({k: v for k, v in e.items() if k not in ("_id", "at")},
                           ensure_ascii=False, default=str)
            if q.lower() in s.lower():
                out("  [SỰ KIỆN ] %s %s" % (fmt(e.get("at")), s[:300]))
    path = os.path.join(config.path(cfg["log"]["dir"]), "find_order.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    out("")
    out("Đã ghi kết quả vào %s" % path)


if __name__ == "__main__":
    main()
