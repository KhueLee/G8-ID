"""Kiểm tra kết nối từng thiết bị từ thẻ Cài đặt, với cấu hình đang chọn (chưa cần lưu).

Mỗi hàm mở cổng riêng, thử vài giây rồi đóng; trả (đạt?, câu giải thích cho công nhân).
Phần gọi (Engine.test_device) phải nhả cổng của driver đang chạy trước khi gọi.
"""
import re
import threading
import time

from .barcode import TRIGGER_OFF, TRIGGER_ON
from .scale import open_serial, parse_weight

SCALE_LISTEN_S = 3.0
BARCODE_QUIET_S = 0.8
BARCODE_WAIT_S = 6.0


def _open(cfg, timeout):
    if not cfg.get("port"):
        raise ValueError("chưa chọn cổng (None)")
    return open_serial(cfg, timeout)


def _shown(data):
    text = data.decode("ascii", "replace").replace("\r", "\\r").replace("\n", "\\n")
    return text[:60] + ("…" if len(text) > 60 else "")


def scale(cfg):
    """Cân phát số liên tục: nghe vài giây, đọc được khối lượng là đạt."""
    try:
        ser = _open(cfg, timeout=0.2)
    except Exception as e:
        return False, "Không mở được %s: %s" % (cfg.get("port") or "cổng", e)
    buf, weight = b"", None
    try:
        end = time.time() + SCALE_LISTEN_S
        while time.time() < end:
            buf += ser.read(256)
            for line in re.split(rb"[\r\n]+", buf)[:-1]:
                w = parse_weight(line.decode("ascii", "ignore"))
                if w is not None:
                    weight = w
            if weight is not None:
                break
    finally:
        ser.close()
    if weight is not None:
        return True, "ĐẠT: %s là cân, đang đọc %s g (bản tin: %s)" % (cfg["port"], weight, _shown(buf))
    if buf:
        return False, ("%s có dữ liệu nhưng không đọc ra khối lượng (%s). Kiểm tra baudrate."
                       % (cfg["port"], _shown(buf)))
    return False, ("Mở được %s nhưng %.0f s không có dữ liệu: cân đang tắt, sai cổng hoặc sai "
                   "baudrate." % (cfg["port"], SCALE_LISTEN_S))


def barcode(cfg):
    """Gửi lệnh bật quét, chờ công nhân đưa một mã vào; nhận được mã là đạt."""
    try:
        ser = _open(cfg, timeout=0.1)
    except Exception as e:
        return False, "Không mở được %s: %s" % (cfg.get("port") or "cổng", e)
    try:
        ser.reset_input_buffer()
        noise, end = b"", time.time() + BARCODE_QUIET_S
        while time.time() < end:
            noise += ser.read(128)
        if noise:
            return False, ("%s tự gửi dữ liệu khi chưa bật quét (%s): giống cân hơn là đầu đọc."
                           % (cfg["port"], _shown(noise)))
        ser.write(TRIGGER_ON)
        buf, end = b"", time.time() + BARCODE_WAIT_S
        while time.time() < end:
            chunk = ser.read(128)
            buf += chunk
            if buf and (not chunk or buf.endswith((b"\r", b"\n"))):
                break
        ser.write(TRIGGER_OFF)
    except Exception as e:
        return False, "Lỗi khi gửi lệnh tới %s: %s" % (cfg["port"], e)
    finally:
        ser.close()
    code = buf.decode("utf-8", "ignore").strip()
    if code:
        return True, "ĐẠT: %s là đầu đọc, đọc được mã %s" % (cfg["port"], code)
    return False, ("Đã gửi lệnh bật quét tới %s nhưng %.0f s không nhận được mã. Đèn quét có sáng "
                   "không? Không sáng = sai cổng / sai baudrate." % (cfg["port"], BARCODE_WAIT_S))


def printer(cfg):
    from .printer_godex import GodexPrinter
    if str(cfg.get("connect_type", "USB")).upper() == "COM" and not cfg.get("com_port"):
        return False, "Kiểu kết nối COM nhưng chưa chọn cổng (None)."
    p = GodexPrinter(cfg)
    try:
        with p._lock:
            p._connect()
            p._close()
    except Exception as e:
        return False, "Máy in: %s" % e
    return True, "ĐẠT: mở được máy in (%s). Bấm In thử để chắc chắn tem ra đúng." % cfg.get("connect_type")


def plc(cfg):
    """Open/Close MX Component trong luồng riêng (COM cần CoInitialize ở luồng gọi)."""
    from .plc_mx import MxPlc
    out = {}

    def run():
        import pythoncom
        pythoncom.CoInitialize()
        try:
            p = MxPlc(dict(cfg, enabled=True))
            ctl, via = p._open()
            ctl.Close()
            out["ok"] = "ĐẠT: nối được PLC qua %s, Logical Station %s" % (via, cfg.get("station_number", 0))
        except Exception as e:
            out["err"] = "PLC: %s" % e
        finally:
            ctl = None
            pythoncom.CoUninitialize()

    t = threading.Thread(target=run, name="plc-test", daemon=True)
    t.start()
    t.join(20)
    if t.is_alive():
        return False, "PLC không trả lời sau 20 s."
    return ("ok" in out), out.get("ok") or out.get("err")


TESTS = {"scale": scale, "barcode": barcode, "printer": printer, "plc": plc}
