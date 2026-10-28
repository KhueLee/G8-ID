"""Khởi động lại cáp USB-SERIAL CH340 của PLC (giống rút cắm cáp) - chỉ cáp PLC, không gỡ driver.

Trạm ST01 (28/10/2026): chip CH340 treo giữa lúc MX Component gửi (GetDevice 0x01808201), sau đó
driver kẹt "đang mở" (Open 0x0180800C mãi). Khởi động lại thiết bị chữa được ngay (kiem_tra_plc T6).

Chỉ chạm đúng MỘT thiết bị: cáp CH340 (VID/PID trong CH341SER.INF) có số COM bằng cổng PLC.
Không làm gì khi chưa biết cổng PLC, cổng PLC trùng cổng thiết bị khác, hoặc không thấy cáp đó.
Dùng `pnputil /restart-device` (một lệnh, không để thiết bị ở trạng thái "đã tắt" như
Disable-PnpDevice - bản 2.4.7 dùng Disable / Enable, trạm ST01 báo Generic failure).
Cần quyền Administrator (chay_dinh_danh.bat tự xin); không có quyền thì bỏ qua, chỉ ghi log.
"""
import ctypes
import json
import re
import subprocess
import time

# Mã trong CH341SER.INF (giống tools\reinstall_ch340.ps1, restart_ch340.bat).
CH340_IDS = ("USB\\VID_1A86&PID_7523", "USB\\VID_1A86&PID_5523", "USB\\VID_4348&PID_5523")
_NO_WINDOW = 0x08000000


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run(args, timeout=60, encoding="utf-8"):
    """encoding: utf-8 cho PowerShell (đã đặt OutputEncoding), "oem" cho pnputil (bảng mã console)."""
    r = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=_NO_WINDOW)
    return (r.returncode, r.stdout.decode(encoding, "ignore").strip(),
            r.stderr.decode(encoding, "ignore").strip())


def present():
    """[{id, name, status, com}] các cáp CH340 đang cắm."""
    likes = " -or ".join("$_.InstanceId -like '%s*'" % i for i in CH340_IDS)
    rc, out, _ = _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                       "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
                       "@(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { %s } | "
                       "ForEach-Object { [pscustomobject]@{ id = $_.InstanceId; name = $_.FriendlyName; "
                       "status = \"$($_.Status)\" } }) | ConvertTo-Json" % likes])
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
    """Cáp CH340 đúng cổng com_port. Không đoán khi chưa biết cổng."""
    want = str(com_port or "").strip().upper()
    return next((d for d in devs if want and d["com"] == want), None)


def check(com_port, other_ports=()):
    """Lý do KHÔNG được khởi động lại (bền, không tự hết khi chạy tiếp), hoặc "" nếu được."""
    want = str(com_port or "").strip().upper()
    if not is_admin():
        return "không có quyền Administrator (mở G8 ID bằng chay_dinh_danh.bat và bấm Yes)"
    if not want:
        return "chưa biết cổng COM của PLC (devices.plc.com_port trống)"
    if want in {str(p or "").strip().upper() for p in other_ports}:
        return "cổng PLC %s trùng cổng thiết bị khác - không đụng tới" % want
    return ""


def restart(com_port, other_ports=()):
    """Khởi động lại cáp CH340 ở cổng com_port. Trả (được hay không, mô tả)."""
    why = check(com_port, other_ports)
    if why:
        return False, why
    dev = pick(present(), com_port)
    if dev is None:
        return False, "không thấy cáp CH340 ở %s" % com_port
    rc, out, err = _run(["pnputil", "/restart-device", dev["id"]], timeout=60, encoding="oem")
    text = " ".join((out + " " + err).split())
    if rc == 3010:
        return False, "pnputil báo cần khởi động lại máy mới xong (%s)" % text
    if rc != 0:
        return False, "pnputil /restart-device lỗi %s: %s" % (rc, text)
    for _ in range(20):                          # chờ Windows bật lại xong (tối đa ~10 s)
        now = pick(present(), com_port)
        if now and now.get("status") == "OK":
            return True, now["name"]
        time.sleep(0.5)
    return False, "đã khởi động lại nhưng %s chưa sẵn sàng" % com_port
