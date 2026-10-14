"""Log ra file theo ngày: app-YYYYMMDD.log, http-..., device-..., crash.log. Tự xóa file cũ."""
import collections
import datetime
import faulthandler
import logging
import os
import sys
import threading
import time

FMT = "%(asctime)s.%(msecs)03d [%(levelname)-5s] [%(threadName)s] [%(name)s] %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"

# 300 dòng gần nhất cho thẻ "Lịch sử Log" và khung log ở Trang chủ.
recent = collections.deque(maxlen=300)
_log_dir = None
_crash_file = None


class DailyFileHandler(logging.Handler):
    """Mỗi ngày một file <prefix>-YYYYMMDD.log; mở/đóng theo từng lần đổi ngày."""

    def __init__(self, log_dir, prefix):
        super().__init__()
        self.log_dir, self.prefix = log_dir, prefix
        self._day, self._fh = None, None

    def emit(self, record):
        try:
            day = time.strftime("%Y%m%d", time.localtime(record.created))
            if day != self._day:
                if self._fh:
                    self._fh.close()
                self._fh = open(os.path.join(self.log_dir, f"{self.prefix}-{day}.log"),
                                "a", encoding="utf-8")
                self._day = day
            self._fh.write(self.format(record) + "\n")
            self._fh.flush()
        except Exception:
            self.handleError(record)

    def close(self):
        if self._fh:
            self._fh.close()
            self._fh = None
        super().close()


class RecentHandler(logging.Handler):
    def emit(self, record):
        if record.name.startswith(("http", "raw", "waitress", "werkzeug")):
            return
        recent.append({
            "t": time.strftime("%H:%M:%S", time.localtime(record.created)),
            "lv": record.levelname,
            "tag": record.name,
            "msg": record.getMessage(),
        })


def setup(log_dir, level="INFO", keep_days=30, prefix="app", console=True):
    global _log_dir, _crash_file
    os.makedirs(log_dir, exist_ok=True)
    _log_dir = log_dir
    fmt = logging.Formatter(FMT, DATEFMT)
    root = logging.getLogger()
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    for h in list(root.handlers):
        root.removeHandler(h)

    main = DailyFileHandler(log_dir, prefix)
    main.setFormatter(fmt)
    root.addHandler(main)
    root.addHandler(RecentHandler())
    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)-5s] [%(name)s] %(message)s",
                                          "%H:%M:%S"))
        ch.addFilter(lambda r: not r.name.startswith(("raw", "http")))
        root.addHandler(ch)

    # Kênh riêng: bản tin HTTP vào/ra (đủ body) và thiết bị (kết nối, byte thô).
    for name in ("http", "device", "raw"):
        h = DailyFileHandler(log_dir, f"{prefix}-{name}" if prefix != "app" else name)
        h.setFormatter(fmt)
        logging.getLogger(name).addHandler(h)
    logging.getLogger("raw").propagate = False
    logging.getLogger("waitress").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    _crash_file = open(os.path.join(log_dir, "crash.log"), "a", encoding="utf-8")
    faulthandler.enable(_crash_file)

    def _hook(exc_type, exc, tb):
        logging.getLogger("crash").critical("Lỗi không bắt được", exc_info=(exc_type, exc, tb))

    sys.excepthook = _hook
    threading.excepthook = lambda a: logging.getLogger("crash").critical(
        "Luồng %s chết vì lỗi", a.thread.name if a.thread else "?",
        exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    cleanup(keep_days)


def cleanup(keep_days):
    """Xóa file log quá hạn để ổ đĩa không đầy."""
    if not _log_dir:
        return
    limit = time.time() - max(1, int(keep_days)) * 86400
    for name in os.listdir(_log_dir):
        p = os.path.join(_log_dir, name)
        try:
            if name.endswith(".log") and name != "crash.log" and os.path.getmtime(p) < limit:
                os.remove(p)
        except OSError:
            pass
    try:  # crash.log không theo ngày: cắt khi quá 5 MB
        p = os.path.join(_log_dir, "crash.log")
        if os.path.getsize(p) > 5 * 1024 * 1024:
            _crash_file.truncate(0)
    except OSError:
        pass


def list_files():
    if not _log_dir:
        return []
    out = []
    for name in sorted(os.listdir(_log_dir), reverse=True):
        if name.endswith(".log"):
            p = os.path.join(_log_dir, name)
            out.append({"name": name, "size": os.path.getsize(p),
                        "mtime": datetime.datetime.fromtimestamp(os.path.getmtime(p))
                        .strftime("%d/%m/%Y %H:%M")})
    return out


def tail(name, lines=500, grep=""):
    """Đọc N dòng cuối của một file log (cho thẻ Lịch sử Log)."""
    if not _log_dir or os.path.basename(name) != name or not name.endswith(".log"):
        return []
    p = os.path.join(_log_dir, name)
    if not os.path.exists(p):
        return []
    with open(p, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - 400_000))
        data = f.read().decode("utf-8", "replace").splitlines()
    if grep:
        g = grep.lower()
        data = [x for x in data if g in x.lower()]
    return data[-lines:]
