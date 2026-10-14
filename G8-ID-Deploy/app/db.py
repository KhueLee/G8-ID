"""MongoDB: tự khởi động mongod kèm theo, tạo index/TTL, dọn dữ liệu cũ.

Chống tràn:
  - pallets / parcels chỉ giữ lệnh ĐANG làm (như bảng *_Prod bản cũ); xong hoặc hủy là
    chuyển sang pallets_his / parcels_his (thay cho trigger SQL).
  - *_his và event_log có TTL index -> MongoDB tự xóa sau N ngày; thêm trần số bản ghi.
  - Mọi truy vấn trên màn hình đều đi theo index và có limit.
"""
import datetime
import logging
import os
import subprocess
import time

import pymongo
from pymongo import ASCENDING, DESCENDING

from . import config

log = logging.getLogger("db")

_client = None
_mongod = None        # tiến trình mongod do phần mềm tự bật
_owned = False        # mongod kèm theo (kể cả còn sót từ lần chạy trước) -> tắt khi thoát
_dbs = {}


def now():
    return datetime.datetime.now()


def _ping(uri, timeout_ms=1500):
    c = pymongo.MongoClient(uri, serverSelectionTimeoutMS=timeout_ms, connectTimeoutMS=timeout_ms)
    try:
        c.admin.command("ping")
        return True
    except Exception:
        return False
    finally:
        c.close()


def _start_bundled(cfg):
    global _mongod
    exe = config.path("mongodb", "bin", "mongod.exe")
    if not os.path.exists(exe):
        raise RuntimeError("Không kết nối được MongoDB và không có mongodb\\bin\\mongod.exe")
    dbpath = os.path.join(config.DATA_DIR, "db")
    os.makedirs(dbpath, exist_ok=True)
    logdir = config.path(cfg["log"]["dir"])
    os.makedirs(logdir, exist_ok=True)
    hostport = cfg["mongo"]["uri"].split("//", 1)[1].split("/", 1)[0].split(",")[0]
    port = hostport.split(":")[1] if ":" in hostport else "27017"
    args = [exe, "--dbpath", dbpath, "--bind_ip", "127.0.0.1", "--port", port,
            "--wiredTigerCacheSizeGB", str(cfg["mongo"]["cache_gb"]),
            "--logpath", os.path.join(logdir, "mongod.log"), "--logappend", "--quiet"]
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    _mongod = subprocess.Popen(args, creationflags=flags, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log.info("Đã bật mongod kèm theo (pid %s, cổng %s, dbpath %s)", _mongod.pid, port, dbpath)


def connect():
    """Kết nối MongoDB; chưa có thì bật mongod kèm theo. Thường xong trong 1-3 giây."""
    global _client, _owned
    cfg = config.get()
    uri = cfg["mongo"]["uri"]
    t0 = time.time()
    if not _ping(uri):
        if not cfg["mongo"]["start_bundled"]:
            raise RuntimeError(f"Không kết nối được MongoDB tại {uri}")
        _start_bundled(cfg)
        deadline = time.time() + 60
        while not _ping(uri, 1000):
            if _mongod.poll() is not None:
                raise RuntimeError(f"mongod thoát ngay (mã {_mongod.returncode}) - xem logs\\mongod.log")
            if time.time() > deadline:
                raise RuntimeError("mongod không sẵn sàng sau 60 giây - xem logs\\mongod.log")
            time.sleep(0.3)
    _client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000,
                                  socketTimeoutMS=10000, appname="g8id")
    _owned = _mongod is not None or _is_our_mongod()
    log.info("MongoDB sẵn sàng sau %.1f s (%s, server %s, %s)", time.time() - t0, uri,
             _client.server_info().get("version"),
             "mongod kèm theo" if _owned else "MongoDB cài sẵn trên máy")
    return _client


def _is_our_mongod():
    """mongod kèm theo còn sống từ lần chạy trước (phần mềm bị tắt cứng) -> vẫn là của mình."""
    try:
        opts = _client.admin.command("getCmdLineOpts").get("parsed", {})
        theirs = os.path.normcase(os.path.abspath(opts.get("storage", {}).get("dbPath", "")))
        return theirs == os.path.normcase(os.path.abspath(os.path.join(config.DATA_DIR, "db")))
    except Exception:
        return False


def settings_col():
    """Thông số vận hành luôn nằm ở DB chính, không phụ thuộc AUTO/MANUAL."""
    return _client[config.get()["mongo"]["db"]]["settings"]


def data_db(manual):
    """DB nghiệp vụ: AUTO và MANUAL tách riêng để dữ liệu mô phỏng không lẫn vào sản xuất."""
    m = config.get()["mongo"]
    name = m["db_manual"] if manual else m["db"]
    if name not in _dbs:
        d = _client[name]
        ensure_indexes(d)
        _dbs[name] = d
    return _dbs[name]


def _ttl(col, field, days, name):
    secs = int(days) * 86400
    try:
        col.create_index([(field, ASCENDING)], expireAfterSeconds=secs, name=name)
    except pymongo.errors.OperationFailure:
        # Index đã có với số ngày khác -> đổi thời hạn tại chỗ.
        col.database.command("collMod", col.name,
                             index={"name": name, "expireAfterSeconds": secs})


def ensure_indexes(d):
    m = config.get()["mongo"]
    d.pallets.create_index([("pallet_id", ASCENDING)], unique=True, name="ux_pallet")
    d.pallets.create_index([("status", ASCENDING), ("seq", ASCENDING)], name="ix_status_seq")
    d.pallets.create_index([("task_id", ASCENDING)], name="ix_task")
    d.parcels.create_index([("parcel_code", ASCENDING)], unique=True, name="ux_parcel")
    d.parcels.create_index([("pallet_id", ASCENDING), ("status", ASCENDING), ("seq", ASCENDING)],
                           name="ix_pallet_status_seq")
    d.pallets_his.create_index([("pallet_id", ASCENDING)], name="ix_pallet")
    d.pallets_his.create_index([("po_key", ASCENDING), ("status", ASCENDING)], name="ix_po")
    d.parcels_his.create_index([("pallet_id", ASCENDING), ("seq", ASCENDING)], name="ix_pallet_seq")
    _ttl(d.pallets_his, "done_at", m["history_days"], "ttl_done_at")
    _ttl(d.parcels_his, "done_at", m["history_days"], "ttl_done_at")
    _ttl(d.event_log, "at", m["event_log_days"], "ttl_at")


def janitor(d):
    """Trần số bản ghi lịch sử (phòng khi TTL chưa kịp xóa hoặc sản lượng tăng đột biến)."""
    cap = int(config.get()["mongo"]["history_max_docs"])
    for col in (d.parcels_his, d.pallets_his, d.event_log):
        n = col.estimated_document_count()
        if n > cap:
            cut = list(col.find({}, {"_id": 1}).sort("_id", DESCENDING).skip(cap).limit(1))
            if cut:
                r = col.delete_many({"_id": {"$lte": cut[0]["_id"]}})
                log.warning("Dọn %s: xóa %d bản ghi cũ nhất (trần %d)", col.name, r.deleted_count, cap)


def stats(d):
    out = {}
    for name in ("pallets", "parcels", "pallets_his", "parcels_his", "event_log"):
        out[name] = d[name].estimated_document_count()
    try:
        s = d.command("dbstats")
        out["size_mb"] = round((s.get("dataSize", 0) + s.get("indexSize", 0)) / 1048576, 2)
    except Exception:
        pass
    return out


def close():
    """Đóng kết nối; mongod do phần mềm bật thì tắt sạch (không để lại lock)."""
    global _client, _mongod, _owned
    if _client is not None:
        uri = config.get()["mongo"]["uri"]
        if _owned:
            try:
                _client.admin.command("shutdown")
            except Exception:
                pass  # server đóng kết nối ngay khi nhận lệnh shutdown
            deadline = time.time() + 15
            while time.time() < deadline and _ping(uri, 300):
                time.sleep(0.2)
            if _mongod is not None and _mongod.poll() is None:
                try:
                    _mongod.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _mongod.terminate()
            log.info("Đã tắt mongod kèm theo")
        try:
            _client.close()
        except Exception:
            pass
    _client, _mongod, _owned = None, None, False
    _dbs.clear()
