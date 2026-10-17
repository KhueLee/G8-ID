"""Kiểm tra máy trạm trước khi chạy (check_env.bat). Chỉ ĐỌC, không sửa gì trên máy.

Chạy được cả khi phần mềm chính đang chạy. Kết quả in ra màn hình và ghi logs\\check_env.txt
để gửi cho người hỗ trợ.
"""
import ctypes
import importlib
import os
import socket
import struct
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
lines = []
bad = 0


def out(level, text):
    global bad
    if level == "LỖI":
        bad += 1
    line = "[%-8s] %s" % (level, text)
    lines.append(line)
    print(line)


def port_busy(port):
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", int(port))) == 0
    finally:
        s.close()


def main():
    out("INFO", "G8 ID - kiểm tra môi trường lúc %s" % time.strftime("%d/%m/%Y %H:%M:%S"))
    bits = struct.calcsize("P") * 8
    out("OK" if sys.version_info >= (3, 10) else "LỖI",
        "Python %s (%d-bit) tại %s" % (sys.version.split()[0], bits, sys.executable))

    for mod in ("pymongo", "serial", "flask", "waitress", "win32com.client", "comtypes"):
        try:
            importlib.import_module(mod)
            out("OK", "Thư viện %s" % mod)
        except Exception as e:
            out("CẢNH BÁO" if mod in ("win32com.client", "comtypes") else "LỖI",
                "Thiếu thư viện %s (%s) -> chạy install.bat" % (mod, e))

    from app import config
    cfg = config.load()
    out("INFO", "Mã trạm %s | file cấu hình %s" % (cfg["station_id"], config.CONFIG_PATH))

    # MongoDB
    mongod = config.path("mongodb", "bin", "mongod.exe")
    out("OK" if os.path.exists(mongod) else "CẢNH BÁO", "mongod kèm theo: %s" % mongod)
    try:
        import pymongo
        c = pymongo.MongoClient(cfg["mongo"]["uri"], serverSelectionTimeoutMS=1500)
        v = c.server_info()["version"]
        names = [cfg["mongo"]["db"], cfg["mongo"]["db_manual"]]
        sizes = ", ".join("%s: %.1f MB" % (n, c[n].command("dbstats")["dataSize"] / 1048576)
                          for n in names)
        out("OK", "MongoDB %s đang chạy (%s)" % (v, sizes))
        c.close()
    except Exception:
        out("INFO", "MongoDB chưa chạy - phần mềm sẽ tự bật mongod kèm theo khi khởi động")

    # Cổng mạng
    running = port_busy(cfg["ui"]["port"])
    out("INFO", "Phần mềm chính %s (cổng màn hình %s)" %
        ("ĐANG CHẠY" if running else "chưa chạy", cfg["ui"]["port"]))
    if not running and port_busy(cfg["order_server"]["port"]):
        out("LỖI", "Cổng nhận lệnh %s đang bị chương trình khác chiếm (bản WinForms cũ còn chạy?)"
            % cfg["order_server"]["port"])
    try:
        r = subprocess.run(["netsh", "advfirewall", "firewall", "show", "rule", "name=all", "dir=in"],
                           capture_output=True, text=True, errors="ignore", timeout=20)
        has = str(cfg["order_server"]["port"]) in r.stdout
        out("OK" if has else "CẢNH BÁO", "Firewall %s luật mở cổng %s cho hệ thống gửi lệnh%s" % (
            "đã có" if has else "CHƯA thấy", cfg["order_server"]["port"],
            "" if has else " -> chạy tools\\open_firewall.bat bằng quyền Admin"))
    except Exception as e:
        out("INFO", "Không đọc được firewall: %s" % e)

    # Cổng COM
    try:
        from serial.tools import list_ports
        ports = list(list_ports.comports())
        if not ports:
            out("CẢNH BÁO", "Windows không thấy cổng COM nào")
        for p in ports:
            out("INFO", "Cổng %s: %s [%s]" % (p.device, p.description, p.hwid))
            if "ballpoint" in p.description.lower() or "serial mouse" in p.description.lower():
                out("LỖI", "%s bị Windows nhận nhầm là chuột serial -> chạy tools\\fix_serial_mouse.bat"
                    % p.device)
        have = {p.device.upper() for p in ports}
        for name in ("scale", "barcode"):
            want = str(cfg["devices"][name]["port"] or "").upper()
            if not want:
                out("CẢNH BÁO", "%s chọn cổng None - không dùng" % name.upper())
                continue
            out("OK" if want in have else "LỖI", "%s cấu hình %s %s" % (
                name.upper(), want, "- có trên máy" if want in have else "- KHÔNG có trên máy"))
        why = config.com_conflict(cfg["devices"])
        if why:
            out("LỖI", why)
        if not running:
            import serial
            for name in ("scale", "barcode"):
                want = cfg["devices"][name]["port"] or ""
                if want and want.upper() in have:
                    try:
                        serial.Serial(want, int(cfg["devices"][name]["baudrate"]), timeout=0.2).close()
                        out("OK", "Mở/đóng thử %s được" % want)
                    except Exception as e:
                        out("LỖI", "Không mở được %s: %s (cổng đang bị chương trình khác giữ?)"
                            % (want, e))
    except Exception as e:
        out("LỖI", "Không liệt kê được cổng COM: %s" % e)

    # Chuột serial: nguyên nhân hay gặp khiến cổng CH340 của cân bị "chiếm" sau khi khởi động máy
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Services\sermouse") as k:
            start = winreg.QueryValueEx(k, "Start")[0]
        out("OK" if start == 4 else "CẢNH BÁO", "Dịch vụ chuột serial (sermouse) Start=%s %s" % (
            start, "(đã tắt)" if start == 4 else
            "- cân phát dữ liệu liên tục có thể bị Windows nhận nhầm là chuột khi khởi động "
            "-> chạy tools\\fix_serial_mouse.bat bằng quyền Admin"))
    except OSError:
        out("OK", "Không có dịch vụ chuột serial (sermouse)")

    # Máy in Godex
    dll = config.path("drivers", "EZio64.dll" if bits == 64 else "EZio32.dll")
    try:
        lib = ctypes.CDLL(dll) if bits == 64 else ctypes.WinDLL(dll)
        out("OK", "Nạp được %s" % dll)
        if not running:
            buf = ctypes.create_string_buffer(256)
            lib.FindFirstUSB.argtypes, lib.FindFirstUSB.restype = [ctypes.c_char_p], ctypes.c_int
            found = lib.FindFirstUSB(buf) == 1
            out("OK" if found else "CẢNH BÁO", "Máy in Godex USB: %s" % (
                buf.value.decode("mbcs", "ignore") if found else "không tìm thấy"))
    except Exception as e:
        out("LỖI", "Không nạp được %s: %s" % (dll, e))
    logo = config.path(cfg["devices"]["printer"]["logo"])
    out("OK" if os.path.exists(logo) else "CẢNH BÁO", "Logo in trên tem: %s" % logo)

    # MX Component (PLC)
    if cfg["devices"]["plc"].get("enabled", True):
        # ActUtlType64 (MX Component 5) là máy chủ COM .exe -> tìm theo CLSID, dùng được với
        # Python 32 lẫn 64-bit. ActUtlType (MX Component 4) là DLL 32-bit -> chỉ Python 32-bit.
        ids = [(r"CLSID\{F0B1A112-BFCB-4DA3-9535-C296D69A17E0}\LocalServer32",
                "ActUtlType64 (MX Component 5)")]
        if bits == 32:
            ids.append((r"ActUtlType.ActUtlType\CLSID", "ActUtlType (32-bit)"))
        if cfg["devices"]["plc"].get("progid"):
            ids = [(cfg["devices"]["plc"]["progid"] + r"\CLSID", cfg["devices"]["plc"]["progid"])]
        try:
            import winreg
            found = []
            for key, label in ids:
                for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                    try:
                        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key, 0,
                                                       winreg.KEY_READ | view))
                        found.append(label)
                        break
                    except OSError:
                        pass
            out("OK" if found else "CẢNH BÁO", "MX Component: %s" % (
                ", ".join(found) + " - Logical Station %s phải được tạo trong Communication "
                "Settings Utility" % cfg["devices"]["plc"].get("station_number", 0) if found else
                "chưa cài bản dùng được cho Python %d-bit (đèn tháp sẽ không sáng, trạm vẫn chạy)"
                % bits))
        except Exception as e:
            out("INFO", "Không kiểm tra được MX Component: %s" % e)

    chrome = [os.path.join(os.environ.get(k, ""), r"Google\Chrome\Application\chrome.exe")
              for k in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")]
    out("OK" if any(os.path.exists(c) for c in chrome) else "CẢNH BÁO", "Google Chrome")
    free = ctypes.c_ulonglong(0)
    ctypes.windll.kernel32.GetDiskFreeSpaceExW(ROOT, None, None, ctypes.byref(free))
    gb = free.value / 1073741824
    out("OK" if gb > 5 else "CẢNH BÁO", "Ổ đĩa còn trống %.1f GB" % gb)

    out("INFO", "KẾT LUẬN: %s" % ("%d LỖI cần xử lý" % bad if bad else "không có lỗi chặn"))
    try:
        log_dir = config.path(cfg["log"]["dir"])
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "check_env.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("\nĐã ghi kết quả vào %s" % os.path.join(log_dir, "check_env.txt"))
    except OSError:
        pass
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
