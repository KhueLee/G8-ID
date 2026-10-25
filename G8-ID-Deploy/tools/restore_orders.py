"""Khôi phục lệnh WCS đã trả SUCCESS nhưng không có trong DB (khoi_phuc_lenh.bat).

Đọc logs\\http-*.log, lấy mọi /ids/orderTask từ WCS (không tính 127.0.0.1) đã được trả
200 SUCCESS, rồi đối chiếu với DB AUTO: lệnh coi là ĐÃ CÓ nếu Task_ID + PO_ID hoặc bất kỳ mã thùng
nào của nó đã nằm trong lệnh đang chờ / lịch sử. Lệnh bị /ids/cancelTask (cùng Task_ID hoặc PO_ID)
sau đó thì bỏ qua.

Mặc định chỉ LIỆT KÊ, không gửi gì. Thêm --apply để gửi lại các lệnh "SẼ KHÔI PHỤC" vào cổng nhận
lệnh của phần mềm đang chạy (phải ở chế độ AUTO) - đi đúng đường như lệnh WCS gửi.

    khoi_phuc_lenh.bat                       liệt kê
    khoi_phuc_lenh.bat --from 2026-10-23     chỉ xét log từ ngày này
    khoi_phuc_lenh.bat --task <Task_ID>      chỉ xét các Task_ID này (gõ nhiều lần được)
    khoi_phuc_lenh.bat --apply               gửi lại
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pymongo import MongoClient  # noqa: E402

from app import config  # noqa: E402
from app.engine import field, parse_carton, to_int  # noqa: E402

START = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3} ")
ENTRY = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.\d{3} .*?\bIN  POST (/ids/[A-Za-z_]+)/? "
                   r"từ (\S+) body=(.*) -> (\d{3}) \{code:(\d+), desc:.*\}\s*$", re.S)
LOCAL = ("127.0.0.1", "::1")
lines = []


def out(text=""):
    lines.append(text)
    print(text)


def read_entries(log_dir, day_from):
    """Các bản tin vào đã thành công, theo thứ tự thời gian. Body nhiều dòng được ghép lại."""
    files = sorted(glob.glob(os.path.join(log_dir, "http-*.log")))
    if day_from:
        files = [f for f in files if os.path.basename(f)[5:13] >= day_from.replace("-", "")]
    entries = []
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as f:
            buf = []
            for line in f.read().splitlines() + ["0000-00-00 00:00:00.000 end"]:
                if START.match(line) and buf:
                    m = ENTRY.match("\n".join(buf))
                    if m and m.group(5) == "200" and m.group(6) == "1000":
                        try:
                            body = json.loads(m.group(4))
                        except ValueError:
                            body = None
                        if isinstance(body, dict):
                            entries.append({"at": m.group(1), "path": m.group(2),
                                            "src": m.group(3), "raw": m.group(4), "body": body})
                    buf = []
                buf.append(line)
    entries.sort(key=lambda e: e["at"])
    return entries


def codes_of(body):
    out_ = []
    for item in field(body, "info_detail", "InforDetail", "infor_detail") or []:
        for raw in field(item, "Carton_List", "CartonList") or []:
            code, _ = parse_carton(raw)
            if code:
                out_.append(code)
    return out_


def lpns_of(body):
    return [str(field(i, "Pallet_ID", "PalletId", default="") or "").strip()
            for i in field(body, "info_detail", "InforDetail", "infor_detail") or []]


def api(url, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="day_from", default="", help="YYYY-MM-DD")
    ap.add_argument("--task", action="append", default=[], help="chỉ xét Task_ID này")
    ap.add_argument("--apply", action="store_true", help="gửi lại các lệnh cần khôi phục")
    ap.add_argument("--include-local", action="store_true",
                    help="tính cả lệnh gửi từ 127.0.0.1 (công cụ mô phỏng / lần khôi phục trước)")
    a = ap.parse_args()
    cfg = config.get()
    log_dir = config.path(cfg["log"]["dir"])
    entries = read_entries(log_dir, a.day_from)
    out("Khôi phục lệnh từ http log lúc %s (thư mục %s)" % (time.strftime("%d/%m/%Y %H:%M:%S"),
                                                            log_dir))
    orders = [e for e in entries if e["path"] == "/ids/orderTask"
              and (a.include_local or e["src"] not in LOCAL)]
    cancels = [e for e in entries if e["path"] == "/ids/cancelTask"]
    if a.task:
        orders = [e for e in orders if str(field(e["body"], "Task_ID", default="")) in a.task]
    out("Tìm thấy %d lệnh WCS đã trả SUCCESS, %d lệnh hủy." % (len(orders), len(cancels)))

    d = MongoClient(cfg["mongo"]["uri"], serverSelectionTimeoutMS=3000)[cfg["mongo"]["db"]]
    all_codes = list({c for e in orders for c in codes_of(e["body"])})
    have_codes = set()
    for col in (d.parcels, d.parcels_his):
        have_codes |= {r["parcel_code"] for r in col.find({"parcel_code": {"$in": all_codes}},
                                                          {"parcel_code": 1})}
    todo = []
    for n, e in enumerate(orders, 1):
        b = e["body"]
        tid, po = str(field(b, "Task_ID", default="") or ""), to_int(field(b, "PO_ID"))
        codes = codes_of(b)
        head = "%3d. %s  PO=%s (%s)  Task_ID=%s  pallet=%s  %d thùng" % (
            n, e["at"], field(b, "PO_Name", default=""), po, tid or "-",
            ",".join(lpns_of(b)), len(codes))
        if tid and any(c.find_one({"task_id": tid, "po_id": po}, {"_id": 1})
                       for c in (d.pallets, d.pallets_his)):
            out(head + "\n       ĐÃ CÓ trong DB (Task_ID)")
            continue
        if have_codes.intersection(codes):
            out(head + "\n       ĐÃ CÓ trong DB (%d/%d mã thùng)" % (
                len(have_codes.intersection(codes)), len(codes)))
            continue
        cancel = next((c for c in cancels if c["at"] >= e["at"] and (
            (tid and str(field(c["body"], "Task_ID", default="")) == tid) or
            (po and to_int(field(c["body"], "PO_ID")) == po))), None)
        if cancel and not a.task:
            out(head + "\n       BỎ QUA: WMS đã hủy lúc %s" % cancel["at"])
            continue
        out(head + "\n       SẼ KHÔI PHỤC")
        todo.append(e)
    out("")
    out("Cần khôi phục: %d lệnh." % len(todo))

    if a.apply and todo:
        ui = "http://127.0.0.1:%s" % cfg["ui"]["port"]
        try:
            s, info = api(ui + "/api/info")
        except OSError as ex:
            out("KHÔNG GỬI: phần mềm chưa chạy (%s)." % ex)
            return finish(log_dir)
        if info.get("mode") != "AUTO":
            out("KHÔNG GỬI: trạm đang ở chế độ %s. Chuyển AUTO rồi chạy lại." % info.get("mode"))
            return finish(log_dir)
        if (info.get("settings") or {}).get("confirm_new_order"):
            out("KHÔNG GỬI: đang bật 'Hỏi Yes/No khi có lệnh mới' (chỉ giữ được 1 lệnh chờ hỏi). "
                "Tắt ở thẻ Cài đặt rồi chạy lại.")
            return finish(log_dir)
        url = "http://127.0.0.1:%s/ids/orderTask/" % cfg["order_server"]["port"]
        ok = 0
        for e in todo:
            s, r = api(url, e["body"])
            good = s == 200 and r.get("code") == 1000
            ok += good
            out("  %s Task_ID=%s -> %s %s" % ("OK " if good else "LỖI", field(e["body"], "Task_ID"),
                                              s, r.get("desc")))
        out("Đã khôi phục %d/%d lệnh." % (ok, len(todo)))
    elif todo:
        out("Chưa gửi gì. Kiểm tra danh sách trên rồi chạy lại với --apply để khôi phục.")
    finish(log_dir)


def finish(log_dir):
    path = os.path.join(log_dir, "restore_orders.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\nĐã ghi kết quả vào %s" % path)


if __name__ == "__main__":
    main()
