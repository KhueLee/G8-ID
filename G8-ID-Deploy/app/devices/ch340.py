"""Tắt / bật lại cáp USB-SERIAL CH340 của PLC (giống rút cắm cáp) - không gỡ driver.

Trạm ST01 (28/10/2026): chip CH340 treo giữa lúc MX Component gửi (GetDevice 0x01808201), sau đó
driver kẹt ở trạng thái "đang mở": Open báo 0x0180800C, cổng thô báo Access denied mà không tiến
trình nào giữ handle. Tắt / bật lại thiết bị (kiem_tra_plc T6) chữa được ngay và chạy bền tiếp.
Cần quyền Administrator (chay_dinh_danh.bat tự xin); không có quyền thì bỏ qua, chỉ ghi log.
"""
import ctypes
import json
import logging
import re
import subprocess

log = logging.getLogger("device.plc")

# Mã trong CH341SER.INF (giống tools\reinstall_ch340.ps1, restart_ch340.bat).
CH340_IDS = ("USB\\VID_1A86&PID_7523", "USB\\VID_1A86&PID_5523", "USB\\VID_4348&PID_5523")
_NO_WINDOW = 0x08000000


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _ps(script, timeout=60):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + script],
                       capture_output=True, timeout=timeout, creationflags=_NO_WINDOW)
    return r.returncode, r.stdout.decode("utf-8", "ignore").strip(), r.stderr.decode("utf-8", "ignore").strip()


def present():
    """[{id, name, com}] các cáp CH340 đang cắm."""
    likes = " -or ".join("$_.InstanceId -like '%s*'" % i for i in CH340_IDS)
    rc, out, _ = _ps("@(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { %s } | "
                     "ForEach-Object { [pscustomobject]@{ id = $_.InstanceId; name = $_.FriendlyName } }) "
                     "| ConvertTo-Json" % likes)
    try:
        devs = json.loads(out) if out else []
    except ValueError:
        return []
    devs = devs if isinstance(devs, list) else [devs]
    for d in devs:
        m = re.search(r"\((COM\d+)\)", d.get("name") or "")
        d["com"] = m.group(1).upper() if m else ""
    return devs


def pick(devs, com_port):
    """Cáp CH340 của PLC: đúng cổng com_port; chưa biết cổng mà chỉ có một cáp thì lấy cáp đó.
    Có nhiều cáp mà không biết cổng thì không đoán - tránh tắt nhầm cân / đầu đọc dùng CH340."""
    want = str(com_port or "").upper()
    if want:
        return next((d for d in devs if d["com"] == want), None)
    return devs[0] if len(devs) == 1 else None


def restart(com_port):
    """Tắt / bật lại CH340 ở cổng com_port. Trả (được hay không, mô tả)."""
    if not is_admin():
        return False, "không có quyền Administrator (mở G8 ID bằng chay_dinh_danh.bat và bấm Yes)"
    try:
        dev = pick(present(), com_port)
        if dev is None:
            return False, "không thấy cáp CH340 ở %s" % (com_port or "cổng PLC")
        q = dev["id"].replace("'", "''")
        rc, _, err = _ps("Disable-PnpDevice -InstanceId '%s' -Confirm:$false -ErrorAction Stop; Start-Sleep 2; "
                         "Enable-PnpDevice -InstanceId '%s' -Confirm:$false -ErrorAction Stop" % (q, q))
        if rc != 0:
            return False, "tắt / bật lại %s lỗi: %s" % (dev["name"], err.splitlines()[0] if err else rc)
        return True, dev["name"]
    except Exception as e:
        return False, str(e)
