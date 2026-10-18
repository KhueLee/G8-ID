"""Tự dò cổng COM của từng thiết bị theo tên Windows đặt cho cổng (Device Manager → Ports).

Trạm chuẩn: đầu đọc Honeywell = "USB Serial Device", cân (cáp FTDI) = "USB Serial Port",
PLC (cáp CH340) = "USB-SERIAL CH340"; máy in Godex đi USB nên không có cổng COM.
Thiết bị bật "auto" được gán cổng khớp mẫu `detect`; không thấy (hoặc thấy nhiều cổng khớp) thì
để None và báo chọn cổng thủ công. Thiết bị chọn tay (auto = false) giữ nguyên cổng đã chọn.
"""
import logging

log = logging.getLogger("device.ports")

# thiết bị -> khoá chứa cổng trong config["devices"][thiết bị]
AUTO_KEYS = {"scale": "port", "barcode": "port", "plc": "com_port"}


def list_ports():
    try:
        from serial.tools import list_ports as lp
        ports = sorted(lp.comports(), key=lambda p: (len(p.device), p.device))  # COM2 trước COM10
        return [{"port": p.device, "desc": p.description, "hwid": p.hwid} for p in ports]
    except Exception:
        return []


def detect(devices, ports):
    """{thiết bị: (cổng hoặc "", ghi chú)} cho các thiết bị đang bật tự dò."""
    from ..config import com_ports
    auto = {d for d, k in AUTO_KEYS.items() if devices[d].get("auto", True)}
    taken = {p for d, p in com_ports(devices).items() if d not in auto}
    out = {}
    for d in AUTO_KEYS:
        c = devices[d]
        if d not in auto or (d == "plc" and not c.get("enabled", True)):
            continue
        pat = str(c.get("detect") or "").strip()
        hits = [p["port"] for p in ports
                if pat and pat.lower() in p["desc"].lower() and p["port"].upper() not in taken]
        if len(hits) == 1:
            out[d] = (hits[0], "")
            taken.add(hits[0].upper())
        elif hits:
            out[d] = ("", "có %d cổng \"%s\" (%s) - chọn cổng thủ công ở thẻ Cài đặt"
                      % (len(hits), pat, ", ".join(hits)))
        else:
            out[d] = ("", "không thấy cổng \"%s\" - kiểm tra cáp hoặc chọn cổng thủ công ở thẻ "
                          "Cài đặt" % pat)
    return out


def apply(cfg):
    """Gán cổng tự dò vào cfg (trong bộ nhớ). Trả {thiết bị: ghi chú} của thiết bị chưa có cổng."""
    devices = cfg["devices"]
    found = detect(devices, list_ports())
    notes = {}
    for d, (port, note) in found.items():
        key = AUTO_KEYS[d]
        if port:
            if str(devices[d].get(key) or "").upper() != port.upper():
                log.info("Tự dò cổng %s: %s -> %s", d, devices[d].get(key) or "None", port)
            else:
                log.info("Tự dò cổng %s: %s", d, port)
        else:
            log.warning("Tự dò cổng %s: %s", d, note)
            notes[d] = note
        devices[d][key] = port
    return notes
