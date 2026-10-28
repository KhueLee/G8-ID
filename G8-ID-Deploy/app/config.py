"""Cấu hình trạm: config.json (thiết bị, cổng, địa chỉ server) + giá trị mặc định."""
import copy
import json
import os
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.environ.get("G8ID_CONFIG") or os.path.join(BASE_DIR, "config.json")
VERSION = "2.4.5"

DEFAULTS = {
    "station_id": "ST01",
    "desk_no": 1,                # số thứ tự bàn định danh (hiện trên màn hình, thẻ Thông số)
    "software_name": "ĐỊNH DANH SẢN PHẨM",
    "ui": {"host": "0.0.0.0", "port": 8600, "password": "1234",
           "open_browser": True, "kiosk": False},
    "order_server": {"host": "0.0.0.0", "port": 8500},
    "mongo": {"uri": "mongodb://127.0.0.1:27017", "db": "g8id", "db_manual": "g8id_manual",
              "start_bundled": True, "cache_gb": 0.25, "history_days": 90,
              "event_log_days": 30, "history_max_docs": 300000},
    "log": {"dir": "logs", "level": "INFO", "keep_days": 30, "raw_device": False},
    "devices": {
        # auto = mỗi lần khởi động / lưu cấu hình tự tìm cổng có tên Windows chứa `detect`
        # (Device Manager → Ports); auto = false thì dùng đúng `port` đã chọn tay.
        "scale": {"auto": True, "detect": "USB Serial Port", "port": "COM4", "baudrate": 9600, "bytesize": 8, "parity": "N",
                  "stopbits": 1, "stale_s": 2.0, "reopen_s": 10.0},
        "barcode": {"auto": True, "detect": "USB Serial Device", "port": "COM3", "baudrate": 9600, "bytesize": 8, "parity": "N",
                    "stopbits": 1},
        "printer": {"connect_type": "USB", "usb_name": "", "com_port": "COM5",
                    "baudrate": 9600, "lan_ip": "", "lan_port": 9100,
                    "driver_name": "Godex EZ520+", "logo": "drivers/G8_Label.bmp"},
        # MX Component: station_number = Logical Station trong Communication Settings Utility;
        # password = remote password của PLC (nếu có); keepalive_s = chu kỳ đọc thử M10 (0 = tắt);
        # com_port = cổng COM đã đặt cho Logical Station, chỉ để thẻ Cài đặt không gán trùng.
        # buttons = bit nút vật lý trên tủ như bản cũ ("" = không dùng nút đó), đọc mỗi
        # button_poll_ms; có đọc nút thì không cần đọc thử M10.
        "plc": {"enabled": True, "station_number": 0, "password": "", "keepalive_s": 5,
                "progid": "", "com_port": "", "auto": True, "detect": "CH340",
                "buttons": {"start": "M20", "stop": "M22", "identify": "M21"},
                "button_poll_ms": 200},
    },
    "servers": {
        "pallet_done_url": "http://192.168.110.189:8060/identify-service/ids/pallet_identify_done",
        "timeout_s": 10, "retry_s": 30,
    },
    "simulator": {"host": "127.0.0.1", "port": 8700},
}

# Thông số vận hành sửa từ thẻ Cài đặt (lưu trong MongoDB, collection settings).
SETTING_DEFAULTS = {
    "scale_value": 300,          # khối lượng chuẩn (g) - dùng khi lệnh không gửi Weight_ref / GW
    "scale_error": 100,          # sai số cho phép (g)
    "time_scale": 2,             # thời gian cân ổn định (s)
    "positions": ["S01.120.01", "S01.121.01", "S01.122.01",
                  "S01.123.01", "S01.124.01", "S01.125.01"],
    "pallet_done_trigger": "button",  # button = bấm ĐỊNH DANH (như bản cũ) | auto = tự gửi
    "confirm_new_order": False,       # hỏi Yes/No khi có lệnh mới
    "auto_start_on_order": True,      # lệnh mới nạp xong mà trạm đang STOP thì tự bấm Bắt đầu
    "zero_threshold_g": 20,
    "stable_jitter_g": 15,
}

_lock = threading.RLock()
_cfg = None


def _merge(base, extra):
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load():
    global _cfg
    with _lock:
        cfg = copy.deepcopy(DEFAULTS)
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                _merge(cfg, json.load(f))
        _cfg = cfg
        return cfg


def get():
    return _cfg if _cfg is not None else load()


def save(patch):
    """Gộp patch vào config.json (ghi file tạm rồi đổi tên để không hỏng file khi mất điện)."""
    with _lock:
        cfg = get()
        _merge(cfg, patch)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
        return cfg


DEVICE_NAMES = {"scale": "Cân", "barcode": "Đầu đọc", "printer": "Máy in", "plc": "PLC"}


def com_ports(devices):
    """{thiết bị: cổng COM} của các thiết bị đang dùng cổng COM (bỏ cổng None)."""
    d = devices
    ports = {"scale": d["scale"].get("port"), "barcode": d["barcode"].get("port")}
    if str(d["printer"].get("connect_type", "")).upper() == "COM":
        ports["printer"] = d["printer"].get("com_port")
    if d["plc"].get("enabled", True):
        ports["plc"] = d["plc"].get("com_port")
    return {k: str(v).strip().upper() for k, v in ports.items() if v and str(v).strip()}


def com_conflict(devices):
    """Câu báo lỗi nếu hai thiết bị cùng chọn một cổng COM, không trùng thì ''."""
    seen = {}
    for name, port in com_ports(devices).items():
        if port in seen:
            return "%s đang được chọn cho cả %s và %s." % (port, DEVICE_NAMES[seen[port]],
                                                          DEVICE_NAMES[name])
        seen[port] = name
    return ""


def path(*parts):
    p = os.path.join(*parts)
    return p if os.path.isabs(p) else os.path.join(BASE_DIR, p)


DATA_DIR = os.environ.get("G8ID_DATA") or os.path.join(BASE_DIR, "data")
MODE_FILE = os.path.join(DATA_DIR, "mode.json")
SIM_BAT_LOCK = os.path.join(DATA_DIR, "simulator_bat.lock")
GUIDE_PDF = "HUONG_DAN_VAN_HANH.pdf"       # nút Hướng dẫn trên màn hình chính và công cụ mô phỏng
