"""Điểm vào: python -m app.main  (chạy từ chay_dinh_danh.bat).

Mã thoát: 0 = thoát chủ động (không khởi động lại), 3 = đã có bản khác đang chạy,
khác = lỗi -> chay_dinh_danh.bat tự khởi động lại sau vài giây.
"""
import ctypes
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time

from . import config, db, logsetup

log = logging.getLogger("main")
_quit = threading.Event()
_cleanup_lock = threading.Lock()
_cleaned = False
_ctrl_handler = None


def port_in_use(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", int(port))) == 0
    finally:
        s.close()


def open_browser(cfg):
    url = "http://127.0.0.1:%s/" % cfg["ui"]["port"]
    if not cfg["ui"].get("open_browser", True) or os.environ.get("G8ID_NO_BROWSER"):
        return
    candidates = [os.path.join(os.environ.get(k, ""), r"Google\Chrome\Application\chrome.exe")
                  for k in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")]
    chrome = next((c for c in candidates if os.path.exists(c)), None)
    try:
        if chrome:
            args = [chrome, "--new-window", url]
            if cfg["ui"].get("kiosk"):
                args = [chrome, "--kiosk", url]
            subprocess.Popen(args, close_fds=True)
        else:
            log.warning("Không tìm thấy Google Chrome - mở bằng trình duyệt mặc định")
            os.startfile(url)
    except Exception:
        log.exception("Không mở được trình duyệt, hãy tự mở %s", url)


def main():
    cfg = config.load()
    os.makedirs(config.DATA_DIR, exist_ok=True)
    logsetup.setup(config.path(cfg["log"]["dir"]), cfg["log"]["level"], cfg["log"]["keep_days"])
    log.info("=" * 70)
    log.info("G8 ID %s khởi động | trạm %s | Python %s | pid %s", config.VERSION,
             cfg["station_id"], sys.version.split()[0], os.getpid())

    if port_in_use(cfg["ui"]["port"]):
        log.warning("Cổng %s đang được dùng - phần mềm đã chạy sẵn, chỉ mở lại màn hình",
                    cfg["ui"]["port"])
        open_browser(cfg)
        return 3

    from . import webui
    from .engine import Engine

    db.connect()
    engine = Engine()
    servers = []

    def cleanup(reason):
        """Chạy đúng một lần dù thoát bằng cách nào: nút Thoát, Ctrl+C, dấu X cửa sổ, tắt máy."""
        global _cleaned
        with _cleanup_lock:
            if _cleaned:
                return
            _cleaned = True
            log.warning("Thoát phần mềm (%s)", reason)
            try:
                engine.shutdown()
            except Exception:
                log.exception("Lỗi khi đóng thiết bị")
            for s in servers:
                s.stop()
            try:
                db.close()
            except Exception:
                log.exception("Lỗi khi đóng MongoDB")
            log.info("Đã thoát sạch")
            logging.shutdown()

    def request_quit(*_):
        _quit.set()

    signal.signal(signal.SIGINT, request_quit)
    signal.signal(signal.SIGTERM, request_quit)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, request_quit)

    # Bấm dấu X của cửa sổ đen / đăng xuất / tắt máy: Windows cho ~5 s để dọn dẹp.
    global _ctrl_handler

    def on_console(ctrl_type):
        if ctrl_type in (2, 5, 6):          # CLOSE, LOGOFF, SHUTDOWN
            cleanup("đóng cửa sổ / tắt máy (ctrl=%s)" % ctrl_type)
            os._exit(0)
        return False

    _ctrl_handler = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)(on_console)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_ctrl_handler, True)

    code = 0
    try:
        engine.dev.start()
        ui = webui.Server(webui.build_ui(engine, request_quit), cfg["ui"]["host"],
                          cfg["ui"]["port"], "web-ui", threads=8)
        ui.start()
        servers.append(ui)
        try:
            orders = webui.Server(webui.build_order_server(engine), cfg["order_server"]["host"],
                                  cfg["order_server"]["port"], "web-orders", threads=4)
            orders.start()
            servers.append(orders)
            engine.wcs = True
        except OSError as e:
            # Không chặn màn hình: báo WCS đỏ để kỹ thuật biết cổng nhận lệnh đang bị chiếm.
            log.error("Khởi động server nhận lệnh lỗi (cổng %s): %s",
                      cfg["order_server"]["port"], e)
        log.info("Sẵn sàng sau %.1f s | chế độ %s | màn hình http://127.0.0.1:%s",
                 time.time() - engine.started_at, engine.mode, cfg["ui"]["port"])
        open_browser(cfg)

        last_janitor = 0.0
        while not _quit.wait(1.0):
            if time.time() - last_janitor > 3600:
                last_janitor = time.time()
                try:
                    db.janitor(engine.db)
                    logsetup.cleanup(cfg["log"]["keep_days"])
                except Exception:
                    log.exception("Lỗi dọn dữ liệu định kỳ")
    except Exception:
        log.exception("Lỗi nghiêm trọng - phần mềm sẽ được khởi động lại")
        code = 1
    cleanup("yêu cầu thoát" if code == 0 else "lỗi")
    return code


if __name__ == "__main__":
    try:
        rc = main()
    except Exception:
        logging.getLogger("crash").critical("Lỗi khi khởi động", exc_info=True)
        import traceback
        traceback.print_exc()
        rc = 1
    sys.exit(rc)
